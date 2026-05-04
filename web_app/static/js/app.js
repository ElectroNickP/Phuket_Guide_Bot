/* ============================================
   POS v2.0 — Professional Point-of-Sale Logic
   ============================================ */

const tg = window.Telegram.WebApp;

// Global State
let currentPier = new URLSearchParams(window.location.search).get('pier');
const authToken = new URLSearchParams(window.location.search).get('token');
let currentSession = null;
let allProducts = [];
let cart = [];
let activeCategory = 'all';

// ===== INIT =====
async function initializeApp() {
    tg.ready();
    tg.expand();

    try {
        const result = await apiRequest('/api/init');
        if (result.status === 'success') {
            const user = result.data;
            currentPier = currentPier || user.pier;
            
            document.getElementById('greeting').innerText = `${currentPier || 'Pier'} POS`;
            
            const phuketDate = new Date().toLocaleDateString('en-GB', { timeZone: 'Asia/Bangkok' });
            document.getElementById('date-display').innerText = `${phuketDate} • ${user.name}`;

            await Promise.all([
                refreshSessionStatus(),
                loadProducts(),
                loadSeaPlan(),
            ]);
        }
    } catch (e) {
        console.error('Init failed:', e);
    }

    // Hide loader
    const loader = document.getElementById('loader-overlay');
    if (loader) {
        loader.classList.add('hide');
        setTimeout(() => loader.style.display = 'none', 400);
    }
}

// ===== API =====
async function apiRequest(endpoint, options = {}) {
    const initData = tg.initData || '';
    const qp = new URLSearchParams();
    if (initData) qp.append('initData', initData);
    if (authToken) qp.append('token', authToken);

    let url = endpoint;

    if (options.method === 'POST') {
        const body = options.body || {};
        if (initData) body.initData = initData;
        if (authToken) body.token = authToken;
        options.body = JSON.stringify(body);
        options.headers = { 'Content-Type': 'application/json' };
    } else {
        // GET — append params to URL
        const urlObj = new URL(endpoint, window.location.origin);
        qp.forEach((v, k) => urlObj.searchParams.append(k, v));
        // Also append any extra data from options
        if (options.data) {
            Object.entries(options.data).forEach(([k, v]) => urlObj.searchParams.append(k, v));
        }
        url = urlObj.toString();
        delete options.data;
    }

    const resp = await fetch(url, options);
    const json = await resp.json();
    if (!resp.ok) throw new Error(json.message || `HTTP ${resp.status}`);
    return json;
}

// ===== TABS =====
window.switchTab = function(name) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    
    document.getElementById(`tab-btn-${name}`).classList.add('active');
    document.getElementById(`panel-${name}`).classList.add('active');
    
    if (name === 'report') loadReport();
    try { tg.HapticFeedback.selectionChanged(); } catch(e) {}
};

// ===== SESSION MANAGEMENT =====
async function refreshSessionStatus() {
    if (!currentPier) return;
    try {
        const result = await apiRequest('/api/pier/session', { data: { pier: currentPier } });
        if (result.status !== 'success') return;
        
        const data = result.data;
        currentSession = data.active ? data : null;
        
        const badge = document.getElementById('session-badge');
        const openBtn = document.getElementById('session-controls');
        const activeCtrl = document.getElementById('session-active-controls');
        const posTabBtn = document.getElementById('tab-btn-pos');

        if (currentSession) {
            badge.textContent = 'OPEN';
            badge.classList.remove('closed');
            openBtn.style.display = 'none';
            activeCtrl.style.display = 'block';
            posTabBtn.style.opacity = '1';
            posTabBtn.style.pointerEvents = 'auto';
        } else {
            badge.textContent = 'CLOSED';
            badge.classList.add('closed');
            openBtn.style.display = 'block';
            activeCtrl.style.display = 'none';
            posTabBtn.style.opacity = '0.4';
            posTabBtn.style.pointerEvents = 'none';
            switchTab('schedule');
        }

        // Update KPIs
        if (data.report) {
            const r = data.report;
            document.getElementById('kpi-revenue').textContent = `${r.total_amount.toLocaleString()}฿`;
            document.getElementById('kpi-txns').textContent = r.sales_count;
            document.getElementById('kpi-cash').textContent = `${r.cash_amount.toLocaleString()}฿`;
            document.getElementById('kpi-online').textContent = `${r.online_amount.toLocaleString()}฿`;
        }
    } catch (e) {
        console.error('Session refresh failed:', e);
    }
}

