# Payment Integration — Known Issues

Findings from a review of the Razorpay checkout flow ([product/views.py](product/views.py) and [product/templates/product/checkout.html](product/templates/product/checkout.html)). Ordered by severity. Each will get its own fix + commit.

---

## 1. Critical: price and discount are entirely client-controlled

**Files:** [product/views.py:991-1160](product/views.py#L991-L1160), [product/templates/product/checkout.html:258-268](product/templates/product/checkout.html#L258-L268)

`checkout_create_payment` computes the charged amount from `cart_items` and `coupon_discount` sent in the POST body, without re-fetching `Product.price` from the database or re-validating the coupon server-side:

```python
total_amount = sum(float(item.get('price', 0)) * int(item.get('qty', 1)) for item in cart_items)
...
coupon_discount = float(request.POST.get('coupon_discount', 0) or 0)
coupon_discount = max(0, min(coupon_discount, total_amount))
total_amount -= coupon_discount
```

The "Buy Now" flow makes this trivially exploitable — price comes straight from the URL query string:

```js
price: parseFloat(params.get('price')) || 0,
```

Anyone can edit `?price=1` in the address bar and check out a real product for ₹1.

**Fix direction:** in `checkout_create_payment` and `checkout_verify_payment`, look up each `product_id` server-side and use `Product.objects.get(pk=...).price`. Recompute the coupon discount server-side using the same validation logic as `apply_coupon` instead of trusting the client-sent `coupon_discount`.

**Status:** Fixed (commit `175477f`). `checkout_create_payment` now re-prices every line item from `Product.price` and revalidates the coupon via a shared `_validate_coupon` helper (used by both `apply_coupon` and here) instead of trusting `cart_data`/`coupon_discount` from the client. `checkout_verify_payment` already read its values from the session dict this populates, so it inherits the fix automatically.

---

## 2. No stock check before accepting payment

**File:** [product/views.py:991-1078](product/views.py#L991-L1078) (create), [product/views.py:1140-1143](product/views.py#L1140-L1143) (decrement)

Nothing checks `Product.quantity` / `stock_available` before creating the Razorpay order. Stock is only decremented after payment, floored at 0:

```python
Product.objects.filter(pk=product_id).update(
    quantity=Greatest(F('quantity') - qty, Value(0))
)
```

Two concurrent buyers of the last unit can both pay successfully, causing an oversell that has to be resolved manually afterward.

**Fix direction:** validate requested quantity against current stock in `checkout_create_payment` before creating the Razorpay order, and re-check inside the `transaction.atomic()` block in `checkout_verify_payment` (with a `select_for_update()` or similar) before decrementing, so a losing concurrent request fails instead of overselling.

**Status:** Not fixed.

---

## 3. No webhook — a captured payment can leave no order behind

**Files:** [product/views.py:1080-1160](product/views.py#L1080-L1160), [product/templates/product/checkout.html:507-509](product/templates/product/checkout.html#L507-L509)

Order creation only happens client-side, triggered by Razorpay's JS `handler` callback calling `/checkout/verify/`. Payments are auto-captured (`payment_capture: 1`) the moment the customer pays. If the browser/tab closes, crashes, or loses network between payment success and that AJAX call completing, Razorpay has already taken the money but no `Order` row is ever created — a paid order silently vanishes with no automatic way to reconcile it.

**Fix direction:** add a Razorpay webhook endpoint (e.g. `payment.captured` event) that creates the Order server-side independent of the browser session, using the same logic as `checkout_verify_payment`. Requires configuring a webhook secret and signature verification.

**Status:** Not fixed.

---

## 4. No idempotency on verify — possible duplicate orders

**File:** [product/models.py:114-115](product/models.py#L114-L115), [product/views.py:1080-1160](product/views.py#L1080-L1160)

`Order.razorpay_payment_id` has no unique constraint, and `checkout_verify_payment` doesn't check for an existing order with that payment ID before creating a new one. A retried/duplicated request (double-click, network retry, or overlap with the webhook fix in #3) can create two `Order` rows for a single payment.

**Fix direction:** add a unique constraint on `razorpay_payment_id` (nullable, so it doesn't affect non-Razorpay orders), and have `checkout_verify_payment` check for an existing order with that payment ID first and short-circuit if found.

**Status:** Not fixed.
