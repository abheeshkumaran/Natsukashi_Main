// The wishlist now lives server-side (per account), so every browser/device
// the same user logs into sees the same wishlist. `wishlistCache` mirrors the
// server state for synchronous rendering.
let wishlistCache = [];

function wishlistApiCall(url, data) {
    return fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': typeof getCsrfToken === 'function' ? getCsrfToken() : '',
            'X-Requested-With': 'XMLHttpRequest',
        },
        body: new URLSearchParams(data || {}),
    }).then((res) => res.json());
}

function getWishlist() {
    return wishlistCache;
}

function applyWishlistResponse(data) {
    if (data && data.success && Array.isArray(data.items)) {
        wishlistCache = data.items;
    }
    renderAllWishlistUI();
}

function refreshWishlist() {
    if (typeof window.SITE_USER_ID === 'undefined' || !window.SITE_USER_ID) {
        wishlistCache = [];
        renderAllWishlistUI();
        return Promise.resolve();
    }
    return fetch('/wishlist/list/', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then((res) => res.json())
        .then(applyWishlistResponse)
        .catch(() => {
            wishlistCache = [];
            renderAllWishlistUI();
        });
}

// One-time migration: carries over any wishlist items saved locally by an
// older, browser-only version so switching to server-sync doesn't wipe what
// someone already had saved.
function migrateLocalWishlistIfNeeded() {
    if (typeof window.SITE_USER_ID === 'undefined' || !window.SITE_USER_ID) {
        return Promise.resolve();
    }
    const legacyKey = 'natsukashi_wishlist_' + window.SITE_USER_ID;
    const migratedKey = 'natsukashi_wishlist_migrated_' + window.SITE_USER_ID;
    if (localStorage.getItem(migratedKey)) {
        return Promise.resolve();
    }
    const raw = localStorage.getItem(legacyKey);
    localStorage.setItem(migratedKey, '1');
    if (!raw) {
        return Promise.resolve();
    }
    let legacyItems = [];
    try {
        legacyItems = JSON.parse(raw);
    } catch (e) {
        legacyItems = [];
    }
    if (!legacyItems.length) {
        return Promise.resolve();
    }
    return wishlistApiCall('/wishlist/merge/', { items: JSON.stringify(legacyItems) }).then((data) => {
        applyWishlistResponse(data);
        localStorage.removeItem(legacyKey);
    });
}

function renderAllWishlistUI() {
    syncWishlistButtons();
    updateWishlistBadge();
    renderWishlistDrawer();
}

function isInWishlist(id, type) {
    return getWishlist().some((item) => item.id === id && item.type === type);
}

function toggleWishlist(btn) {
    if (typeof window.IS_USER_LOGGED_IN !== 'undefined' && !window.IS_USER_LOGGED_IN) {
        if (typeof openAuthModal === 'function') {
            openAuthModal();
            return;
        }
    }

    wishlistApiCall('/wishlist/toggle/', { product_id: btn.dataset.id }).then(applyWishlistResponse);
}

function removeFromWishlist(id, type) {
    wishlistApiCall('/wishlist/remove/', { product_id: id }).then(applyWishlistResponse);
}

// Wishlisted item -> cart, using cart.js's own storage helpers (loaded on
// the same pages), then drops it out of the wishlist and opens the cart.
function moveWishlistItemToCart(id, type) {
    if (typeof window.IS_USER_LOGGED_IN !== 'undefined' && !window.IS_USER_LOGGED_IN) {
        if (typeof openAuthModal === 'function') {
            openAuthModal();
            return;
        }
    }

    const item = getWishlist().find((i) => i.id === id && i.type === type);
    if (!item || item.in_stock === false) return;

    const addPromise = (typeof cartApiCall === 'function' && !getCart().some((i) => i.id === id && i.type === type))
        ? cartApiCall('/cart/add/', { product_id: id }).then(applyCartResponse)
        : Promise.resolve();

    addPromise
        .then(() => wishlistApiCall('/wishlist/remove/', { product_id: id }))
        .then(applyWishlistResponse)
        .then(() => {
            if (typeof openCartDrawer === 'function') openCartDrawer();
        });
}

// Keeps every heart button on the page in sync with the wishlist. Called on
// load and again whenever the product-modal popup swaps in new content.
function syncWishlistButtons() {
    const list = getWishlist();
    document.querySelectorAll('.wishlist-toggle-btn').forEach((btn) => {
        const active = list.some((item) => item.id === btn.dataset.id && item.type === btn.dataset.type);
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        btn.title = active ? 'Remove from Wishlist' : 'Add to Wishlist';
    });
}

function updateWishlistBadge() {
    const count = getWishlist().length;
    document.querySelectorAll('.wishlist-count').forEach((el) => {
        el.textContent = count;
        el.style.display = count > 0 ? 'inline-block' : 'none';
    });
}

function typeLabel(type) {
    if (type === 'mund') return 'SHOP BY COLLECTION';
    if (type === 'colored') return 'MOST PURCHASED SAREE';
    return 'FEATURED ONAM PICKS';
}

function renderWishlistDrawer() {
    const itemsEl = document.getElementById('wishlistItems');
    if (!itemsEl) return;

    const list = getWishlist();
    const emptyEl = document.getElementById('wishlistEmpty');
    const countEl = document.getElementById('wishlistItemCount');
    if (countEl) countEl.textContent = list.length;

    if (list.length === 0) {
        itemsEl.innerHTML = '';
        if (emptyEl) emptyEl.style.display = 'block';
        return;
    }

    if (emptyEl) emptyEl.style.display = 'none';

    itemsEl.innerHTML = list.map((item) => {
        const priceText = typeof formatPrice === 'function' ? formatPrice(item.price) : `₹${item.price}`;
        return `
        <div class="cart-row">
            <img src="${item.image}" alt="${item.name}" class="cart-item-img">
            <div class="cart-item-info">
                <h6 class="item-name">${item.name}</h6>
                <div class="item-type">${typeLabel(item.type)}</div>
                <div class="price-block">
                    <span class="item-price">${priceText}</span>
                </div>
                <div class="item-actions">
                    ${item.in_stock === false
                        ? '<span class="item-action-btn item-action-outofstock">Out of Stock</span>'
                        : `<a href="javascript:void(0)" class="item-action-btn item-action-move" onclick="moveWishlistItemToCart('${item.id}','${item.type}')">MOVE TO CART</a>`
                    }
                    <a href="javascript:void(0)" class="item-action-btn item-action-remove" onclick="removeFromWishlist('${item.id}','${item.type}')">REMOVE</a>
                </div>
            </div>
        </div>
    `;
    }).join('');
}

function openWishlistDrawer() {
    if (typeof closeCartDrawer === 'function') closeCartDrawer();

    const drawer = document.getElementById('wishlistDrawer');
    const overlay = document.getElementById('wishlistOverlay');
    if (!drawer || !overlay) return;
    drawer.classList.add('active');
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeWishlistDrawer() {
    const drawer = document.getElementById('wishlistDrawer');
    const overlay = document.getElementById('wishlistOverlay');
    if (!drawer || !overlay) return;
    drawer.classList.remove('active');
    overlay.classList.remove('active');
    document.body.style.overflow = '';
}

document.addEventListener('DOMContentLoaded', () => {
    migrateLocalWishlistIfNeeded().then(refreshWishlist);

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeWishlistDrawer();
    });
});
