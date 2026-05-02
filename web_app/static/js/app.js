// Initialize Telegram WebApp
const tg = window.Telegram.WebApp;

// Global state
let currentPier = new URLSearchParams(window.location.search).get('pier');
const authToken = new URLSearchParams(window.location.search).get('token');
let currentSession = null;
let allProducts = [];
let cart = [];

// Cross-browser UI popups
function uiShowAlert(msg, callback) {
    if (tg.platform && tg.platform !== "unknown") {
        tg.showAlert(msg, callback);
    } else {
        alert(msg);
        if (callback) callback();
    }
}

function uiShowConfirm(msg, callback) {
    if (tg.platform && tg.platform !== "unknown") {
        tg.showConfirm(msg, callback);
    } else {
        const ok = confirm(msg);
        setTimeout(() => callback(ok), 0);
    }
}

// Diagnostics and Initialization
async function initializeApp() {
    console.log("Starting WebApp initialization...");
    tg.ready();
    tg.expand();

    // 1. Unified Authentication & Role Handling
    try {
        const initResult = await apiRequest('/api/init');
        if (initResult.status === "success") {
            const user = initResult.data;
            console.log("User initialized:", user);

            // Update UI
            const greetingEl = document.getElementById('greeting');
            if (greetingEl) greetingEl.innerText = `Привет, ${user.name}!`;

            const debugEl = document.getElementById('debug-auth-info');
            if (debugEl) {
                const method = tg.initData ? "TG" : (authToken ? "Token" : "None");
                debugEl.innerText = `Auth: ${method} | Role: ${user.role} | Pier: ${user.pier || '---'}`;
            }

            // 2. Routing
            const isManager = ['pier_manager', 'admin', 'super_admin', 'head_of_guide'].includes(user.role);
            if (isManager) {
                currentPier = currentPier || user.pier;
                if (currentPier) {
                    console.log("Switching to Manager View for pier:", currentPier);
                    initManagerView();
                    return;
                }
            }
        }
    } catch (e) {
        console.warn("Init API failed, using fallback routing:", e);
    }

    // Default Fallback
    if (currentPier) {
        initManagerView();
    } else {
        loadSchedule();
    }
}

// Tab logic
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        tabContents.forEach(c => c.style.display = 'none');
        btn.classList.add('active');
        const targetId = btn.getAttribute('data-target');
        const targetEl = document.getElementById(targetId);
        if (targetEl) targetEl.style.display = 'block';
    });
});

// Utility for authorization
function getInitData() {
    return tg.initData || "";
}

// API Request Wrapper
async function apiRequest(endpoint, options = {}) {
    const initData = getInitData();
    
    // Default options
    const defaultOptions = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    };
    
    // Merge options
    const mergedOptions = { ...defaultOptions, ...options };
    
    // Add initData or Token to GET params or POST body
    let url = endpoint;
    const queryParams = new URLSearchParams();
    if (getInitData()) queryParams.append('initData', getInitData());
    if (authToken) queryParams.append('token', authToken);

    if (mergedOptions.method === 'GET') {
        const urlObj = new URL(url, window.location.origin);
        queryParams.forEach((v, k) => urlObj.searchParams.append(k, v));
        if (mergedOptions.data) {
            Object.keys(mergedOptions.data).forEach(key => 
                urlObj.searchParams.append(key, mergedOptions.data[key])
            );
        }
        url = urlObj.toString();
    } else {
        let bodyObj = mergedOptions.body || {};
        if (typeof bodyObj === 'string') bodyObj = JSON.parse(bodyObj);
        if (getInitData()) bodyObj.initData = getInitData();
        if (authToken) bodyObj.token = authToken;
        mergedOptions.body = JSON.stringify(bodyObj);
    }

    try {
        const response = await fetch(url, mergedOptions);
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.message || `HTTP ${response.status}`);
        }
        return result;
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        throw error;
    }
}