window.toggleSession = async function() {
    const action = currentSession ? 'close' : 'open';
    const msg = action === 'close'
        ? 'Close shift and finalize report?'
        : 'Open a new session for this pier?';

    const proceed = await confirmDialog(msg);
    if (!proceed) return;

    try {
        const body = { pier: currentPier };
        if (action === 'close') body.session_id = currentSession.id;
        
        const result = await apiRequest(`/api/pier/session/${action}`, { method: 'POST', body });
        if (result.status === 'success') {
            showSuccess(action === 'open' ? 'Session Opened!' : 'Session Closed!');
            try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
            await refreshSessionStatus();
            if (action === 'open') {
                await loadProducts();
                switchTab('pos');
            }
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
};

// ===== SEA PLAN =====
async function loadSeaPlan() {
    try {
        const result = await apiRequest('/api/schedule');
        const container = document.getElementById('boat-list');
        if (!container) return;
        container.innerHTML = '';

        if (result.status === 'success' && result.data?.length > 0) {
            result.data.forEach(plan => {
                const card = document.createElement('div');
                card.className = 'schedule-card';
                card.innerHTML = `
                    <div class="sc-header">
                        <span class="sc-boat">${plan.boat || '🚐 Land'}</span>
                        <span class="sc-pax">${plan.pax} PAX</span>
                    </div>
                    <div class="sc-row">
                        <span>🏷️ ${plan.program}</span>
                        <span>⏰ ${plan.pickup_time || '--:--'}</span>
                    </div>
                `;
                container.appendChild(card);
            });
        } else {
            container.innerHTML = '<p style="text-align:center; color:var(--text-muted); padding:30px; font-size:13px;">No boats scheduled for today</p>';
        }
    } catch (e) {
        console.error('Sea plan error:', e);
    }
}

// ===== PRODUCTS =====
async function loadProducts() {
    try {
        const result = await apiRequest('/api/pier/products');
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
    container.innerHTML = '';

    // "All" pill
    const allPill = document.createElement('button');
    allPill.className = 'cat-pill active';
    allPill.textContent = 'All';
    allPill.onclick = () => filterCategory('all', allPill);
    container.appendChild(allPill);

    // Unique categories
    const cats = [...new Set(allProducts.map(p => p.category || 'Other'))];
    const order = ['BAR', 'Bar', 'Rental', 'Repellents', 'Clothing (Apparels)', 'Accessories', 'Bags & Storage', 'Other'];
    cats.sort((a, b) => {
        let ia = order.findIndex(o => a.toLowerCase().includes(o.toLowerCase()));
        let ib = order.findIndex(o => b.toLowerCase().includes(o.toLowerCase()));
        if (ia === -1) ia = 99;
        if (ib === -1) ib = 99;
        return ia - ib;
    });

    cats.forEach(cat => {
        const pill = document.createElement('button');
        pill.className = 'cat-pill';
        pill.textContent = cat;
        pill.onclick = () => filterCategory(cat, pill);
        container.appendChild(pill);
    });
}

window.filterCategory = function(cat, el) {
    activeCategory = cat;
    document.querySelectorAll('.cat-pill').forEach(p => p.classList.remove('active'));
    if (el) el.classList.add('active');
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
        
        const accentColor = getCatColor(p.category);
        const icon = getIconForCategory(p.category);
        
        card.innerHTML = `
            <div class="cat-accent" style="background:${accentColor}"></div>
            <img src="${icon}" class="p-icon" alt="">
            <div class="p-name">${p.name}</div>
            <div class="p-price">${p.sale_price}฿</div>
        `;
        card.onclick = () => addToCart(p);
        grid.appendChild(card);
    });
}

function getCatColor(cat) {
    if (!cat) return 'var(--cat-other)';
    const c = cat.toLowerCase();
    if (c.includes('bar')) return 'var(--cat-bar)';
    if (c.includes('rental')) return 'var(--cat-rental)';
    if (c.includes('repellent')) return 'var(--cat-repellent)';
    if (c.includes('clothing') || c.includes('apparel')) return 'var(--cat-clothing)';
    if (c.includes('access')) return 'var(--cat-accessories)';
    if (c.includes('bag') || c.includes('storage')) return 'var(--cat-bags)';
    return 'var(--cat-other)';
}

function getIconForCategory(cat) {
    if (!cat) return '/static/img/logo.png';
    const c = cat.toLowerCase();
    if (c.includes('bar')) return '/static/img/drink.png';
    if (c.includes('rental')) return '/static/img/rental.png';
    if (c.includes('clothing') || c.includes('apparel')) return '/static/img/clothing.png';
    if (c.includes('bag') || c.includes('storage')) return '/static/img/bag.png';
    return '/static/img/logo.png';
}

// ===== CART =====
function addToCart(product) {
    const existing = cart.find(i => i.id === product.id);
    if (existing) existing.quantity++;
    else cart.push({ ...product, quantity: 1 });

    renderCart();

    // Visual feedback
    const el = document.getElementById(`prod-${product.id}`);
    if (el) {
        el.classList.add('pulse');
        setTimeout(() => el.classList.remove('pulse'), 350);
    }
    try { tg.HapticFeedback.impactOccurred('light'); } catch(e) {}
}

function renderCart() {
    const total = cart.reduce((s, i) => s + i.sale_price * i.quantity, 0);
    const hasItems = cart.length > 0;

    // Desktop cart sidebar
    const cartEl = document.getElementById('cart-items');
    if (cartEl) {
        if (!hasItems) {
            cartEl.innerHTML = '<div class="cart-empty">Tap a product to add it</div>';
        } else {
            cartEl.innerHTML = cart.map(item => `
                <div class="cart-item">
                    <div class="ci-info">
                        <div class="ci-name">${item.name}</div>
                        <div class="ci-price">${item.sale_price}฿ × ${item.quantity}</div>
                    </div>
                    <div class="ci-controls">
                        <button class="qty-btn minus" onclick="updateQty(${item.id}, -1)">−</button>
                        <span class="ci-qty">${item.quantity}</span>
                        <button class="qty-btn" onclick="updateQty(${item.id}, 1)">+</button>
                    </div>
                </div>
            `).join('');
        }
    }

    document.getElementById('cart-total').textContent = `${total.toLocaleString()}฿`;

    // Enable/disable pay buttons
    document.getElementById('btn-pay-cash').disabled = !hasItems;
    document.getElementById('btn-pay-online').disabled = !hasItems;

    // Mobile cart bar
    const mobileBar = document.getElementById('mobile-cart-bar');
    if (mobileBar) {
        document.getElementById('mcb-total').textContent = `${total.toLocaleString()}฿`;
        mobileBar.classList.toggle('active', hasItems);
    }
}

window.updateQty = function(id, delta) {
    const item = cart.find(i => i.id === id);
    if (!item) return;
    item.quantity += delta;
    if (item.quantity <= 0) cart = cart.filter(i => i.id !== id);
    renderCart();
    try { tg.HapticFeedback.impactOccurred('light'); } catch(e) {}
};

window.clearCart = function() {
    cart = [];
    renderCart();
};

// ===== MOBILE CART SHEET =====
window.openMobileCart = function() {
    const sheet = document.getElementById('sheet-overlay');
    const mobileItems = document.getElementById('mobile-cart-items');
    
    mobileItems.innerHTML = cart.map(item => `
        <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 0; border-bottom:1px solid #f0f0f0;">
            <div>
                <div style="font-weight:600;">${item.name}</div>
                <div style="font-size:12px; color:var(--text-muted);">${item.sale_price}฿ × ${item.quantity}</div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <button class="qty-btn minus" onclick="updateQty(${item.id}, -1); openMobileCart();">−</button>
                <span style="font-weight:800;">${item.quantity}</span>
                <button class="qty-btn" onclick="updateQty(${item.id}, 1); openMobileCart();">+</button>
            </div>
        </div>
    `).join('');

    document.getElementById('mobile-cart-total').textContent = 
        `${cart.reduce((s, i) => s + i.sale_price * i.quantity, 0).toLocaleString()}฿`;
    
    sheet.classList.add('active');
};

window.closeMobileCart = function() {
    document.getElementById('sheet-overlay').classList.remove('active');
};

// ===== PAYMENT =====
window.processSale = async function(type) {
    if (cart.length === 0 || !currentSession) return;

    try {
        const payload = {
            session_id: currentSession.id,
            pier: currentPier,
            items: cart.map(i => ({ name: i.name, quantity: i.quantity, price: i.sale_price })),
            payment_type: type
        };

        const result = await apiRequest('/api/pier/sale', { method: 'POST', body: { payload } });
        if (result.status === 'success') {
            showSuccess('Sale Completed!');
            try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
            cart = [];
            renderCart();
            closeMobileCart();
            await refreshSessionStatus();
        }
    } catch (e) {
        alert('Payment error: ' + e.message);
    }
};

// ===== SYNC =====
window.syncData = async function() {
    const btn = document.getElementById('sync-btn');
    btn.classList.add('loading');

    try {
        await apiRequest('/api/pier/sync', { method: 'POST' });
        showSuccess('Synced!');
        try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
        await Promise.all([loadProducts(), loadSeaPlan(), refreshSessionStatus()]);
    } catch (e) {
        alert('Sync error: ' + e.message);
    } finally {
        btn.classList.remove('loading');
    }
};

// ===== UTILITIES =====
function showSuccess(msg) {
    const el = document.getElementById('success-popup');
    el.textContent = `✅ ${msg}`;
    el.classList.add('visible');
    setTimeout(() => el.classList.remove('visible'), 2500);
}

function confirmDialog(msg) {
    return new Promise(resolve => {
        try {
            tg.showConfirm(msg, ok => resolve(ok));
        } catch(e) {
            resolve(confirm(msg));
        }
    });
}

// ===== REPORT =====
async function loadReport() {
    if (!currentPier) return;
    try {
        const result = await apiRequest('/api/pier/report', { data: { pier: currentPier } });
        if (result.status === 'success') renderReport(result.data);
    } catch (e) {
        console.error('Report error:', e);
    }
}

function renderReport(r) {
    // KPI Cards
    document.getElementById('rk-revenue').textContent = `${r.total_amount.toLocaleString()}฿`;
    document.getElementById('rk-cost').textContent = `${r.total_cost.toLocaleString()}฿`;
    document.getElementById('rk-profit').textContent = `${r.total_profit.toLocaleString()}฿`;
    document.getElementById('rk-margin').textContent = `${r.margin_pct}%`;

    // Product Breakdown Table
    const tbody = document.getElementById('report-breakdown-body');
    const items = Object.entries(r.items_summary).sort((a, b) => b[1].subtotal - a[1].subtotal);
    
    if (items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:20px;">No sales yet today</td></tr>';
    } else {
        tbody.innerHTML = items.map(([name, d]) => {
            const marginPct = d.subtotal > 0 ? Math.round((d.profit / d.subtotal) * 100) : 0;
            return `
                <tr>
                    <td>${name}</td>
                    <td class="num">${d.qty}</td>
                    <td class="num">${d.unit_price.toLocaleString()}฿</td>
                    <td class="num cost-cell">${d.cost_price.toLocaleString()}฿</td>
                    <td class="num">${d.subtotal.toLocaleString()}฿</td>
                    <td class="num profit-cell">+${d.profit.toLocaleString()}฿ <small style="opacity:0.6;">(${marginPct}%)</small></td>
                </tr>
            `;
        }).join('') + `
            <tr style="font-weight:900; border-top:2px solid var(--border);">
                <td>TOTAL</td>
                <td class="num">${items.reduce((s, [,d]) => s + d.qty, 0)}</td>
                <td class="num">—</td>
                <td class="num cost-cell">${r.total_cost.toLocaleString()}฿</td>
                <td class="num">${r.total_amount.toLocaleString()}฿</td>
                <td class="num profit-cell">+${r.total_profit.toLocaleString()}฿ <small style="opacity:0.6;">(${r.margin_pct}%)</small></td>
            </tr>
        `;
    }

    // Transaction Log
    const txList = document.getElementById('report-tx-list');
    document.getElementById('report-tx-count').textContent = r.transactions.length;

    if (r.transactions.length === 0) {
        txList.innerHTML = '<p style="text-align:center; color:var(--text-muted); padding:20px; font-size:13px;">No transactions today</p>';
    } else {
        txList.innerHTML = r.transactions.map(tx => {
            const itemsStr = tx.items.map(i => `${i.name}×${i.qty}`).join(', ');
            return `
                <div class="tx-row ${tx.payment}-row">
                    <div class="tx-left">
                        <span class="tx-time">⏰ ${tx.time}</span>
                        <span class="tx-items">${itemsStr}</span>
                    </div>
                    <div class="tx-right">
                        <span class="tx-amount">${tx.amount.toLocaleString()}฿</span>
                        <span class="tx-badge ${tx.payment}">${tx.payment}</span>
                    </div>
                </div>
            `;
        }).join('');
    }
}

// ===== START =====
initializeApp();
