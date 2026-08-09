// Wishlist: a small heart button in the top-right corner of each product
// card. Deliberately never uses color to show state (that's what caused
// hearts to appear red for products nobody actually wishlisted) - instead
// the glyph itself swaps outline <-> filled, and only ever changes on an
// explicit click. The full list of wishlisted products lives on its own
// page (see wishlist_page view), not a drawer.
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
    syncWishlistButtons();
    updateWishlistBadge();
}

function refreshWishlist() {
    if (typeof window.SITE_USER_ID === 'undefined' || !window.SITE_USER_ID) {
        wishlistCache = [];
        syncWishlistButtons();
        updateWishlistBadge();
        return Promise.resolve();
    }
    return fetch('/wishlist/list/', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then((res) => res.json())
        .then(applyWishlistResponse)
        .catch(() => {
            wishlistCache = [];
            syncWishlistButtons();
            updateWishlistBadge();
        });
}

function isInWishlist(id, type) {
    return getWishlist().some((item) => item.id === id && item.type === type);
}

// Only ever called from an explicit click on the heart button - never
// automatically, never on page load.
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

// Keeps every heart button on the page in sync with the wishlist: filled
// (♥) if the product is in it, outline (♡) if not. No color change ever -
// just the shape/glyph, and only ever updated from a real server response.
function syncWishlistButtons() {
    const list = getWishlist();
    document.querySelectorAll('.js-wishlist-btn').forEach((btn) => {
        const active = list.some((item) => item.id === btn.dataset.id && item.type === btn.dataset.type);
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        btn.title = active ? 'Remove from Wishlist' : 'Add to Wishlist';
        // Plain product-card hearts are just a text glyph; the product
        // detail popup's heart is an SVG icon whose fill is handled by CSS
        // off the .active class instead (see _product_modal_include.html).
        if (btn.classList.contains('wishlist-heart-btn')) {
            btn.textContent = active ? '♥' : '♡';
        }
    });
}

function updateWishlistBadge() {
    const count = getWishlist().length;
    document.querySelectorAll('.wishlist-count').forEach((el) => {
        el.textContent = count;
        el.style.display = count > 0 ? 'inline-block' : 'none';
    });
}

document.addEventListener('DOMContentLoaded', () => {
    refreshWishlist();
});

// iOS/Safari can restore a page from its back-forward cache without firing
// DOMContentLoaded again, leaving heart icons showing whatever state they
// were in when the page was frozen. Force a fresh fetch on bfcache restore.
window.addEventListener('pageshow', (e) => {
    if (e.persisted) refreshWishlist();
});
