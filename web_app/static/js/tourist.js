/* ============================================
   Phuket Buddy Shop — Tourist Logic
   Simplified & Streamlined for Travelers
   ============================================ */

const tg = window.Telegram.WebApp;

// Global State
let allProducts = [];
let cart = [];
let activeCategory = 'all';

// ===== INIT =====
async function initializeApp() {
    tg.ready();
    tg.expand();
    
    // Set theme color to ocean blue
    try { 
        tg.setHeaderColor('#0077b6');
        tg.setBackgroundColor('#f8f9fa');
    } catch(e) {}

    try {
        await loadProducts();
    } catch (e) {
        console.error('Init failed:', e);
    }

    // Hide loader
    const loader = document.getElementById('loader-overlay');
    if (loader) {
        loader.style.opacity = '0';
        setTimeout(() => loader.style.display = 'none', 500);
    }
}

// ===== API =====
async function apiRequest(endpoint, options = {}) {
    const initData = tg.initData || '';
    const authToken = new URLSearchParams(window.location.search).get('token');
    
    const qp = new URLSearchParams();
    if (initData) qp.append('init_data', initData); // Matches backend expected param
    if (authToken) qp.append('token', authToken);

    let url = endpoint;
    const urlObj = new URL(endpoint, window.location.origin);
    qp.forEach((v, k) => urlObj.searchParams.append(k, v));
    url = urlObj.toString();

    if (options.method === 'POST') {
        const body = options.body || {};
        options.body = JSON.stringify(body);
        options.headers = { ...options.headers, 'Content-Type': 'application/json' };
    }

    const resp = await fetch(url, options);
    const json = await resp.json();
    if (!resp.ok) throw new Error(json.message || `HTTP ${resp.status}`);
    return json;
}

// ===== PRODUCTS =====
async function loadProducts() {
    try {
        const result = await apiRequest('/api/products/active');
        if (result.status === 'success') {
            allProducts = result.data;
            buildCategoryPills();
            renderProducts();
        }
    } catch (e) {
        console.error('Products error:', e);
    }
}

function buildCategoryPills() {
    const container = document.getElementById('category-pills');
    if (!container) return;
    
    const cats = [...new Set(allProducts.map(p => p.category || 'Other'))];
    console.log("Categories found:", cats);
    
    // Sort logic to match POS or prioritize common tourist items
    const order = ['Bar', 'Rental', 'Repellents', 'Clothing', 'Accessories', 'Bags', 'Other'];
    cats.sort((a, b) => {
        let ia = order.findIndex(o => a.toLowerCase().includes(o.toLowerCase()));
        let ib = order.findIndex(o => b.toLowerCase().includes(o.toLowerCase()));
        if (ia === -1) ia = 99;
        if (ib === -1) ib = 99;
        return ia - ib;
    });

    cats.forEach(cat => {
        const chip = document.createElement('div');
        chip.className = 'cat-chip';
        chip.dataset.cat = cat;
        
        const icon = getIconClassForCategory(cat);
        chip.innerHTML = `<i class="${icon}"></i> ${cat}`;
        
        // Use addEventListener for better reliability
        chip.addEventListener('click', function(e) {
            console.log("Category clicked:", cat);
            filterCategory(cat, this);
        });
        
        container.appendChild(chip);
    });
}

window.filterCategory = function(cat, el) {
    activeCategory = cat;
    document.querySelectorAll('.cat-chip').forEach(p => p.classList.remove('active'));
    if (el) el.classList.add('active');
    
    document.getElementById('current-cat-title').innerText = cat === 'all' ? 'Popular Items' : cat;
    renderProducts();
    try { tg.HapticFeedback.selectionChanged(); } catch(e) {}
};

function renderProducts() {
    const grid = document.getElementById('product-grid');
    grid.innerHTML = '';

    const filtered = activeCategory === 'all'
        ? allProducts
        : allProducts.filter(p => (p.category || 'Other') === activeCategory);

    filtered.forEach(p => {
        const card = document.createElement('div');
        card.className = 'product-card';
        card.id = `prod-${p.id}`;
        
        const iconInfo = getIconForCategory(p.category);
        
        card.innerHTML = `
            <div class="p-image-wrap">
                ${iconInfo.type === 'img' 
                    ? `<img src="${iconInfo.val}" style="width:50%; aspect-ratio:1; object-fit:contain;">`
                    : `<i class="${iconInfo.val}"></i>`
                }
            </div>
            <div class="p-name">${p.name}</div>
            <div class="p-cat">${p.category || 'Travel Essential'}</div>
            <div class="p-footer">
                <div class="p-price">${p.sale_price}฿</div>
                <button class="add-btn" onclick="addToCart(${JSON.stringify(p).replace(/"/g, '&quot;')})">
                    <i class="fas fa-plus"></i>
                </button>
            </div>
        `;
        grid.appendChild(card);
    });
}

