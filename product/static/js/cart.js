// Simple client-side cart stored in localStorage. No backend cart model needed.
const CART_KEY = 'natsukashi_cart';
// Decorative MRP markup so the price-details section can show a "discount",
// matching the same fake-MRP convention already used on the product detail page.
const FAKE_MRP_MARKUP = 500;

function getCart() {
    const cart = JSON.parse(localStorage.getItem(CART_KEY) || '[]');
    // Backfill items saved by an older version of the cart that stored an
    // "images" array + "imgIndex" instead of a single "image" field.
    cart.forEach((item) => {
        if (!item.image && Array.isArray(item.images)) {
            item.image = item.images[item.imgIndex || 0] || item.images[0];
        }
    });
    return cart;
}

function saveCart(cart) {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
    updateCartBadge();
    renderCartDrawer();
    syncAddToCartButtons();
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
        if (btn.dataset.outOfStock === 'true') {
            btn.disabled = true;
            btn.textContent = btn.dataset.defaultLabel;
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
        el.style.display = count > 0 ? 'inline-block' : 'none';
    });
}

function addToCart(btn) {
    const cart = getCart();
    const existing = cart.find((item) => item.id === btn.dataset.id && item.type === btn.dataset.type);
    if (existing) {
        btn.disabled = false;
        btn.textContent = 'Go to Cart';
        syncAddToCartButtons();
        openCartDrawer();
        return;
    }

    const newItem = {
        id: btn.dataset.id,
        type: btn.dataset.type,
        name: btn.dataset.name,
        price: parseFloat(btn.dataset.price),
        image: btn.dataset.image,
        qty: 1,
    };

    cart.push(newItem);
    saveCart(cart);
    btn.disabled = false;
    btn.textContent = 'Go to Cart';
    // Do not open the cart drawer immediately after adding.
    // The drawer should open only when the user clicks the "Go to Cart" button.
}

function changeQty(id, type, delta) {
    let cart = getCart();
    const item = cart.find((i) => i.id === id && i.type === type);
    if (!item) return;
    item.qty += delta;
    if (item.qty <= 0) {
        cart = cart.filter((i) => !(i.id === id && i.type === type));
    }
    saveCart(cart);
}

function removeFromCart(id, type) {
    const cart = getCart().filter((i) => !(i.id === id && i.type === type));
    saveCart(cart);
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
    document.body.style.overflow = 'hidden';
}

function closeCartDrawer() {
    const drawer = document.getElementById('cartDrawer');
    const overlay = document.getElementById('cartOverlay');
    if (!drawer || !overlay) return;
    drawer.classList.remove('active');
    overlay.classList.remove('active');
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
        const mrp = item.price + FAKE_MRP_MARKUP;
        const offPercent = Math.round((FAKE_MRP_MARKUP / mrp) * 100);
        return `
        <div class="cart-row">
            <img src="${item.image}" alt="${item.name}" class="cart-item-img">
            <div class="cart-item-info">
                <h6 class="item-name">${item.name}</h6>
                <div class="item-type">${item.type === 'mund' ? 'Onam Set-Mund' : 'Onam Saree'}</div>
                <div class="price-block">
                    <span class="item-price">${formatPrice(item.price)}</span>
                    <span class="item-mrp">${formatPrice(mrp)}</span>
                    <span class="item-off">${offPercent}% off</span>
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
    const totalMrp = cart.reduce((sum, item) => sum + (item.price + FAKE_MRP_MARKUP) * item.qty, 0);
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
        const mrp = item.price + FAKE_MRP_MARKUP;
        const offPercent = Math.round((FAKE_MRP_MARKUP / mrp) * 100);
        return `
        <div class="cart-row">
            <img src="${item.image}" alt="${item.name}" class="cart-item-img">
            <div class="cart-item-info">
                <h6 class="item-name">${item.name}</h6>
                <div class="item-type">${item.type === 'mund' ? 'Onam Set-Mund' : item.type === 'colored' ? 'Colored Saree' : 'Onam Saree'}</div>
                <div class="price-block">
                    <span class="item-price">${formatPrice(item.price)}</span>
                    <span class="item-mrp">${formatPrice(mrp)}</span>
                    <span class="item-off">${offPercent}% off</span>
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
    const totalMrp = cart.reduce((sum, item) => sum + (item.price + FAKE_MRP_MARKUP) * item.qty, 0);
    const totalAmount = cart.reduce((sum, item) => sum + item.price * item.qty, 0);
    const totalDiscount = totalMrp - totalAmount;

    setText('cartPageItemCount', itemCount);
    setText('cartPageMrpTotal', formatPrice(totalMrp));
    setText('cartPageDiscount', '− ' + formatPrice(totalDiscount));
    setText('cartPageTotal', formatPrice(totalAmount));
    setText('cartPageSavings', `You will save ${formatPrice(totalDiscount)} on this order`);
}

document.addEventListener('DOMContentLoaded', () => {
    updateCartBadge();
    renderCartDrawer();
    syncAddToCartButtons();
    renderCartPage();

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeCartDrawer();
    });
});
