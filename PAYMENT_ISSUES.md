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

**Status:** Mostly fixed. `checkout_create_payment` now rejects the request up front if `product.quantity < qty` or the product isn't `stock_available`, so a Razorpay order is never created for something that's already out of stock. `checkout_verify_payment` now takes a `select_for_update()` row lock on each product before decrementing, so two verify calls racing on the same product serialize instead of both reading the same starting quantity.

Not fully closed: there's still a window between `checkout_create_payment`'s check and the customer actually completing payment in the Razorpay popup. If two people are mid-payment for the last unit at the same time, both can still succeed (each already paid Razorpay before either verify call runs) - avoiding that completely requires reserving stock at order-creation time (with a release-on-timeout) or moving to Razorpay's manual-capture flow, which is a bigger change than this fix. This is the same underlying gap as issue #3.

---

## 3. No webhook — a captured payment can leave no order behind

**Files:** [product/views.py:1080-1160](product/views.py#L1080-L1160), [product/templates/product/checkout.html:507-509](product/templates/product/checkout.html#L507-L509)

Order creation only happens client-side, triggered by Razorpay's JS `handler` callback calling `/checkout/verify/`. Payments are auto-captured (`payment_capture: 1`) the moment the customer pays. If the browser/tab closes, crashes, or loses network between payment success and that AJAX call completing, Razorpay has already taken the money but no `Order` row is ever created — a paid order silently vanishes with no automatic way to reconcile it.

**Fix direction:** add a Razorpay webhook endpoint (e.g. `payment.captured` event) that creates the Order server-side independent of the browser session, using the same logic as `checkout_verify_payment`. Requires configuring a webhook secret and signature verification.

A real fix needs the Order to be creatable without the browser's session (Razorpay's servers call the webhook, not the customer's browser, so `request.session['pending_order']` isn't available to it). The clean way to do that: create the `Order` immediately when payment starts (status `'Payment Pending'`), then have both the browser callback (`checkout_verify_payment`) and the new webhook flip it to `'Order Placed'` - whichever fires first, guarded by the same idempotency check added for issue #4.

Trade-off discussed with the team: this means an abandoned checkout (customer closes the Razorpay popup without paying) leaves a permanent `'Payment Pending'` row instead of vanishing like today, which would show up in `my_orders.html` and the admin order lists unless explicitly filtered out. Decided to **defer this** until there's a decision on how pending/abandoned orders should be surfaced to customers vs. admins, rather than ship that UX change bundled into a bug fix.

**Status:** Deliberately deferred (2026-08-09). Not fixed. Revisit once the pending-order UX question above is decided.

---

## 4. No idempotency on verify — possible duplicate orders

**File:** [product/models.py:114-115](product/models.py#L114-L115), [product/views.py:1080-1160](product/views.py#L1080-L1160)

`Order.razorpay_payment_id` has no unique constraint, and `checkout_verify_payment` doesn't check for an existing order with that payment ID before creating a new one. A retried/duplicated request (double-click, network retry, or overlap with the webhook fix in #3) can create two `Order` rows for a single payment.

**Fix direction:** add a unique constraint on `razorpay_payment_id` (nullable, so it doesn't affect non-Razorpay orders), and have `checkout_verify_payment` check for an existing order with that payment ID first and short-circuit if found.

**Status:** Mostly fixed. `checkout_verify_payment` now checks `Order.objects.filter(razorpay_order_id=razorpay_order_id).first()` at the top of its atomic block and, if found, returns success without creating a second `Order`/`OrderItem`s or decrementing stock again - this covers double-clicks and client-side retries, which is the realistic case today (the confirm button is also disabled client-side while a request is in flight).

Not fully closed: this is an application-level check, not a DB-level guarantee - a genuine simultaneous race (two requests hitting the check at the same instant, before either has committed its `Order.objects.create()`) could theoretically still slip through. Closing that fully needs a `unique=True` constraint on `Order.razorpay_order_id`, which requires a migration against the shared database - deferred alongside issue #3 since it's the same "needs a schema change" category, and the two are easiest to do together once the webhook design is settled.