// --- Guide Logic ---
async function loadSchedule() {
    try {
        const result = await apiRequest('/api/schedule');
        const container = document.getElementById('schedule-cards');
        const loader = document.getElementById('schedule-loading');
        if (loader) loader.style.display = 'none';
        
        if (result.status === "success" && result.data && result.data.length > 0) {
            if (!container) return;
            container.innerHTML = "";
            result.data.forEach(plan => {
                const card = document.createElement("div");
                card.className = "program-card";
                card.innerHTML = `
                    <h3>${plan.date} - ${plan.type === 'sea' ? '🌊 Sea' : '🚐 Land'}</h3>
                    <div class="program-info"><span class="label">Program</span><span class="value">${plan.program}</span></div>
                    ${plan.boat ? `<div class="program-info"><span class="label">Boat</span><span class="value">${plan.boat}</span></div>` : ''}
                    <div class="program-info"><span class="label">P/U Time</span><span class="value">${plan.pickup_time || '---'}</span></div>
                    <div class="program-info"><span class="label">Total guests</span><span class="value">${plan.pax}</span></div>
                `;
                container.appendChild(card);
            });
        } else if (container) {
            container.innerHTML = `<div style="text-align:center; color: var(--hint-color); padding: 20px;">No schedule found for today or tomorrow.</div>`;
        }
    } catch (e) {
        const loader = document.getElementById('schedule-loading');
        if (loader) loader.innerText = "Error loading schedule.";
    }
}

async function closeSession() {
    if (!currentSession) return;
    
    uiShowConfirm("Close this session?", async (ok) => {
        if (!ok) return;
        try {
            const result = await apiRequest('/api/pier/session/close', {
                method: 'POST',
                body: { 
                    session_id: currentSession.id,
                    pier: currentPier 
                }
            });
            if (result.status === "success") {
                uiShowAlert("Session closed. Daily report finalized.");
                refreshSessionStatus();
            }
        } catch (e) {
            uiShowAlert(`Error: ${e.message}`);
        }
    });
}

async function sendReport(payload) {
    tg.MainButton.showProgress();
    try {
        const result = await apiRequest('/api/report', {
            method: 'POST',
            body: { payload: payload }
        });
        if (result.status === "success") {
            uiShowAlert('✅ Report sent successfully!', () => tg.close());
        }
    } catch (e) {
        uiShowAlert(`❌ Error: ${e.message}`);
    } finally {
        tg.MainButton.hideProgress();
    }
}

// Forms
document.getElementById('start-report-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    sendReport({
        type: 'start',
        time: document.getElementById('start-time').value,
        adults: document.getElementById('start-pax-adults').value,
        children: document.getElementById('start-pax-children').value,
        comment: document.getElementById('start-comment').value
    });
});

document.getElementById('finish-report-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    sendReport({ type: 'finish', time: document.getElementById('finish-time').value });
});

// --- Manager Logic ---
async function initManagerView() {
    if (!currentPier) return;
    
    // Expand to full height and width
    tg.ready();
    tg.expand();
    document.body.classList.add('manager-active');
    
    const tabs = document.querySelector('.tabs');
    if (tabs) tabs.style.display = 'none';
    
    document.getElementById('schedule-tab').style.display = 'none';
    document.getElementById('reports-tab').style.display = 'none';
    document.getElementById('manager-view').style.display = 'block';
    document.getElementById('manager-pier-title').innerText = `Pier: ${currentPier}`;
    
    await refreshSessionStatus();
    await loadProducts();
}

async function refreshSessionStatus() {
    try {
        const result = await apiRequest('/api/pier/session', { data: { pier: currentPier } });
        if (result.status === "success") {
            const data = result.data;
            
            // Set Today's Date in specific format
            const phuketDate = new Date().toLocaleDateString('ru-RU', { timeZone: 'Asia/Bangkok' });
            
            if (data.active) {
                currentSession = data;
                document.getElementById('session-status').innerText = "Session Open";
                document.getElementById('session-status').className = "session-badge open";
                document.getElementById('session-controls').style.display = 'none';
                document.getElementById('cash-register').style.display = 'block';
                
                document.getElementById('report-container').style.display = 'block';
                document.getElementById('close-session-btn').style.display = 'block';
                document.getElementById('report-title').innerText = `📊 Daily Report: ${phuketDate} (Active)`;
                updateReportDisplay(data.report);
            } else {
                currentSession = null;
                document.getElementById('session-status').innerText = "Session Closed";
                document.getElementById('session-status').className = "session-badge closed";
                document.getElementById('session-controls').style.display = 'flex';
                document.getElementById('cash-register').style.display = 'none';
                
                if (data.report) {
                    document.getElementById('report-container').style.display = 'block';
                    document.getElementById('close-session-btn').style.display = 'none';
                    document.getElementById('report-title').innerText = `📊 Daily Report: ${phuketDate} (Final)`;
                    updateReportDisplay(data.report);
                } else {
                    document.getElementById('report-container').style.display = 'none';
                }
            }
        }
    } catch (e) {
        console.error("Session refresh failed:", e);
        showError(e.message);
    }
}

