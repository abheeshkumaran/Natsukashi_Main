function getWishlistKey() {
    return (typeof window.SITE_USER_ID !== 'undefined' && window.SITE_USER_ID) 
        ? 'natsukashi_wishlist_' + window.SITE_USER_ID 
        : null;
}

function getWishlist() {
    const key = getWishlistKey();
    if (!key) return [];
    return JSON.parse(localStorage.getItem(key) || '[]');
}

function saveWishlist(list) {
    const key = getWishlistKey();
    if (!key) return;
    localStorage.setItem(key, JSON.stringify(list));
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

    const { id, type, name, price, image } = btn.dataset;
    let list = getWishlist();
    const exists = list.some((item) => item.id === id && item.type === type);

    if (exists) {
        list = list.filter((item) => !(item.id === id && item.type === type));
    } else {
        list.push({ id, type, name, price: parseFloat(price), image });
    }

    saveWishlist(list);
}

function removeFromWishlist(id, type) {
    saveWishlist(getWishlist().filter((item) => !(item.id === id && item.type === type)));
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
    if (!item) return;

    if (typeof getCart === 'function' && typeof saveCart === 'function') {
        const cart = getCart();
        if (!cart.some((i) => i.id === id && i.type === type)) {
            cart.push({ id: item.id, type: item.type, name: item.name, price: item.price, image: item.image, qty: 1 });
            saveCart(cart);
        }
    }

    saveWishlist(getWishlist().filter((i) => !(i.id === id && i.type === type)));
    if (typeof openCartDrawer === 'function') openCartDrawer();
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
    return 'FEATURED ONAM PICKS PICKS';
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
                    <a href="javascript:void(0)" onclick="moveWishlistItemToCart('${item.id}','${item.type}')">MOVE TO CART</a>
                    <a href="javascript:void(0)" onclick="removeFromWishlist('${item.id}','${item.type}')">REMOVE</a>
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
    syncWishlistButtons();
    updateWishlistBadge();
    renderWishlistDrawer();

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeWishlistDrawer();
    });
});
