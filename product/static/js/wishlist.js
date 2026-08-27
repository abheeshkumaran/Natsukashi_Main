// The wishlist lives server-side (per account), same as the cart - every
// browser/device the same user logs into sees the same wishlist.
// `wishlistCache` is just an in-memory mirror of the server state used for
// synchronous rendering; it's kept in sync via refreshWishlist() and every
// mutating call below.
let wishlistCache = [];
let wishlistRequestSeq = 0;

function wishlistApiCall(url, data) {
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

function renderAllWishlistUI() {
    updateWishlistBadge();
    renderWishlistDrawer();
    syncWishlistButtons();
}

// Keeps every heart button on the page in sync with the wishlist: filled
// (♥) if the product is in it, outline (♡) otherwise. Never uses color to
// show state - only the glyph itself changes, and only ever on an explicit
// click (never automatically).
function syncWishlistButtons() {
    // Every wishlist-able thing is really the same underlying Product row -
    // 'mund'/'colored'/'saree'/'product' on data-type are just per-page
    // display labels, not distinct item types - so match on id alone rather
    // than also requiring the type to line up.
    const list = getWishlist();
    document.querySelectorAll('.js-wishlist-btn').forEach((btn) => {
        const active = list.some((item) => item.id === btn.dataset.id);
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        btn.title = active ? 'Remove from Wishlist' : 'Add to Wishlist';
        if (btn.classList.contains('wishlist-heart-btn')) {
            btn.textContent = active ? '♥' : '♡';
        }
    });
}

function updateWishlistBadge() {
    const count = getWishlist().length;
    document.querySelectorAll('.wishlist-count').forEach((el) => {
        el.textContent = count;
        el.style.display = count > 0 ? 'inline-flex' : 'none';
    });
}

function toggleWishlist(btn) {
    if (typeof window.IS_USER_LOGGED_IN !== 'undefined' && !window.IS_USER_LOGGED_IN) {
        if (typeof openAuthModal === 'function') {
            openAuthModal();
            return;
        }
    }
    const id = btn.dataset.id;
    const wasActive = wishlistCache.some((item) => item.id === id);

    // Reflect the change immediately instead of waiting on the network
    // round-trip, then reconcile with the server's response below.
    if (wasActive) {
        wishlistCache = wishlistCache.filter((item) => item.id !== id);
    } else {
        wishlistCache = [...wishlistCache, { id, type: btn.dataset.type || 'product', name: '', price: 0, image: '' }];
    }
    renderAllWishlistUI();

    const requestId = ++wishlistRequestSeq;
    wishlistApiCall('/wishlist/toggle/', { product_id: id }).then((data) => {
        if (requestId !== wishlistRequestSeq) return; // superseded by a later change
        if (data && data.success) {
            applyWishlistResponse(data);
        } else {
            refreshWishlist();
        }
    }).catch(() => {
        if (requestId === wishlistRequestSeq) refreshWishlist();
    });
}

function removeFromWishlist(id, type) {
    wishlistCache = wishlistCache.filter((item) => item.id !== id);
    renderAllWishlistUI();

    const requestId = ++wishlistRequestSeq;
    wishlistApiCall('/wishlist/remove/', { product_id: id }).then((data) => {
        if (requestId !== wishlistRequestSeq) return;
        if (data && data.success) {
            applyWishlistResponse(data);
        } else {
            refreshWishlist();
        }
    }).catch(() => {
        if (requestId === wishlistRequestSeq) refreshWishlist();
    });
}

function moveWishlistItemToCart(id, type) {
    cartApiCall('/cart/add/', { product_id: id }).then((data) => {
        if (typeof applyCartResponse === 'function') applyCartResponse(data);
        removeFromWishlist(id, type);
    });
}

function formatWishlistPrice(amount) {
    return '₹' + amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function openWishlistDrawer() {
    if (typeof closeCartDrawer === 'function') closeCartDrawer();

    const drawer = document.getElementById('wishlistDrawer');
    const overlay = document.getElementById('wishlistOverlay');
    if (!drawer || !overlay) return;
    drawer.classList.add('active');
    overlay.classList.add('active');
}

function closeWishlistDrawer() {
    const drawer = document.getElementById('wishlistDrawer');
    const overlay = document.getElementById('wishlistOverlay');
    if (!drawer || !overlay) return;
    drawer.classList.remove('active');
    overlay.classList.remove('active');
}

function setWishlistText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function renderWishlistDrawer() {
    const itemsEl = document.getElementById('wishlistItems');
    if (!itemsEl) return;

    const wishlist = getWishlist();
    const emptyEl = document.getElementById('wishlistEmpty');

    setWishlistText('wishlistItemCount', wishlist.length);

    if (wishlist.length === 0) {
        itemsEl.innerHTML = '';
        if (emptyEl) emptyEl.style.display = 'block';
        return;
    }

    if (emptyEl) emptyEl.style.display = 'none';

    itemsEl.innerHTML = wishlist.map((item) => {
        const mrp = (item.fake_price && item.fake_price > item.price) ? item.fake_price : item.price;
        const hasOff = mrp > item.price;
        const offPercent = hasOff ? Math.round((1 - item.price / mrp) * 100) : 0;
        return `
        <div class="cart-row">
            <img src="${item.image}" alt="${item.name}" class="cart-item-img">
            <div class="cart-item-info">
                <h6 class="item-name">${item.name}</h6>
                <div class="price-block">
                    <span class="item-price">${formatWishlistPrice(item.price)}</span>
                    ${hasOff ? `<span class="item-mrp">${formatWishlistPrice(mrp)}</span><span class="item-off">${offPercent}% off</span>` : ''}
                </div>
                <div class="item-actions">
                    <a href="javascript:void(0)" class="item-action-btn item-action-move" onclick="moveWishlistItemToCart('${item.id}','${item.type}')">MOVE TO CART</a>
                    <a href="javascript:void(0)" class="item-action-btn item-action-remove" onclick="removeFromWishlist('${item.id}','${item.type}')">REMOVE</a>
                </div>
            </div>
        </div>
    `;
    }).join('');
}

document.addEventListener('DOMContentLoaded', () => {
    refreshWishlist();

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeWishlistDrawer();
    });
});

// iOS/Safari can restore a page from its back-forward cache without firing
// DOMContentLoaded again, leaving heart icons showing whatever state they
// were in when the page was frozen. Force a fresh fetch on bfcache restore.
window.addEventListener('pageshow', (e) => {
    if (e.persisted) refreshWishlist();
});
