from aiogram import Router, types, F, html
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from config import config
from services.sea_plan import sea_plan_service
from services.translator import translate_to_english
from utils.time import get_phuket_now, get_phuket_today
from loguru import logger
import datetime

router = Router()

class HelpStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_detail = State() # Guests -> Booking, Transport -> Vehicle
    waiting_for_description = State()

HELP_CATEGORIES = {
    "guests": "👥 Гости",
    "transport": "🚐 Транспорт",
    "route": "🗺 Маршрут",
    "other": "💡 Другое"
}

@router.message(F.text == "/get_id")
async def cmd_get_id(message: types.Message):
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    text = (f"🆔 <b>Chat ID:</b> <code>{chat_id}</code>\n"
            f"🧵 <b>Thread ID (Topic):</b> <code>{thread_id}</code>")
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "🆘 Нужна помощь")
async def cmd_help(message: types.Message, state: FSMContext):
    # Keep simulation data if already set
    data = await state.get_data()
    is_test = data.get("is_test", False)
    proxy_username = data.get("proxy_username")
    
    await state.clear()
    
    if is_test:
        await state.update_data(is_test=True, proxy_username=proxy_username)
    
    builder = InlineKeyboardBuilder()
    for key, label in HELP_CATEGORIES.items():
        builder.button(text=label, callback_data=f"help_cat_{key}")
    builder.adjust(2)
    
    await message.answer(
        "🆘 <b>НУЖНА ПОМОЩЬ</b>\n\n"
        "Выберите категорию проблемы для более быстрого решения:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(HelpStates.waiting_for_category)

@router.callback_query(F.data.startswith("help_cat_"))
async def process_help_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("help_cat_", "")
    await state.update_data(category=category)
    
    state_data = await state.get_data()
    proxy_username = state_data.get("proxy_username")
    username = proxy_username or callback.from_user.username or str(callback.from_user.id)
    today = get_phuket_today()
    
    if category == "guests":
        await callback.message.edit_text(f"🔍 Ищу данные по гостям (@{username}) на сегодня...")
        
        # Fetch programs first
        sea_plans = await sea_plan_service.get_guide_sea_plan(username, today)
        land_plans = await sea_plan_service.get_guide_land_plan(username, today)
        
        program_names = []
        for p in sea_plans:
            for prog in p.programs: program_names.append(prog.name)
        for p in land_plans: program_names.append(p.program)
        
        if not program_names:
            await callback.message.answer(f"❌ У @{username} нет активных программ на сегодня в плане. Введите данные гостя вручную в описании проблемы.")
            await callback.message.answer("📝 Опишите проблему (Ваучер, Имя, Агент и суть проблемы):")
            await state.set_state(HelpStates.waiting_for_description)
            return

        guests = await sea_plan_service.get_guest_list(today, program_names)
        
        if not guests:
            await callback.message.answer(f"❌ Список гостей для @{username} в плане пуст. Введите данные вручную.")
            await callback.message.answer("📝 Опишите проблему:")
            await state.set_state(HelpStates.waiting_for_description)
            return
            
        builder = InlineKeyboardBuilder()
        # Limit to 15 guests to avoid keyboard limit
        for i, g in enumerate(guests[:15]):
            label = f"{g.voucher} - {g.name[:15]}"
            builder.button(text=label, callback_data=f"help_guest_{i}")
        
        builder.button(text="➕ Ввести вручную", callback_data="help_guest_manual")
        builder.adjust(1)
        
        await state.update_data(temp_guests=[{
            "voucher": g.voucher, "name": g.name, "agent": g.agent, "hotel": g.hotel, "pax": g.pax, "program": g.program
        } for g in guests[:15]])
        
        await callback.message.edit_text(
            f"👥 <b>ВЫБОР ГОСТЯ (@{username})</b>\n\n"
            "Выберите из списка или введите данные вручную:",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await state.set_state(HelpStates.waiting_for_detail)
        
    elif category == "transport":
        # Check Sea or Land
        sea_plans = await sea_plan_service.get_guide_sea_plan(username, today)
        land_plans = await sea_plan_service.get_guide_land_plan(username, today)
        
        builder = InlineKeyboardBuilder()
        vehicles = []
        
        for p in sea_plans:
            vehicles.append({"type": "Лодка", "name": p.boat, "pier": p.pier})
        for p in land_plans:
            vehicles.append({"type": "Авто", "name": p.bus or "N/A", "driver": p.driver or "N/A"})
            
        if vehicles:
            for i, v in enumerate(vehicles):
                label = f"{v['type']}: {v['name']}"
                builder.button(text=label, callback_data=f"help_trans_{i}")
            await state.update_data(temp_vehicles=vehicles)
        
        builder.button(text="➕ Другой транспорт", callback_data="help_trans_manual")
        builder.adjust(1)
        
        await callback.message.edit_text(
            f"🚐 <b>ВЫБОР ТРАНСПОРТА (@{username})</b>\n\n"
            "Выберите транспорт из программы или укажите другой:",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await state.set_state(HelpStates.waiting_for_detail)
        
    else:
        # Route or Other
        cat_name = HELP_CATEGORIES.get(category, "Проблема")
        prompt = f"📝 <b>Опишите суть проблемы подробно (от лица @{username}):</b>" if proxy_username else "📝 <b>Опишите суть проблемы подробно:</b>"
        await callback.message.edit_text(
            f"{cat_name}\n\n{prompt}",
            parse_mode="HTML"
        )
        await state.set_state(HelpStates.waiting_for_description)

@router.callback_query(HelpStates.waiting_for_detail, F.data.startswith("help_guest_"))
async def process_help_guest_detail(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx_str = callback.data.replace("help_guest_", "")
    
    if idx_str == "manual":
        detail_info = "Введено вручную"
    else:
        idx = int(idx_str)
        g = data["temp_guests"][idx]
        detail_info = (
            f"🎫 Ваучер: {g['voucher']}\n"
            f"👤 Гость: {g['name']}\n"
            f"🏢 Отель: {g['hotel']}\n"
            f"🤝 Агент: {g['agent']}\n"
            f"📦 Пакс: {g['pax']}\n"
            f"🗓 Программа: {g['program']}"
        )
    
    await state.update_data(detail_info=detail_info)
    await callback.message.edit_text(
        "📝 <b>Опишите саму проблему:</b>\n"
        "(Например: гость не вышел, нет ваучера, ошибка в данных)",
        parse_mode="HTML"
    )
    await state.set_state(HelpStates.waiting_for_description)

@router.callback_query(HelpStates.waiting_for_detail, F.data.startswith("help_trans_"))
async def process_help_trans_detail(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx_str = callback.data.replace("help_trans_", "")
    
    if idx_str == "manual":
        detail_info = "Другой транспорт (введите в описании)"
    else:
        idx = int(idx_str)
        v = data["temp_vehicles"][idx]
        if v["type"] == "Лодка":
            detail_info = f"🚢 Лодка: {v['name']} (Пирс: {v['pier']})"
        else:
            detail_info = f"🚐 Авто: {v['name']} (Водитель: {v['driver']})"
            
    await state.update_data(detail_info=detail_info)
    await callback.message.edit_text(
        "📝 <b>Опишите проблему с транспортом:</b>\n"
        "(Например: поломка, задержка, грязный салон)",
        parse_mode="HTML"
    )
    await state.set_state(HelpStates.waiting_for_description)

@router.message(HelpStates.waiting_for_description)
async def process_help_description(message: types.Message, state: FSMContext):
    description = message.text
    data = await state.get_data()
    category = data.get("category")
    cat_label = HELP_CATEGORIES.get(category, "🆘 Помощь")
    detail_info = data.get("detail_info", "---")
    is_test = data.get("is_test", False)
    proxy_username = data.get("proxy_username")
    
    await message.answer("⏳ Перевожу и отправляю запрос на горячую линию...")
    
    # 1. Translate
    translation = "---"
    try:
        translation = await translate_to_english(description)
        if not translation:
             translation = "---"
    except Exception as e:
        logger.error(f"Translation failed in Help: {e}")

    # 2. Build Notification
    username = proxy_username or message.from_user.username or str(message.from_user.id)
    guide_info = f"@{username}"
    
    # If it's a test, add banner
    test_prefix = "🚨 <b>[ТЕСТ / TEST]</b> 🚨\n\n" if is_test else ""
    if is_test:
        guide_info = f"{guide_info} (ИМИТАЦИЯ от @{message.from_user.username})"

    notification = (
        f"{test_prefix}"
        f"{cat_label}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🧭 <b>Гид:</b> {guide_info}\n"
        f"📅 <b>Дата:</b> {get_phuket_today().strftime('%d.%m')}\n"
        f"📍 <b>Контекст:</b>\n{detail_info}\n\n"
        f"❓ <b>ПРОБЛЕМА:</b>\n{description}\n\n"
        f"🇬🇧 <b>TRANSLATION:</b>\n<i>{translation}</i>\n\n"
        f"🔔 <b>Notify Hotline:</b> {config.SOS_NOTIFY_TARGET}"
    )

    # 3. Send to Topic
    try:
        await message.bot.send_message(
            chat_id=config.REPORT_GROUP_ID,
            message_thread_id=config.HELP_TOPIC_ID,
            text=notification,
            parse_mode="HTML"
        )
        success_msg = "✅ <b>ТЕСТОВЫЙ Запрос отправлен!</b>" if is_test else "✅ <b>Запрос отправлен!</b>\n\nВаше сообщение доставлено на горячую линию."
        await message.answer(success_msg, parse_mode="HTML")
        
        # Log action (only if not test, or mark as test)
        from database.db import update_user_activity
        action_name = f"SOS: {category}"
        if is_test: action_name = f"TEST_{action_name}"
        await update_user_activity(message.from_user.id, action=action_name)
        
    except Exception as e:
        logger.error(f"Failed to send Help notification: {e}")
        await message.answer("❌ Произошла ошибка при отправке сообщения.")

    await state.clear()