function getIconForCategory(cat) {
    if (!cat) return { type: 'icon', val: 'fas fa-box' };
    const c = cat.toLowerCase();
    if (c.includes('bar') || c.includes('drink')) return { type: 'img', val: '/static/img/drink.png' };
    if (c.includes('rental')) return { type: 'img', val: '/static/img/rental.png' };
    if (c.includes('repellent')) return { type: 'icon', val: 'fas fa-spray-can' };
    if (c.includes('clothing') || c.includes('apparel')) return { type: 'img', val: '/static/img/clothing.png' };
    if (c.includes('bag') || c.includes('storage')) return { type: 'img', val: '/static/img/bag.png' };
    if (c.includes('access')) return { type: 'icon', val: 'fas fa-glasses' };
    return { type: 'icon', val: 'fas fa-umbrella-beach' };
}

function getIconClassForCategory(cat) {
    // Only used for category pills
    const info = getIconForCategory(cat);
    if (info.type === 'img') {
        if (cat.toLowerCase().includes('bar')) return 'fas fa-cocktail';
        if (cat.toLowerCase().includes('rental')) return 'fas fa-swimmer';
        if (cat.toLowerCase().includes('clothing')) return 'fas fa-tshirt';
        if (cat.toLowerCase().includes('bag')) return 'fas fa-shopping-bag';
    }
    return info.val;
}

// ===== CART =====
window.addToCart = function(product) {
    const existing = cart.find(i => i.id === product.id);
    if (existing) existing.quantity++;
    else cart.push({ ...product, quantity: 1 });

    updateCartUI();

    // Visual feedback
    const el = document.getElementById(`prod-${product.id}`);
    if (el) {
        el.classList.add('pulse');
        setTimeout(() => el.classList.remove('pulse'), 350);
    }
    try { tg.HapticFeedback.impactOccurred('medium'); } catch(e) {}
};

function updateCartUI() {
    const total = cart.reduce((s, i) => s + i.sale_price * i.quantity, 0);
    const count = cart.reduce((s, i) => s + i.quantity, 0);
    const hasItems = cart.length > 0;

    document.getElementById('cart-count-badge').innerText = count;
    document.getElementById('cart-total-display').innerText = `${total.toLocaleString()}฿`;
    document.getElementById('modal-total').innerText = `${total.toLocaleString()}฿`;

    document.getElementById('bottom-bar').style.display = hasItems ? 'flex' : 'none';
}

window.openCart = function() {
    renderCartList();
    document.getElementById('cart-modal').classList.add('active');
    try { tg.HapticFeedback.impactOccurred('light'); } catch(e) {}
};

window.closeCart = function() {
    document.getElementById('cart-modal').classList.remove('active');
};

function renderCartList() {
    const list = document.getElementById('cart-items-list');
    if (!list) return;
    
    if (cart.length === 0) {
        list.innerHTML = '<div style="text-align:center; padding:40px; color:#999;">Your cart is empty</div>';
        return;
    }

    list.innerHTML = cart.map(item => `
        <div class="cart-item">
            <div class="ci-main">
                <div class="ci-name">${item.name}</div>
                <div class="ci-price">${item.sale_price}฿ each</div>
            </div>
            <div class="qty-ctrl">
                <button class="q-btn" onclick="updateQty(${item.id}, -1)">−</button>
                <span class="q-val">${item.quantity}</span>
                <button class="q-btn" onclick="updateQty(${item.id}, 1)">+</button>
            </div>
        </div>
    `).join('');
}

window.updateQty = function(id, delta) {
    const item = cart.find(i => i.id === id);
    if (!item) return;
    item.quantity += delta;
    if (item.quantity <= 0) cart = cart.filter(i => i.id !== id);
    
    updateCartUI();
    renderCartList();
    if (cart.length === 0) closeCart();
    try { tg.HapticFeedback.impactOccurred('light'); } catch(e) {}
};

// ===== CHECKOUT =====
window.processCheckout = async function() {
    const payBtn = document.getElementById('pay-btn');
    const originalText = payBtn.innerText;
    payBtn.innerText = 'WAITING FOR QR...';
    payBtn.disabled = true;

    try {
        const payload = {
            items: cart.map(i => ({
                name: i.name,
                quantity: i.quantity,
                price: i.sale_price
            })),
            pier: 'Yamu' // Dedicated accounting for Buddy Shop
        };

        const result = await apiRequest('/api/tourist/checkout', {
            method: 'POST',
            body: payload
        });

        if (result.status === 'success' && (result.pay_url || result.payment_url)) {
            // Open the payment link directly
            tg.openLink(result.pay_url || result.payment_url);
            
            // Show a "Waiting for payment" state or just instruct the user
            tg.showConfirm("Please complete the payment in the browser. Once paid, your order will be confirmed.", (ok) => {
                if (ok) {
                    // Check payment status or just close?
                    // Typically, we'd poll or wait for webhook
                }
            });
            
            // For now, let's just clear cart if they confirmed they paid (though not reliable)
            // Ideally, we'd have a status page
        }
    } catch (e) {
        alert('Checkout error: ' + e.message);
    } finally {
        payBtn.innerText = originalText;
        payBtn.disabled = false;
    }
};

// ===== START =====
initializeApp();