async function loadProducts() {
    try {
        const result = await apiRequest('/api/pier/products');
        if (result.status === "success") {
            allProducts = result.data;
            renderProductGrid();
        }
    } catch (e) {
        showError(e.message);
    }
}

function renderProductGrid() {
    const grid = document.getElementById('product-grid');
    if (!grid) return;
    grid.innerHTML = "";
    allProducts.forEach(p => {
        const item = document.createElement('div');
        item.className = 'product-item';
        item.innerHTML = `<span class="name">${p.name}</span><span class="price">${p.sale_price}฿</span>`;
        item.onclick = () => addToCart(p);
        grid.appendChild(item);
    });
}

function addToCart(product) {
    const existing = cart.find(item => item.id === product.id);
    if (existing) existing.quantity++;
    else cart.push({ ...product, quantity: 1 });
    renderCart();
    tg.HapticFeedback.impactOccurred('light');
}

function renderCart() {
    const list = document.getElementById('cart-items');
    if (!list) return;
    list.innerHTML = "";
    let total = 0;
    cart.forEach(item => {
        const row = document.createElement('div');
        row.className = 'cart-item';
        row.innerHTML = `
            <div class="item-info"><span class="item-name">${item.name}</span><span class="item-price">${item.sale_price}฿</span></div>
            <div class="qty-controls">
                <button class="qty-btn" onclick="updateQty(${item.id}, -1)">-</button>
                <span class="item-qty">${item.quantity}</span>
                <button class="qty-btn" onclick="updateQty(${item.id}, 1)">+</button>
            </div>
        `;
        list.appendChild(row);
        total += item.sale_price * item.quantity;
    });
    const totalEl = document.getElementById('cart-total-amount');
    if (totalEl) totalEl.innerText = total;
}

window.updateQty = (id, delta) => {
    const item = cart.find(i => i.id === id);
    if (item) {
        item.quantity += delta;
        if (item.quantity <= 0) cart = cart.filter(i => i.id !== id);
        renderCart();
    }
};

