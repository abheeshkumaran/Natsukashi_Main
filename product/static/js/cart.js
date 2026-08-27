// The struck-through "MRP" is now a real per-product value (Product.fake_price),
// sent from the server as item.fake_price. Falls back to the sale price (i.e. no
// discount shown) when a product has no fake price set.
function itemMrp(item) {
    return (item.fake_price && item.fake_price > item.price) ? item.fake_price : item.price;
}

// The cart now lives server-side (per account), so every browser/device the
// same user logs into sees the same cart. `cartCache` is just an in-memory
// mirror of the server state used for synchronous rendering; it's kept in
// sync via refreshCart() and every mutating call below.
let cartCache = [];

function getCsrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
}

function cartApiCall(url, data) {
    return fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
        },
        body: new URLSearchParams(data || {}),
    }).then((res) => res.json());
}

function getCart() {
    return cartCache;
}

function applyCartResponse(data) {
    if (data && data.success && Array.isArray(data.items)) {
        cartCache = data.items;
    }
    renderAllCartUI();
}

function refreshCart() {
    if (typeof window.SITE_USER_ID === 'undefined' || !window.SITE_USER_ID) {
        cartCache = [];
        renderAllCartUI();
        return Promise.resolve();
    }
    return fetch('/cart/list/', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then((res) => res.json())
        .then(applyCartResponse)
        .catch(() => {
            cartCache = [];
            renderAllCartUI();
        });
}

function renderAllCartUI() {
    updateCartBadge();
    renderCartDrawer();
    syncAddToCartButtons();
    if (typeof renderCartPage === 'function') renderCartPage();
}

// Keeps every "Add to Cart" button on the page in sync with the cart: disabled
// (and re-labelled) while the product is already carted, enabled otherwise.
// Buttons that are out of stock stay disabled no matter what.
function syncAddToCartButtons() {
    const cart = getCart();
    document.querySelectorAll('.cart-toggle-btn').forEach((btn) => {
        if (!btn.dataset.defaultLabel) {
            btn.dataset.defaultLabel = btn.textContent.trim() || 'Add to Cart';
        }
        if (btn.dataset.outOfStock === 'true' || btn.disabled || !btn.dataset.id) {
            // Already rendered as permanently disabled (out of stock) server-side,
            // or missing the data it needs to function - never re-enable it here.
            return;
        }
        const inCart = cart.some((item) => item.id === btn.dataset.id && item.type === btn.dataset.type);
        btn.disabled = false;
        btn.textContent = inCart ? 'Go to Cart' : (btn.dataset.defaultLabel || 'Add to Cart');
    });
}

function updateCartBadge() {
    const count = getCart().reduce((sum, item) => sum + item.qty, 0);
    document.querySelectorAll('.cart-count').forEach((el) => {
        el.textContent = count;
        el.style.display = count > 0 ? 'inline-flex' : 'none';
    });
}

function addToCart(btn) {
    if (typeof window.IS_USER_LOGGED_IN !== 'undefined' && !window.IS_USER_LOGGED_IN) {
        if (typeof openAuthModal === 'function') {
            openAuthModal();
            return;
        }
    }

    const existing = getCart().find((item) => item.id === btn.dataset.id && item.type === btn.dataset.type);
    if (existing) {
        btn.disabled = false;
        btn.textContent = 'Go to Cart';
        syncAddToCartButtons();
        openCartDrawer();
        return;
    }

    btn.disabled = true;
    cartApiCall('/cart/add/', { product_id: btn.dataset.id }).then((data) => {
        applyCartResponse(data);
        btn.disabled = false;
        btn.textContent = 'Go to Cart';
        // Open the drawer right away so the add is visibly confirmed -
        // requiring a second click on "Go to Cart" to actually see the
        // cart was repeatedly reported as "cart not visible after adding".
        openCartDrawer();
    });
}

let cartRequestSeq = 0;

function changeQty(id, type, delta) {
    const item = getCart().find((i) => i.id === id && i.type === type);
    if (!item) return;
    const newQty = item.qty + delta;

    // Reflect the change immediately instead of waiting on the network
    // round-trip, then reconcile with the server's response below.
    if (newQty <= 0) {
        cartCache = cartCache.filter((i) => !(i.id === id && i.type === type));
    } else {
        item.qty = newQty;
    }
    renderAllCartUI();

    const requestId = ++cartRequestSeq;
    cartApiCall('/cart/update/', { product_id: id, qty: newQty }).then((data) => {
        if (requestId !== cartRequestSeq) return; // superseded by a later change
        if (data && data.success) {
            applyCartResponse(data);
        } else {
            refreshCart();
        }
    }).catch(() => {
        if (requestId === cartRequestSeq) refreshCart();
    });
}

function removeFromCart(id, type) {
    cartApiCall('/cart/remove/', { product_id: id }).then(applyCartResponse);
}

function formatPrice(amount) {
    return '₹' + amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function openCartDrawer() {
    if (typeof closeWishlistDrawer === 'function') closeWishlistDrawer();

    const drawer = document.getElementById('cartDrawer');
    const overlay = document.getElementById('cartOverlay');
    if (!drawer || !overlay) return;
    drawer.classList.add('active');
    overlay.classList.add('active');
}

function closeCartDrawer() {
    const drawer = document.getElementById('cartDrawer');
    const overlay = document.getElementById('cartOverlay');
    if (!drawer || !overlay) return;
    drawer.classList.remove('active');
    overlay.classList.remove('active');
    // Always reset in case a stale inline style survived from before this
    // lock was removed (e.g. a page restored from iOS Safari's bfcache).
    document.body.style.overflow = '';
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function renderCartDrawer() {
    const itemsEl = document.getElementById('cartItems');
    if (!itemsEl) return;

    const cart = getCart();
    const emptyEl = document.getElementById('cartEmpty');
    const summaryEl = document.getElementById('cartSummary');

    setText('cartItemCount', cart.reduce((sum, item) => sum + item.qty, 0));

    if (cart.length === 0) {
        itemsEl.innerHTML = '';
        if (emptyEl) emptyEl.style.display = 'block';
        if (summaryEl) summaryEl.style.display = 'none';
        return;
    }

    if (emptyEl) emptyEl.style.display = 'none';
    if (summaryEl) summaryEl.style.display = 'block';

    // Section 1: cart items
    itemsEl.innerHTML = cart.map((item) => {
        const mrp = itemMrp(item);
        const hasOff = mrp > item.price;
        const offPercent = hasOff ? Math.round((1 - item.price / mrp) * 100) : 0;
        return `
        <div class="cart-row">
            <img src="${item.image}" alt="${item.name}" class="cart-item-img">
            <div class="cart-item-info">
                <h6 class="item-name">${item.name}</h6>
                <div class="item-type">${item.type === 'mund' ? 'SHOP BY COLLECTION' : 'FEATURED ONAM PICKS'}</div>
                <div class="price-block">
                    <span class="item-price">${formatPrice(item.price)}</span>
                    ${hasOff ? `<span class="item-mrp">${formatPrice(mrp)}</span><span class="item-off">${offPercent}% off</span>` : ''}
                </div>
                <div class="qty-stepper">
                    <button onclick="changeQty('${item.id}','${item.type}',-1)">−</button>
                    <span>${item.qty}</span>
                    <button onclick="changeQty('${item.id}','${item.type}',1)">+</button>
                </div>
                <div class="item-actions">
                    <a href="javascript:void(0)" onclick="removeFromCart('${item.id}','${item.type}')">REMOVE</a>
                </div>
            </div>
        </div>
    `;
    }).join('');

    // Section 2: price details
    const itemCount = cart.reduce((sum, item) => sum + item.qty, 0);
    const totalMrp = cart.reduce((sum, item) => sum + itemMrp(item) * item.qty, 0);
    const totalAmount = cart.reduce((sum, item) => sum + item.price * item.qty, 0);
    const totalDiscount = totalMrp - totalAmount;

    setText('summaryItemCount', itemCount);
    setText('cartMrpTotal', formatPrice(totalMrp));
    setText('cartDiscount', '− ' + formatPrice(totalDiscount));
    setText('cartTotal', formatPrice(totalAmount));
    setText('savingsMsg', `You will save ${formatPrice(totalDiscount)} on this order`);
}

function renderCartPage() {
    const itemsEl = document.getElementById('cartPageItems');
    if (!itemsEl) return;

    const cart = getCart();
    const summaryEl = document.getElementById('cartPageSummary');
    const emptyEl = document.getElementById('cartPageEmpty');

    if (cart.length === 0) {
        itemsEl.innerHTML = '';
        if (emptyEl) emptyEl.style.display = 'block';
        if (summaryEl) summaryEl.style.display = 'none';
        return;
    }

    if (emptyEl) emptyEl.style.display = 'none';
    if (summaryEl) summaryEl.style.display = 'block';

    itemsEl.innerHTML = cart.map((item) => {
        const mrp = itemMrp(item);
        const hasOff = mrp > item.price;
        const offPercent = hasOff ? Math.round((1 - item.price / mrp) * 100) : 0;
        return `
        <div class="cart-row">
            <img src="${item.image}" alt="${item.name}" class="cart-item-img">
            <div class="cart-item-info">
                <h6 class="item-name">${item.name}</h6>
                <div class="item-type">${item.type === 'mund' ? 'SHOP BY COLLECTION' : item.type === 'colored' ? 'MOST PURCHASED SAREE' : 'FEATURED ONAM PICKS'}</div>
                <div class="price-block">
                    <span class="item-price">${formatPrice(item.price)}</span>
                    ${hasOff ? `<span class="item-mrp">${formatPrice(mrp)}</span><span class="item-off">${offPercent}% off</span>` : ''}
                </div>
                <div class="qty-stepper">
                    <button onclick="changeQty('${item.id}','${item.type}',-1)">−</button>
                    <span>${item.qty}</span>
                    <button onclick="changeQty('${item.id}','${item.type}',1)">+</button>
                </div>
                <div class="item-actions">
                    <a href="javascript:void(0)" onclick="removeFromCart('${item.id}','${item.type}')">REMOVE</a>
                </div>
            </div>
        </div>
    `;
    }).join('');

    const itemCount = cart.reduce((sum, item) => sum + item.qty, 0);
    const totalMrp = cart.reduce((sum, item) => sum + itemMrp(item) * item.qty, 0);
    const totalAmount = cart.reduce((sum, item) => sum + item.price * item.qty, 0);
    const totalDiscount = totalMrp - totalAmount;

    setText('cartPageItemCount', itemCount);
    setText('cartPageMrpTotal', formatPrice(totalMrp));
    setText('cartPageDiscount', '− ' + formatPrice(totalDiscount));
    setText('cartPageTotal', formatPrice(totalAmount));
    setText('cartPageSavings', `You will save ${formatPrice(totalDiscount)} on this order`);
}

document.addEventListener('DOMContentLoaded', () => {
    refreshCart();

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeCartDrawer();
    });
});

// iOS/Safari can restore a page from its back-forward cache without firing
// DOMContentLoaded again, leaving "Add to Cart" buttons showing whatever
// state they were in when the page was frozen (stale, or wrong entirely
// after switching accounts). Force a fresh fetch on bfcache restore.
window.addEventListener('pageshow', (e) => {
    if (e.persisted) refreshCart();
});
