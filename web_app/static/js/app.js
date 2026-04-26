console.log("Telegram WebApp Script Loaded");

// Initialize Telegram WebApp
const tg = window.Telegram.WebApp;
tg.expand(); // Expand to max height

// Theme colors initialization (handled by CSS vars, but we wait for ready)
tg.ready();

// Setup UI based on user
const initDataUnsafe = tg.initDataUnsafe || {};
const user = initDataUnsafe.user || { first_name: "Гид" };
document.getElementById('greeting').innerText = `Привет, ${user.first_name}!`;

const now = new Date();
const dateStr = now.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });
document.getElementById('date-display').innerText = dateStr;

// Set up Tabs
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        // Deactivate all
        tabBtns.forEach(b => b.classList.remove('active'));
        tabContents.forEach(c => c.style.display = 'none');
        
        // Activate target
        btn.classList.add('active');
        const targetId = btn.getAttribute('data-target');
        document.getElementById(targetId).style.display = 'block';
    });
});

// Fetch Schedule
async function loadSchedule() {
    try {
        const response = await fetch(`/api/schedule?initData=${encodeURIComponent(tg.initData)}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        const container = document.getElementById('schedule-cards');
        document.getElementById('schedule-loading').style.display = 'none';
        
        if (data.status === "success" && data.data && data.data.length > 0) {
            container.innerHTML = "";
            data.data.forEach(plan => {
                const card = document.createElement("div");
                card.className = "program-card";
                
                card.innerHTML = `
                    <h3>${plan.date} - ${plan.type === 'sea' ? '🌊 Море' : '🚐 Суша'}</h3>
                    <div class="program-info">
                        <span class="label">Программа</span>
                        <span class="value">${plan.program}</span>
                    </div>
                    ${plan.boat ? `
                    <div class="program-info">
                        <span class="label">Лодка</span>
                        <span class="value">${plan.boat}</span>
                    </div>
                    ` : ''}
                    <div class="program-info">
                        <span class="label">P/U Время</span>
                        <span class="value">${plan.pickup_time || '---'}</span>
                    </div>
                    <div class="program-info">
                        <span class="label">Всего гостей</span>
                        <span class="value">${plan.pax}</span>
                    </div>
                `;
                container.appendChild(card);
            });
        } else {
            container.innerHTML = `<div style="text-align:center; color: var(--hint-color); padding: 20px;">На сегодня и завтра расписания не найдено.</div>`;
        }
    } catch (e) {
        document.getElementById('schedule-loading').innerText = "Ошибка загрузки расписания.";
        console.error("Error loading schedule:", e);
    }
}

// Handling forms
document.getElementById('start-report-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    tg.MainButton.showProgress();
    
    const payload = {
        type: 'start',
        time: document.getElementById('start-time').value,
        adults: document.getElementById('start-pax-adults').value,
        children: document.getElementById('start-pax-children').value,
        comment: document.getElementById('start-comment').value
    };

    await sendReport(payload);
});

document.getElementById('finish-report-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    tg.MainButton.showProgress();
    
    const payload = {
        type: 'finish',
        time: document.getElementById('finish-time').value
    };

    await sendReport(payload);
});

async function sendReport(payload) {
    try {
        const response = await fetch('/api/report', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                initData: tg.initData,
                payload: payload
            })
        });
        
        const result = await response.json();
        
        if (result.status === "success") {
            tg.showAlert('✅ Отчет успешно отправлен!', () => {
                tg.close();
            });
        } else {
            tg.showAlert(`❌ Ошибка: ${result.message || 'Неизвестная ошибка'}`);
        }
    } catch (e) {
        console.error("Failed to submit:", e);
        tg.showAlert('❌ Сетевая ошибка при отправке отчета.');
    } finally {
        tg.MainButton.hideProgress();
    }
}

// Initial Load
loadSchedule();