function updateReportDisplay(report) {
    const summary = document.getElementById('session-report-summary');
    if (!summary) return;

    // --- 1. KPI Summary Grid ---
    const kpiHtml = `
        <div class="report-summary-grid">
            <div class="report-item">
                <span class="val">${report.sales_count}</span>
                <span class="lab">Transactions</span>
            </div>
            <div class="report-item">
                <span class="val">${report.total_amount.toLocaleString()}฿</span>
                <span class="lab">Total Revenue</span>
            </div>
            <div class="report-item">
                <span class="val" style="color:var(--corporate-teal)">${report.cash_amount.toLocaleString()}฿</span>
                <span class="lab">💵 Cash</span>
            </div>
            <div class="report-item">
                <span class="val" style="color:var(--corporate-red)">${report.online_amount.toLocaleString()}฿</span>
                <span class="lab">📱 Online</span>
            </div>
        </div>`;

    // --- 2. Product Breakdown Table ---
    let itemRows = '';
    const items = report.items_summary || {};
    Object.entries(items).sort((a,b) => b[1].subtotal - a[1].subtotal).forEach(([name, d]) => {
        itemRows += `
            <tr>
                <td>${name}</td>
                <td class="num">${d.qty}</td>
                <td class="num">${d.unit_price.toLocaleString()}฿</td>
                <td class="num total-cell">${d.subtotal.toLocaleString()}฿</td>
                <td class="num cash-cell">${d.cash > 0 ? d.cash.toLocaleString()+'฿' : '—'}</td>
                <td class="num online-cell">${d.online > 0 ? d.online.toLocaleString()+'฿' : '—'}</td>
            </tr>`;
    });

    const tableHtml = Object.keys(items).length > 0 ? `
        <div class="report-section-title">📦 Product Breakdown</div>
        <div class="report-table-wrap">
            <table class="report-table">
                <thead>
                    <tr>
                        <th>Product</th>
                        <th class="num">Qty</th>
                        <th class="num">Unit ฿</th>
                        <th class="num">Subtotal</th>
                        <th class="num">Cash</th>
                        <th class="num">Online</th>
                    </tr>
                </thead>
                <tbody>${itemRows}</tbody>
            </table>
        </div>` : '';

    // --- 3. Transactions Log ---
    let txRows = '';
    const txList = (report.transactions || []).slice().reverse();
    txList.forEach(tx => {
        const isCash = tx.payment === 'cash';
        const badge = isCash
            ? `<span class="pay-badge cash">Cash</span>`
            : `<span class="pay-badge online">Online</span>`;
        const rowClass = isCash ? 'cash-row' : 'online-row';
        const itemsList = tx.items.map(i => `${i.name} ×${i.qty}`).join(', ');
        txRows += `
            <div class="tx-row ${rowClass}">
                <div class="tx-left">
                    <span class="tx-time">${tx.time}</span>
                    <span class="tx-items">${itemsList}</span>
                </div>
                <div class="tx-right">
                    ${badge}
                    <span class="tx-amount">${tx.amount.toLocaleString()}฿</span>
                </div>
            </div>`;
    });

    const txHtml = txRows ? `
        <div class="report-section-title" style="margin-top:20px">
            🧾 Transactions
            <span class="tx-count">${txList.length} sales</span>
        </div>
        <div class="tx-list">${txRows}</div>` : '';

    summary.innerHTML = kpiHtml + tableHtml + txHtml;
}


function showError(msg) {
    const overlay = document.getElementById('error-overlay');
    const msgEl = document.getElementById('error-message');
    if (!overlay || !msgEl) return;
    msgEl.innerText = msg;
    overlay.style.display = 'flex';
}

document.getElementById('close-error-btn')?.addEventListener('click', () => {
    const overlay = document.getElementById('error-overlay');
    if (overlay) overlay.style.display = 'none';
});

// Control Buttons
document.getElementById('open-session-btn')?.addEventListener('click', async () => {
    try {
        await apiRequest('/api/pier/session/open', { method: 'POST', body: { pier: currentPier } });
        tg.HapticFeedback.notificationOccurred('success');
        await refreshSessionStatus();
    } catch (e) { uiShowAlert(e.message); }
});

document.getElementById('close-session-btn')?.addEventListener('click', closeSession);


document.querySelectorAll('.pay-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
        if (cart.length === 0) { uiShowAlert("Cart is empty!"); return; }
        const type = btn.getAttribute('data-type');
        tg.MainButton.showProgress();
        try {
            await apiRequest('/api/pier/sale', {
                method: 'POST',
                body: { payload: {
                    session_id: currentSession.id,
                    pier: currentPier,
                    items: cart.map(i => ({ name: i.name, quantity: i.quantity, price: i.sale_price })),
                    payment_type: type
                }}
            });
            tg.HapticFeedback.notificationOccurred('success');
            cart = [];
            renderCart();
            await refreshSessionStatus();
            
            // Show Success Popup
            const popup = document.getElementById('success-popup');
            if (popup) {
                popup.style.display = 'block';
                void popup.offsetWidth; // trigger reflow
                popup.style.opacity = '1';
                setTimeout(() => {
                    popup.style.opacity = '0';
                    setTimeout(() => popup.style.display = 'none', 300);
                }, 2000);
            }
            
        } catch (e) { uiShowAlert(e.message); }
        finally { tg.MainButton.hideProgress(); }
    });
});

// Start
initializeApp();
