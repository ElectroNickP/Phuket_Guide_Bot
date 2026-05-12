from aiogram import Router, types, F, Bot
from aiogram.types import WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, KeyboardButton, InlineKeyboardBuilder
from database.models import UserRole
from utils.permissions import RoleFilter
from services.sea_plan import sea_plan_service
from services.pos_client import pos_client, POSClientError
from utils.time import get_phuket_now
from utils.auth_tokens import generate_auth_token
from loguru import logger
from config import config
from services.np_calculator import detect_nps, np_fee_line, calc_envelope, NP_FEES
import datetime
import re

router = Router()

# Define roles allowed to access this dashboard
ALLOWED_ROLES = [UserRole.PIER_MANAGER, UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE]

PIERS = ["RPM", "Yamu", "Sarasin", "Chalong"]

class PierManagerStates(StatesGroup):
    waiting_for_pier = State()
    dashboard = State()
    pier_ops = State()
    envelope_calc = State()  # waiting for PAX input
    
    # Cash Register states
    cash_main = State()
    cash_sale_category = State()
    cash_sale_product = State()
    cash_sale_quantity = State()
    cash_sale_payment = State()

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

@router.message(F.text == "⚓️ Панель Пирс-Менеджера", RoleFilter(ALLOWED_ROLES))
async def cmd_pier_manager_dashboard(message: types.Message, state: FSMContext):
    logger.info(f"Pier Manager dashboard accessed by {message.from_user.id}")

    builder = ReplyKeyboardBuilder()
    for pier in PIERS:
        builder.button(text=pier)
    builder.row(KeyboardButton(text="🔙 Главное меню"))
    builder.adjust(2)

    await state.set_state(PierManagerStates.waiting_for_pier)
    await message.answer(
        "⚓️ <b>Панель Пирс-Менеджера</b>\n\nПожалуйста, выберите пирс для работы:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# ─────────────────────────────────────────────────────────────────────────────
# PIER SELECTION → MAIN PIER DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.waiting_for_pier, F.text.in_(PIERS))
async def process_pier_selection(message: types.Message, state: FSMContext):
    pier = message.text
    await state.update_data(selected_pier=pier)
    await state.set_state(PierManagerStates.dashboard)
    await show_pier_dashboard(message, pier)


async def show_pier_dashboard(message: types.Message, pier: str):
    """Main dashboard for a selected pier — info + open pier button."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=f"🚪 Открыть пирс {pier}")
    builder.button(text="⛴ Лодки сегодня")
    builder.button(text="⛴ Лодки завтра")
    builder.button(text="👤 Гиды сегодня")
    builder.button(text="👤 Гиды завтра")
    builder.button(text="🔄 Сменить пирс")
    builder.button(text="🔙 Главное меню")
    builder.adjust(1, 2, 2, 2)

    await message.answer(
        f"⚓️ <b>Пирс: {pier}</b>\n\nВыберите нужное действие:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# ─────────────────────────────────────────────────────────────────────────────
# BOATS / GUIDES INFO (existing logic)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.dashboard, F.text.regexp(r"(⛴ Лодки|👤 Гиды) (сегодня|завтра)"))
async def process_pier_action(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier")
    if not pier:
        await cmd_pier_manager_dashboard(message, state)
        return

    text = message.text
    is_boats = "Лодки" in text
    is_today = "сегодня" in text

    target_date = get_phuket_now().date()
    if not is_today:
        target_date += datetime.timedelta(days=1)

    date_str = target_date.strftime("%d.%m.%Y")
    await message.answer(f"⏳ Загружаю данные из Google Таблицы на {date_str}...")

    plans = await sea_plan_service.get_pier_detailed_plan(pier, target_date)

    if not plans:
        await message.answer(f"❌ Данных для пирса <b>{pier}</b> на <b>{date_str}</b> не найдено.", parse_mode="HTML")
        return

    if is_boats:
        report = f"⛴ <b>Лодки на пирсе {pier} ({date_str}):</b>\n\n"
        for p in sorted(plans, key=lambda x: x.boat):
            progs = ", ".join([prog.name for prog in p.programs])
            pax = p.pax_string
            guides = ", ".join([g.full_info for g in p.guides])
            report += f"🚢 <b>{p.boat}</b>\n"
            report += f"📝 Программы: {progs}\n"
            report += f"👥 PAX: <code>{pax}</code>\n"
            report += f"👤 Гиды: {guides}\n"
            if p.thai_guide:
                report += f"🇹🇭 Тай. гид: {p.thai_guide}\n"
            report += "──────────────────\n"
    else:
        report = f"👤 <b>Гиды на пирсе {pier} ({date_str}):</b>\n\n"
        unique_guides = {}
        for p in plans:
            for g in p.guides:
                if g.full_info not in unique_guides:
                    unique_guides[g.full_info] = []
                unique_guides[g.full_info].append(p.boat)

        if not unique_guides:
            report += "Гиды не найдены."
        else:
            for guide, boats in sorted(unique_guides.items()):
                boats_str = ", ".join(boats)
                report += f"👤 {guide}\n🚢 Лодки: {boats_str}\n\n"

    for x in range(0, len(report), 4000):
        await message.answer(report[x:x+4000], parse_mode="HTML")

# ─────────────────────────────────────────────────────────────────────────────
# OPEN PIER → OPERATIONS PANEL
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.dashboard, F.text.regexp(r"^🚪 Открыть пирс (.+)$"))
async def open_pier_ops(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier")
    if not pier:
        await cmd_pier_manager_dashboard(message, state)
        return

    await state.set_state(PierManagerStates.pier_ops)
    await show_pier_ops_menu(message, pier)


async def show_pier_ops_menu(message: types.Message, pier: str):
    # Secure token generation for fallback auth
    token = generate_auth_token(message.from_user.id, config.BOT_TOKEN.get_secret_value())
    webapp_url = f"{config.WEBAPP_URL}/?pier={pier}&token={token}"
    
    # Dashboard Keyboard
    builder = ReplyKeyboardBuilder()
    builder.button(text="🖥 Веб-интерфейс", web_app=WebAppInfo(url=webapp_url))
    builder.button(text="💰 Касса")
    builder.button(text="🏞 Нац. парки")
    builder.button(text="📩 Конверты NP")
    builder.button(text="📊 Итоги дня")
    builder.button(text="⛴ Лодки сегодня")
    builder.button(text="👤 Гиды сегодня")
    builder.button(text="🔙 К выбору пирса")
    builder.adjust(1, 2, 1, 1, 2, 1)
    
    # Inline button for maximum reliability on Desktop
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="🖥 Внутри Telegram", web_app=WebAppInfo(url=webapp_url))
    inline_builder.button(text="🌐 Внешний браузер", url=webapp_url)
    inline_builder.adjust(1, 1)
    
    await message.answer(
        f"⚓️ <b>Операции на пирсе {pier}</b>\n\nВыберите действие в меню или откройте веб-приложение для работы с кассой:",
        reply_markup=builder.as_markup(resize_keyboard=True),
        parse_mode="HTML"
    )
    await message.answer("💡 Рекомендуем использовать эту кнопку для входа:", reply_markup=inline_builder.as_markup())

    now = get_phuket_now()
    is_sunday = now.weekday() == 6
    sunday_warn = "\n⚠️ Сегодня воскресенье — JB без бесплатных!" if is_sunday else ""
    await message.answer(
        f"🚪 <b>Пирс {pier} открыт</b>\n"
        f"📅 {now.strftime('%d.%m.%Y')}  🕐 {now.strftime('%H:%M')}{sunday_warn}\n\n"
        f"Выберите действие:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# ─────────────────────────────────────────────────────────────────────────────
# OPS: 💰 Касса (Cash Register)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.pier_ops, F.text == "💰 Касса")
async def ops_cash_main(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier")
    if not pier:
        await cmd_pier_manager_dashboard(message, state)
        return

    # Check for active session
    session = await pos_client.get_active_session(pier)
    await state.set_state(PierManagerStates.cash_main)
    
    if not session:
        builder = ReplyKeyboardBuilder()
        builder.button(text="🟢 Открыть новую смену")
        builder.button(text="🔄 Синхронизировать товары")
        builder.button(text="🔙 Назад")
        builder.adjust(1)
        
        await message.answer(
            f"💰 <b>Касса — Пирс {pier}</b>\n\nНет открытой смены. Пожалуйста, откройте смену, чтобы начать работу.",
            parse_mode="HTML",
            reply_markup=builder.as_markup(resize_keyboard=True)
        )
    else:
        await show_cash_menu(message, pier, session)


async def show_cash_menu(message: types.Message, pier: str, session):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🛒 Продажа")
    builder.button(text="📊 Отчет за смену")
    builder.button(text="🔴 Закрыть смену")
    builder.button(text="🔙 Назад")
    builder.adjust(1, 2, 1)
    
    now = get_phuket_now()
    opened_at = session.get('opened_at', '?')
    if isinstance(opened_at, str) and 'T' in opened_at:
        # Parse ISO datetime string
        try:
            from datetime import datetime
            opened_at = datetime.fromisoformat(opened_at).strftime('%H:%M')
        except: pass
    
    await message.answer(
        f"💰 <b>Касса — Пирс {pier}</b>\n"
        f"──────────────────\n"
        f"✅ Смена открыта в: <b>{opened_at}</b>\n"
        f"🕒 Текущее время: <b>{now.strftime('%H:%M')}</b>\n"
        f"👤 Менеджер: <b>{message.from_user.full_name}</b>\n"
        f"──────────────────\n"
        f"Выберите действие:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@router.message(PierManagerStates.cash_main, F.text == "🟢 Открыть новую смену")
async def ops_cash_open_session(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier")
    manager_id = message.from_user.id
    
    session = await pos_client.open_session(pier, manager_id)
    await show_cash_menu(message, pier, session)

@router.message(PierManagerStates.cash_main, F.text == "🔄 Синхронизировать товары")
async def ops_cash_sync_products(message: types.Message, state: FSMContext):
    msg = await message.answer("⏳ Синхронизация товаров из Google Sheets...")
    try:
        count = await pos_client.sync_products()
        if count > 0:
            await msg.edit_text("✅ Список товаров успешно обновлен!")
        else:
            await msg.edit_text("❌ Ошибка при синхронизации товаров. Проверьте логи.")
    except PermissionError:
        from config import config
        # Fetch email from service account file or just hardcode if known from JSON
        service_email = "bot-reader-telegram@best-telegram-bots.iam.gserviceaccount.com"
        await msg.edit_text(
            f"❌ <b>Доступ запрещен</b>\n\n"
            f"Бот не имеет доступа к таблице с прайс-листом.\n\n"
            f"Пожалуйста, предоставьте доступ (роль 'Редактор' или 'Читатель') для этого email:\n"
            f"<code>{service_email}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Sync error: {e}")
        await msg.edit_text(f"❌ Произошла ошибка при синхронизации: {e}")

@router.message(PierManagerStates.cash_main, F.text == "🛒 Продажа")
async def ops_cash_start_sale(message: types.Message, state: FSMContext):
    products = await pos_client.get_products()
    if not products:
        await message.answer("⚠️ Список товаров пуст. Пожалуйста, синхронизируйте товары.")
        return

    # Initialize cart
    await state.update_data(cart=[])
    await state.set_state(PierManagerStates.cash_sale_category)
    await show_category_selection(message, state)

async def show_category_selection(message: types.Message, state: FSMContext):
    # Fetch categories from DB for parity with Web App
    categories = await pos_client.get_categories()
    
    # Mapping for nice labels with emojis
    MAPPING = {
        "Bar": "🍹 Напитки (Bar)",
        "Rental": "🤿 Аренда (Rental)",
        "Repellents": "🦟 Репелленты",
        "Clothing": "👕 Одежда",
        "Clothing (Apparel)": "👕 Одежда",
        "Bags & Storage": "🎒 Сумки",
        "Accessories": "💍 Аксессуары",
        "Other": "🧩 Разное"
    }
    
    # Store dynamic mapping in state for reverse lookup
    label_to_cat = {}
    
    builder = ReplyKeyboardBuilder()
    # Add known categories from DB
    processed = set()
    for cat in categories:
        label = MAPPING.get(cat, f"📦 {cat}")
        if label in processed: continue
        builder.button(text=label)
        label_to_cat[label] = cat
        processed.add(label)
    
    # Fallback if no products/categories
    if not categories:
        builder.button(text="🧩 Разное")
        label_to_cat["🧩 Разное"] = "Other"

    builder.row(KeyboardButton(text="🔙 Назад"))
    builder.adjust(2)
    
    await state.update_data(label_to_cat=label_to_cat)
    
    await message.answer(
        "📂 <b>Выберите категорию товаров:</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@router.message(PierManagerStates.cash_sale_category, F.text == "🔙 Назад")
async def ops_cash_cat_back(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier")
    session = await pos_client.get_active_session(pier)
    await state.set_state(PierManagerStates.cash_main)
    await show_cash_menu(message, pier, session)

@router.message(PierManagerStates.cash_sale_category)
async def ops_cash_select_category(message: types.Message, state: FSMContext):
    data = await state.get_data()
    label_to_cat = data.get("label_to_cat", {})
    category = label_to_cat.get(message.text)
    
    if not category:
        # Emergency backup if state lost mapping
        text = message.text.lower()
        if "напитки" in text: category = "Bar"
        elif "аренда" in text: category = "Rental"
        elif "репеллент" in text: category = "Repellents"
        elif "одежда" in text: category = "Clothing"
        elif "сумки" in text: category = "Bags & Storage"
        elif "разное" in text: category = "Other"
        else: category = "Other"
    
    await state.update_data(selected_category=category)
    products = await pos_client.get_products()
    filtered = [p for p in products if p.get('category') == category]
    
    if not filtered:
        await message.answer(f"⚠️ В категории <b>{category}</b> нет активных товаров.", parse_mode="HTML")
        return

    data = await state.get_data()
    cart = data.get("cart", [])
    await state.set_state(PierManagerStates.cash_sale_product)
    await show_product_selection(message, filtered, cart)

async def show_product_selection(message: types.Message, products, cart):
    builder = ReplyKeyboardBuilder()
    for p in products:
        emoji = get_emoji_for_category(p.get('category', 'Other'))
        builder.button(text=f"{emoji} {p['name']} ({p['sale_price']}฿)")
    
    builder.row(KeyboardButton(text="🧮 Посмотреть корзину"))
    builder.row(KeyboardButton(text="📁 К категориям"))
    builder.row(KeyboardButton(text="❌ Отмена"))
    builder.adjust(2)
    
    cart_text = ""
    if cart:
        cart_text = "<b>🛒 В корзине:</b>\n"
        total = 0
        for i, item in enumerate(cart):
            item_total = item['quantity'] * item['price']
            total += item_total
            cart_text += f"{i+1}. {item['name']} x{item['quantity']} = {item_total}฿\n"
        cart_text += f"──────────────────\n💰 <b>Итого: {total}฿</b>\n\n"

    await message.answer(
        f"{cart_text}🛍 <b>Выберите товар или действие:</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

def get_emoji_for_category(cat: str) -> str:
    c = cat.lower()
    if "bar" in c: return "🍹"
    if "rental" in c: return "🤿"
    if "repellent" in c: return "🦟"
    if "clothing" in c: return "👕"
    if "bag" in c: return "🎒"
    return "🧩"

@router.message(PierManagerStates.cash_sale_product, F.text == "📁 К категориям")
async def ops_cash_back_to_cats(message: types.Message, state: FSMContext):
    await state.set_state(PierManagerStates.cash_sale_category)
    await show_category_selection(message)

@router.message(PierManagerStates.cash_sale_product, F.text == "🧮 Посмотреть корзину")
@router.message(PierManagerStates.cash_sale_product, F.text == "✅ Оформить продажу")
async def ops_cash_sale_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", [])
    if not cart:
        await message.answer("⚠️ Корзина пуста. Добавьте товары, прежде чем оформлять продажу.")
        return
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="💵 Наличные B")
    builder.button(text="💳 Онлайн")
    builder.button(text="🔄 Очистить корзину")
    builder.button(text="🔙 Назад к товарам")
    builder.adjust(2, 1, 1)
    
    items_text = "<b>🛒 Состав заказа:</b>\n"
    total = 0
    for i, item in enumerate(cart):
        item_total = item['quantity'] * item['price']
        total += item_total
        items_text += f"{i+1}. {item['name']} x{item['quantity']} = {item_total}฿\n"
    
    await state.set_state(PierManagerStates.cash_sale_payment)
    await message.answer(
        f"{items_text}\n💰 <b>Сумма к оплате: {total}฿</b>\n\nВыберите способ оплаты или действие:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@router.message(PierManagerStates.cash_sale_payment, F.text == "🔄 Очистить корзину")
async def ops_cash_clear_cart(message: types.Message, state: FSMContext):
    await state.update_data(cart=[])
    await message.answer("✅ Корзина очищена.")
    await state.set_state(PierManagerStates.cash_sale_category)
    await show_category_selection(message)

@router.message(PierManagerStates.cash_sale_product)
async def ops_cash_select_product(message: types.Message, state: FSMContext):
    text = message.text
    # Parse product name from button text "Emoji Name (Price฿)"
    match = re.search(r"(.+)\s\((\d+)฿\)", text)
    if not match:
        await message.answer("⚠️ Пожалуйста, используйте кнопки для выбора товара.")
        return
    
    # Remove emoji from name if present
    full_name = match.group(1).strip()
    product_name = re.sub(r"^[^\w\s]\s*", "", full_name).strip()
    price = int(match.group(2))
    
    await state.update_data(current_item={'name': product_name, 'price': price})
    await state.set_state(PierManagerStates.cash_sale_quantity)
    
    builder = ReplyKeyboardBuilder()
    for q in [1, 2, 3, 4, 5, 10]:
        builder.button(text=str(q))
    builder.button(text="🔙 Назад")
    builder.adjust(3)
    
    await message.answer(
        f"🔢 <b>{product_name}</b>\n\nСколько штук?",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@router.message(PierManagerStates.cash_sale_quantity, F.text == "🔙 Назад")
async def ops_cash_quantity_back(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cat = data.get("selected_category")
    products = await pos_client.get_products()
    filtered = [p for p in products if p.get('category') == cat or (cat == "Other" and p.get('category') not in ["Bar", "Rental", "Repellents", "Clothing", "Bags & Storage"])]
    cart = data.get("cart", [])
    await state.set_state(PierManagerStates.cash_sale_product)
    await show_product_selection(message, filtered, cart)

@router.message(PierManagerStates.cash_sale_quantity, F.text.regexp(r"^\d+$"))
async def ops_cash_select_quantity(message: types.Message, state: FSMContext):
    quantity = int(message.text)
    if quantity <= 0:
        await message.answer("❌ Количество должно быть больше 0.")
        return
    
    data = await state.get_data()
    cart = data.get("cart", [])
    current_item = data.get("current_item")
    
    # Add or update item in cart
    existing_item = next((item for item in cart if item['name'] == current_item['name']), None)
    if existing_item:
        existing_item['quantity'] += quantity
    else:
        cart.append({
            'name': current_item['name'],
            'price': current_item['price'],
            'quantity': quantity
        })
    
    await state.update_data(cart=cart)
    data = await state.get_data()
    cat = data.get("selected_category")
    products = await pos_client.get_products()
    filtered = [p for p in products if p.get('category') == cat or (cat == "Other" and p.get('category') not in ["Bar", "Rental", "Repellents", "Clothing", "Bags & Storage"])]
    
    await state.set_state(PierManagerStates.cash_sale_product)
    await message.answer(f"✅ Добавлено: <b>{current_item['name']}</b> x{quantity}", parse_mode="HTML")
    await show_product_selection(message, filtered, cart)

@router.message(PierManagerStates.cash_sale_payment, F.text == "🔙 Назад к товарам")
async def ops_cash_payment_back(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cat = data.get("selected_category")
    products = await pos_client.get_products()
    filtered = [p for p in products if p.get('category') == cat or (cat == "Other" and p.get('category') not in ["Bar", "Rental", "Repellents", "Clothing", "Bags & Storage"])]
    cart = data.get("cart", [])
    await state.set_state(PierManagerStates.cash_sale_product)
    await show_product_selection(message, filtered, cart)

@router.message(PierManagerStates.cash_sale_payment, F.text.in_(["💵 Наличные B", "💳 Онлайн"]))
async def ops_cash_confirm_sale(message: types.Message, state: FSMContext):
    payment_type = "cash" if "Наличные" in message.text else "online"
    data = await state.get_data()
    cart = data.get("cart", [])
    pier = data.get("selected_pier")
    manager_id = message.from_user.id
    
    session = await pos_client.get_active_session(pier)
    if not session:
        await message.answer("❌ Смена была закрыта. Продажа невозможна.")
        await ops_cash_main(message, state)
        return
        
    sale = await pos_client.record_sale(
        session_id=session['id'],
        pier=pier,
        manager_id=manager_id,
        items_data=cart,
        payment_type=payment_type,
    )
    
    # Confirmation text
    items_text = ""
    for item in cart:
        items_text += f"• {item['name']} x{item['quantity']} = {item['quantity'] * item['price']}฿\n"
    
    receipt = (
        f"✅ <b>Продажа зафиксирована</b>\n"
        f"──────────────────\n"
        f"{items_text}"
        f"──────────────────\n"
        f"💰 Итого: <b>{sale.get('total_amount', 0)}฿</b>\n"
        f"💳 Оплата: <b>{message.text}</b>\n"
    )
    
    await message.answer(receipt, parse_mode="HTML")
    await state.set_state(PierManagerStates.cash_main)
    await show_cash_menu(message, pier, session)

@router.message(PierManagerStates.cash_main, F.text == "📊 Отчет за смену")
async def ops_cash_session_report(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier")
    session = await pos_client.get_active_session(pier)
    
    if not session:
        await message.answer("❌ Нет активной смены.")
        return
        
    report = await pos_client.get_session_report(session['id'])
    
    items_text = ""
    for name, qty in sorted(report["items_summary"].items()):
        items_text += f"• {name}: <b>{qty}</b> шт.\n"
    
    text = (
        f"📊 <b>Отчет за смену — Пирс {pier}</b>\n"
        f"📅 Открыта: <code>{session.get('opened_at', '?')}</code>\n"
        f"──────────────────\n"
        f"💼 <b>Статистика продаж:</b>\n"
        f"💰 Итого:  <b>{report['total_amount']:,}฿</b>\n"
        f"💵 Налич:  <b>{report['cash_amount']:,}฿</b>\n"
        f"💳 Онлйн:  <b>{report['online_amount']:,}฿</b>\n"
        f"🧾 Чеков:  <b>{report['sales_count']}</b>\n"
        f"──────────────────\n"
        f"🛒 <b>Продано товаров:</b>\n{items_text or '—'}\n"
        f"──────────────────\n"
        f"👤 Менеджер: {message.from_user.full_name}"
    )
    
    await message.answer(text, parse_mode="HTML")

@router.message(PierManagerStates.cash_main, F.text == "🔴 Закрыть смену")
async def ops_cash_close_session(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier")
    session = await pos_client.get_active_session(pier)
    
    if not session:
        await message.answer("❌ Смена уже закрыта.")
        await ops_cash_main(message, state)
        return
        
    # Get final report before closing
    report = await pos_client.get_session_report(session['id'])
    await pos_client.close_session(session['id'], pier)
    
    text = (
        f"🔴 <b>Смена закрыта</b>\n"
        f"──────────────────\n"
        f"🚢 Пирс: <b>{pier}</b>\n"
        f"🕒 Время: <b>{get_phuket_now().strftime('%H:%M')}</b>\n"
        f"💰 Итого за смену: <b>{report['total_amount']}฿</b>\n"
        f"──────────────────\n"
        f"✅ Данные сохранены. Спасибо за работу!"
    )
    
    await message.answer(text, parse_mode="HTML")
    await state.set_state(PierManagerStates.pier_ops)
    await show_pier_ops_menu(message, pier)

@router.message(PierManagerStates.cash_main, F.text == "🔙 Назад")
async def ops_cash_back_to_ops(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier")
    await state.set_state(PierManagerStates.pier_ops)
    await show_pier_ops_menu(message, pier)

@router.message(PierManagerStates.pier_ops, F.text == "🏞 Нац. парки")
async def ops_nat_parks(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier", "—")
    target_date = get_phuket_now().date()
    date_str = target_date.strftime("%d.%m.%Y")

    await message.answer(f"⏳ Проверяю нац. парки для пирса <b>{pier}</b> на {date_str}...", parse_mode="HTML")

    plans = await sea_plan_service.get_pier_detailed_plan(pier, target_date)

    if not plans:
        await message.answer(f"❌ Данных для пирса <b>{pier}</b> на <b>{date_str}</b> не найдено.", parse_mode="HTML")
        return

    # Collect: np_code → list of program entries
    # Each program can have multiple NP codes
    np_entries: dict[str, list] = {"PP": [], "JB": [], "HG": []}

    for plan in plans:
        for prog in plan.programs:
            codes = detect_nps(prog.name)
            for code in codes:
                if code in np_entries:
                    np_entries[code].append({
                        "boat": plan.boat,
                        "program": prog.name,
                        "pax": prog.pax,
                        "guide": prog.guide,
                    })

    has_any = any(np_entries[k] for k in np_entries)
    if not has_any:
        await message.answer(
            f"🏞 <b>Нац. парки — {pier} ({date_str})</b>\n\n"
            "Программ с нац. парками не обнаружено.",
            parse_mode="HTML"
        )
        return

    report = f"🏞 <b>Нац. парки — {pier} ({date_str})</b>\n\n"
    total_np_pax = 0

    for code in ["PP", "JB", "HG"]:
        entries = np_entries[code]
        if not entries:
            continue
        f = NP_FEES[code]
        report += f"<b>{f['emoji']} {f['name']}</b>\n"
        report += f"{np_fee_line(code)}\n"
        for e in entries:
            pax_total = _sum_pax(e['pax'])
            total_np_pax += pax_total
            report += f"  🚢 {e['boat']} — {e['program']}\n"
            report += f"     👥 PAX: <code>{e['pax']}</code> ({pax_total} чел.)\n"
            if e['guide']:
                report += f"     👤 Гид: {e['guide']}\n"
        report += "\n"

    report += "──────────────────\n"
    report += f"🎫 Итого туристов с нац. парками: <b>{total_np_pax}</b>"

    await message.answer(report, parse_mode="HTML")

# ─────────────────────────────────────────────────────────────────────────────
# OPS: 📩 Конверты NP — envelope calculator
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.pier_ops, F.text == "📩 Конверты NP")
async def ops_envelope_start(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier")
    if not pier:
        await cmd_pier_manager_dashboard(message, state)
        return

    target_date = get_phuket_now().date()
    date_str = target_date.strftime("%d.%m.%Y")
    now = get_phuket_now()
    is_sunday = now.weekday() == 6

    await message.answer(f"⏳ Рассчитываю конверты для лодок на пирсе <b>{pier}</b>...", parse_mode="HTML")

    plans = await sea_plan_service.get_pier_detailed_plan(pier, target_date)

    report = (
        f"📩 <b>Авто-расчёт конвертов — {pier} ({date_str})</b>\n"
        f"📅 {now.strftime('%H:%M')} | {'⚠️ ВОСКРЕСЕНЬЕ' if is_sunday else now.strftime('%A')}\n"
        f"──────────────────\n"
    )

    if not plans:
        report += "❌ Плана на сегодня не найдено.\n"
    else:
        grand_total_all = 0
        for plan in sorted(plans, key=lambda x: x.boat):
            # Parse PAX from plan.pax_string (e.g. "22/0/0")
            pa, pc, pi = 0, 0, 0
            try:
                parts = plan.pax_string.split("/")
                pa = int(parts[0]) if parts[0].isdigit() else 0
                pc = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                pi = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            except Exception:
                pass

            if pa + pc + pi == 0:
                continue

            report += f"🚢 <b>{plan.boat}</b> (PAX: <code>{plan.pax_string}</code>)\n"
            boat_total = 0
            for code in ["PP", "JB", "HG"]:
                fee = NP_FEES[code]
                total, formula = calc_envelope(code, pa, pc, is_sunday)
                boat_total += total
                report += f"  {fee['emoji']} <code>{total:,}฿</code> ({formula})\n"
            
            report += f"  💰 Итого лодка: <b>{boat_total:,}฿</b>\n"
            report += "──────────────────\n"
            grand_total_all += boat_total

        if grand_total_all > 0:
            report += f"💼 <b>ОБЩИЙ ИТОГ ПИРС: {grand_total_all:,}฿</b>\n\n"
        else:
            report += "Нет активных лодок с PAX > 0.\n\n"

    report += (
        "💡 Выше — данные из Sea Plan.\n"
        "Чтобы пересчитать вручную, введи PAX (например <code>22</code> или <code>22/0/0</code>):"
    )

    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отмена")

    await state.set_state(PierManagerStates.envelope_calc)
    await message.answer(report, parse_mode="HTML", reply_markup=builder.as_markup(resize_keyboard=True))


@router.message(PierManagerStates.envelope_calc, F.text == "❌ Отмена")
async def ops_envelope_cancel(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier", "—")
    await state.set_state(PierManagerStates.pier_ops)
    await show_pier_ops_menu(message, pier)


@router.message(PierManagerStates.envelope_calc, F.text.regexp(r"^\d+(/\d+(/\d+)?)?$"))
async def ops_envelope_calc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier", "—")
    now = get_phuket_now()
    is_sunday = now.weekday() == 6

    # Parse PAX
    parts = message.text.strip().split("/")
    try:
        adults   = int(parts[0]) if len(parts) > 0 else 0
        children = int(parts[1]) if len(parts) > 1 else 0
        infants  = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        await message.answer("❌ Неверный формат. Введи <code>22/0/0</code> или <code>22</code>", parse_mode="HTML")
        return

    date_str = now.strftime("%d.%m.%Y")
    day_label = "⚠️ ВОСКРЕСЕНЬЕ" if is_sunday else now.strftime("%A")

    report = (
        f"📩 <b>Конверты NP — {pier} ({date_str})</b>\n"
        f"👥 PAX: <code>{adults}/{children}/{infants}</code>  |  {day_label}\n"
        f"──────────────────\n"
    )

    grand_total = 0
    for code in ["PP", "JB", "HG"]:
        fee = NP_FEES[code]
        total, formula = calc_envelope(code, adults, children, is_sunday)
        grand_total += total
        report += f"{fee['emoji']} <b>{fee['name']}</b>\n"
        report += f"  {formula}\n"
        report += f"  💵 <b>{total:,}฿</b>\n"
        report += "──────────────────\n"

    report += f"💼 Итого в конвертах: <b>{grand_total:,}฿</b>"

    await message.answer(report, parse_mode="HTML")
    # Stay in envelope_calc state so user can try different PAX

# ─────────────────────────────────────────────────────────────────────────────
# OPS: 📊 Итоги дня
# ─────────────────────────────────────────────────────────────────────────────

def _sum_pax(pax_str: str) -> int:
    """Sums A/C/I pax string. Returns 0 on error."""
    try:
        if "/" in pax_str:
            parts = pax_str.split("/")
            return sum(int(p.strip()) for p in parts if p.strip().isdigit())
        elif pax_str.strip().isdigit():
            return int(pax_str.strip())
    except Exception:
        pass
    return 0


@router.message(PierManagerStates.pier_ops, F.text == "📊 Итоги дня")
async def ops_daily_summary(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier", "—")
    target_date = get_phuket_now().date()
    date_str = target_date.strftime("%d.%m.%Y")

    await message.answer(f"⏳ Собираю итоги для пирса <b>{pier}</b>...", parse_mode="HTML")

    plans = await sea_plan_service.get_pier_detailed_plan(pier, target_date)

    if not plans:
        await message.answer(f"❌ Данных для пирса <b>{pier}</b> на <b>{date_str}</b> не найдено.", parse_mode="HTML")
        return

    total_a, total_c, total_i = 0, 0, 0
    total_boats = len(plans)
    boats_lines = []

    for plan in sorted(plans, key=lambda x: x.boat):
        pa, pc, pi = 0, 0, 0
        try:
            parts = plan.pax_string.split("/")
            pa = int(parts[0]) if parts[0].isdigit() else 0
            pc = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            pi = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        except Exception:
            pass
        total_a += pa
        total_c += pc
        total_i += pi
        boat_total = pa + pc + pi
        boats_lines.append(f"  🚢 {plan.boat}: <code>{plan.pax_string}</code> ({boat_total} чел.)")

    grand_total = total_a + total_c + total_i

    report = (
        f"📊 <b>Итоги дня — {pier} ({date_str})</b>\n"
        f"──────────────────\n"
    )
    report += "\n".join(boats_lines) + "\n"
    report += (
        f"──────────────────\n"
        f"🚢 Лодок: <b>{total_boats}</b>\n"
        f"👥 PAX:  A=<b>{total_a}</b>  C=<b>{total_c}</b>  I=<b>{total_i}</b>\n"
        f"🎯 Всего туристов: <b>{grand_total}</b>"
    )

    await message.answer(report, parse_mode="HTML")

# ─────────────────────────────────────────────────────────────────────────────
# OPS: ⛴ Лодки / 👤 Гиды сегодня (inside pier_ops state)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.pier_ops, F.text.in_(["⛴ Лодки сегодня", "👤 Гиды сегодня"]))
async def ops_boats_or_guides(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier", "—")
    target_date = get_phuket_now().date()
    date_str = target_date.strftime("%d.%m.%Y")
    is_boats = "Лодки" in message.text

    await message.answer(f"⏳ Загружаю данные из Google Таблицы на {date_str}...")

    plans = await sea_plan_service.get_pier_detailed_plan(pier, target_date)

    if not plans:
        await message.answer(f"❌ Данных для пирса <b>{pier}</b> на <b>{date_str}</b> не найдено.", parse_mode="HTML")
        return

    if is_boats:
        report = f"⛴ <b>Лодки на пирсе {pier} ({date_str}):</b>\n\n"
        for p in sorted(plans, key=lambda x: x.boat):
            progs = ", ".join([prog.name for prog in p.programs])
            guides = ", ".join([g.full_info for g in p.guides])
            report += f"🚢 <b>{p.boat}</b>\n"
            report += f"📝 Программы: {progs}\n"
            report += f"👥 PAX: <code>{p.pax_string}</code>\n"
            report += f"👤 Гиды: {guides}\n"
            if p.thai_guide:
                report += f"🇹🇭 Тай. гид: {p.thai_guide}\n"
            report += "──────────────────\n"
    else:
        report = f"👤 <b>Гиды на пирсе {pier} ({date_str}):</b>\n\n"
        unique_guides: dict[str, list] = {}
        for p in plans:
            for g in p.guides:
                if g.full_info not in unique_guides:
                    unique_guides[g.full_info] = []
                unique_guides[g.full_info].append(p.boat)
        if not unique_guides:
            report += "Гиды не найдены."
        else:
            for guide, boats in sorted(unique_guides.items()):
                report += f"👤 {guide}\n🚢 Лодки: {', '.join(boats)}\n\n"

    for x in range(0, len(report), 4000):
        await message.answer(report[x:x+4000], parse_mode="HTML")

# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.dashboard, F.text == "🔄 Сменить пирс")
async def cmd_change_pier(message: types.Message, state: FSMContext):
    await cmd_pier_manager_dashboard(message, state)


@router.message(PierManagerStates.pier_ops, F.text == "🔙 К выбору пирса")
async def ops_back_to_pier_select(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier", "—")
    await state.set_state(PierManagerStates.dashboard)
    await show_pier_dashboard(message, pier)


@router.message(F.text == "🔙 Главное меню", RoleFilter(ALLOWED_ROLES))
async def back_to_main_menu_pier(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.common import cmd_start
    await cmd_start(message)
