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

Not fully closed: there's still a window between `checkout_create_payment`'s check and the customer actually completing payment in the Razorpay popup. If two people are mid-payment for the last unit at the same time, both can still succeed (each already paid Razorpay before either finalize step runs) - avoiding that completely requires reserving stock at order-creation time (with a release-on-timeout, similar in spirit to the `'Payment Pending'` order itself but for the stock count specifically) or moving to Razorpay's manual-capture flow. Bigger change than this fix; not attempted here.

---

## 3. No webhook — a captured payment can leave no order behind

**Files:** [product/views.py:1080-1160](product/views.py#L1080-L1160), [product/templates/product/checkout.html:507-509](product/templates/product/checkout.html#L507-L509)

Order creation only happens client-side, triggered by Razorpay's JS `handler` callback calling `/checkout/verify/`. Payments are auto-captured (`payment_capture: 1`) the moment the customer pays. If the browser/tab closes, crashes, or loses network between payment success and that AJAX call completing, Razorpay has already taken the money but no `Order` row is ever created — a paid order silently vanishes with no automatic way to reconcile it.

**Fix direction:** add a Razorpay webhook endpoint (e.g. `payment.captured` event) that creates the Order server-side independent of the browser session, using the same logic as `checkout_verify_payment`. Requires configuring a webhook secret and signature verification.

A real fix needs the Order to be creatable without the browser's session (Razorpay's servers call the webhook, not the customer's browser, so `request.session['pending_order']` isn't available to it). The clean way to do that: create the `Order` immediately when payment starts (status `'Payment Pending'`), then have both the browser callback (`checkout_verify_payment`) and the new webhook flip it to `'Order Placed'` - whichever fires first, guarded by the same idempotency check added for issue #4.

Trade-off originally raised: an abandoned checkout (customer closes the Razorpay popup without paying) would leave a permanent `'Payment Pending'` row instead of vanishing like today. Resolved by making abandonment fully self-cleaning instead of just filtering the row out of views - see below.

**Status:** Fixed (2026-08-09).

- `checkout_create_payment` now creates the `Order` + `OrderItem`s immediately at status `'Payment Pending'`, before the customer even opens the Razorpay popup. Nothing else (stock, cart, `UserData`) is touched at this point - the only side effect is the coupon's `used_count` being bumped provisionally (see below).
- `checkout_verify_payment` (browser callback) and the new `razorpay_webhook` endpoint (`/razorpay/webhook/`, `payment.captured` event) both call a shared `_finalize_paid_order()` - whichever fires first flips the order to `'Order Placed'`, decrements stock, clears the cart, and sends the confirmation emails; the other is a no-op (idempotent, guarded by `select_for_update()` inside the same transaction).
- `_cleanup_stale_pending_orders()` deletes any `'Payment Pending'` order older than 30 minutes, and reverses the coupon `used_count` bump if one was tied to it - so an abandoned checkout fully rolls back to as if it never happened, rather than lingering as a visible artifact. It's called on `my_orders` and `admin_dashboard` page loads, plus at the start of every new checkout attempt.
- Added `Order.coupon_code` / `Order.coupon_discount` fields (migration `0037_order_coupon_code_order_coupon_discount`, applied) so the webhook - which has no browser session to read - and the cleanup routine can both see what a given order attempt claimed.
- The webhook is inert until `RAZORPAY_WEBHOOK_SECRET` is set (see `.env.example`) - **still needs to be configured in the Razorpay Dashboard** (Settings > Webhooks > add webhook pointing at `/razorpay/webhook/`, subscribed to `payment.captured`) before it actually does anything. That configuration step has to happen outside this codebase.

---

## 4. No idempotency on verify — possible duplicate orders

**File:** [product/models.py:114-115](product/models.py#L114-L115), [product/views.py:1080-1160](product/views.py#L1080-L1160)

`Order.razorpay_payment_id` has no unique constraint, and `checkout_verify_payment` doesn't check for an existing order with that payment ID before creating a new one. A retried/duplicated request (double-click, network retry, or overlap with the webhook fix in #3) can create two `Order` rows for a single payment.

**Fix direction:** add a unique constraint on `razorpay_payment_id` (nullable, so it doesn't affect non-Razorpay orders), and have `checkout_verify_payment` check for an existing order with that payment ID first and short-circuit if found.

**Status:** Fixed (2026-08-09), superseded by the issue #3 rework. There's now exactly one `Order` row per `razorpay_order_id` by construction - it's created once, up front, by `checkout_create_payment` (status `'Payment Pending'`), not by whichever of the browser callback / webhook happens to finalize it. Both `checkout_verify_payment` and `razorpay_webhook` look that same row up, lock it with `select_for_update()` inside a transaction, and call the shared `_finalize_paid_order()`, which checks `order.status == 'Order Placed'` before doing anything - so no matter how many times or how close together the two finalize paths fire, only the first one actually decrements stock / sends emails; the rest are no-ops. This is a DB-level guarantee (via the row lock), not just an application-level check, so the race noted below is closed.
