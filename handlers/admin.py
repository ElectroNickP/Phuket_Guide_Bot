from utils.time import get_phuket_now, get_phuket_today
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db import AsyncSessionLocal
from database.models import User, AppSettings
from services.google_sheets import google_sheets
from sqlalchemy import select, update
from loguru import logger
from config import config
import re
import datetime
import html
from services.sea_plan import sea_plan_service


class IsAdminFilter(BaseFilter):
    """Router-level filter: silently ignores non-admin users."""
    async def __call__(self, event: types.Message | types.CallbackQuery) -> bool:
        user = event.from_user if hasattr(event, 'from_user') else None
        if not user:
            return False
            
        # Check by ID
        if user.id in config.admin_id_list:
            return True
            
        # Check by Username
        if user.username:
            return user.username.lower() in config.admin_username_list
            
        return False


class IsSuperAdminFilter(BaseFilter):
    """Router-level filter: only allows super admins (@Pankonick)."""
    async def __call__(self, event: types.Message | types.CallbackQuery) -> bool:
        user = event.from_user if hasattr(event, 'from_user') else None
        if not user or not user.username:
            return False
        return user.username.lower() == "pankonick"


router = Router()
# Apply admin guard to ALL message and callback handlers in this router
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

class AdminStates(StatesGroup):
    waiting_for_spreadsheet_id = State()
    waiting_for_sea_spreadsheet_id = State()
    waiting_for_monitor_username = State()
    waiting_for_land_monitor_username = State()
    waiting_for_guide_name_sea = State()

@router.message(F.text == "🔗 Сменить таблицу", IsSuperAdminFilter())
async def cmd_set_sheet_kb(message: types.Message, state: FSMContext):
    await message.answer("📝 Пришли мне URL или ID новой Google таблицы:")
    await state.set_state(AdminStates.waiting_for_spreadsheet_id)

@router.message(AdminStates.waiting_for_spreadsheet_id, IsSuperAdminFilter())
async def process_sheet_url(message: types.Message, state: FSMContext):
    raw_input = message.text
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", raw_input)
    sheet_id = match.group(1) if match else raw_input

    async with AsyncSessionLocal() as session:
        query = select(AppSettings).where(AppSettings.key == "spreadsheet_id")
        result = await session.execute(query)
        setting = result.scalar_one_or_none()
        
        if not setting:
            setting = AppSettings(key="spreadsheet_id", value=sheet_id)
            session.add(setting)
        else:
            setting.value = sheet_id
            
        await session.commit()
    
    # Reload spreadsheet in service
    try:
        await google_sheets.get_spreadsheet()
        await message.answer(f"✅ Таблица успешно обновлена и подгружена!\nID: <code>{sheet_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при подгрузке таблицы: {e}")
        
    await state.clear()

@router.message(F.text == "🔗 Сменить таблицу (Море)", IsSuperAdminFilter())
async def cmd_set_sea_sheet_kb(message: types.Message, state: FSMContext):
    await message.answer("📝 Пришли мне URL или ID новой Google таблицы (ПЛАН НА МОРЕ):")
    await state.set_state(AdminStates.waiting_for_sea_spreadsheet_id)

@router.message(AdminStates.waiting_for_sea_spreadsheet_id, IsSuperAdminFilter())
async def process_sea_sheet_url(message: types.Message, state: FSMContext):
    raw_input = message.text
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", raw_input)
    sheet_id = match.group(1) if match else raw_input

    async with AsyncSessionLocal() as session:
        query = select(AppSettings).where(AppSettings.key == "sea_spreadsheet_id")
        result = await session.execute(query)
        setting = result.scalar_one_or_none()
        
        if not setting:
            setting = AppSettings(key="sea_spreadsheet_id", value=sheet_id)
            session.add(setting)
        else:
            setting.value = sheet_id
            
        await session.commit()
    
    # Reload in service
    from services.sea_plan import sea_plan_service
    try:
        await sea_plan_service.get_spreadsheet()
        await message.answer(f"✅ Таблица (Море) успешно обновлена!\nID: <code>{sheet_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при подгрузке таблицы (Море): {e}")
        
    await state.clear()

@router.message(F.text == "📋 Логи", IsSuperAdminFilter())
async def cmd_logs_kb(message: types.Message):
    try:
        with open("logs/bot.log", "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        # Show last 30 lines, filter to anything WARNING or above for compact view
        last_lines = lines[-30:]
        log_text = "".join(last_lines)
        
        # Telegram limit: 4096 chars. Truncate from the start if too long.
        if len(log_text) > 3500:
            log_text = "..." + log_text[-3500:]
        
        await message.answer(
            f"📋 <b>Последние 30 строк логов:</b>\n\n<code>{html.escape(log_text)}</code>",
            parse_mode="HTML"
        )
    except FileNotFoundError:
        await message.answer("⚠️ Файл логов не найден. Бот ещё ничего не записал в файл.")
    except Exception as e:
        logger.exception(f"Error reading logs: {e}")
        await message.answer(f"❌ Ошибка при чтении логов: {e}")

@router.message(F.text == "👁 Мониторинг гидов")
async def cmd_monitor_guides(message: types.Message, state: FSMContext):
    await message.answer("👥 Введи username гида (через @), чье расписание ты хочешь посмотреть:")
    await state.set_state(AdminStates.waiting_for_monitor_username)

@router.message(AdminStates.waiting_for_monitor_username)
async def process_guide_monitor(message: types.Message, state: FSMContext):
    target_username = message.text.replace("@", "").strip()
    
    sheet = await google_sheets.get_current_month_sheet()
    if not sheet:
        await message.answer("❌ Не удалось найти лист с расписанием.")
        await state.clear()
        return

    staff, freelance = await google_sheets.parse_guides(sheet)
    all_guides = staff + freelance
    guide_info = next((g for g in all_guides if g['username'].lower() == target_username.lower()), None)

    if not guide_info:
        await message.answer(f"❌ Гид @{target_username} не найден в таблице.")
    else:
        # Show today/tomorrow schedule for this guide
        today = get_phuket_now().day
        tomorrow = (get_phuket_now() + datetime.timedelta(days=1)).day
        
        sched_today = await google_sheets.get_guide_schedule(sheet, guide_info['row'], day=today)
        sched_tomorrow = await google_sheets.get_guide_schedule(sheet, guide_info['row'], day=tomorrow)
        
        type_str = "Штат" if guide_info['type'] == "staff" else "Фриланс"
        
        await message.answer(
            f"👁 <b>Архив/Мониторинг: @{target_username}</b> ({type_str})\n\n"
            f"📅 Сегодня ({today}): <b>{sched_today or '---'}</b>\n"
            f"📅 Завтра ({tomorrow}): <b>{sched_tomorrow or '---'}</b>",
            parse_mode="HTML"
        )
    
    await state.clear()

@router.message(F.text == "🌊 Мониторинг моря")
async def cmd_monitor_sea_guides(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Сегодня", callback_data="admsea_date_today")
    builder.button(text="📅 Завтра", callback_data="admsea_date_tomorrow")
    builder.adjust(2)
    
    await message.answer(
        "🌊 <b>Мониторинг моря</b>\n\nВыберите дату для просмотра списка работающих гидов:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await state.clear()

@router.callback_query(F.data.startswith("admsea_date_"))
async def process_admin_sea_date_select(callback: types.CallbackQuery, state: FSMContext):
    is_today = "today" in callback.data
    target_date = get_phuket_today() if is_today else get_phuket_today() + datetime.timedelta(days=1)
    date_str = target_date.strftime("%d.%m")
    
    await callback.answer(f"Ищу гидов на {date_str}...")
    active_guides = await sea_plan_service.get_active_sea_guides([target_date])
    
    if active_guides:
        builder = InlineKeyboardBuilder()
        for uname in active_guides:
            builder.button(text=f"👤 @{uname}", callback_data=f"admsea_user_{date_str}_{uname}")
        builder.adjust(2)
        await callback.message.answer(
            f"🌊 <b>Работающие на море ({date_str}):</b>\n"
            "Выберите гида для просмотра морского плана:",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.answer(
            f"🌊 На {date_str} активных гидов в морской программе не найдено.\n"
            "Вы можете ввести username вручную (например, @username):"
        )
        await state.set_state(AdminStates.waiting_for_guide_name_sea)
        await state.update_data(target_date=target_date.isoformat())

@router.callback_query(F.data.startswith("admsea_user_"))
async def process_admin_sea_user_select(callback: types.CallbackQuery):
    # data: admsea_user_{date_str}_{username}
    parts = callback.data.split("_", 3)
    date_str = parts[2]
    username = parts[3]
    
    target_date = datetime.datetime.strptime(f"{date_str}.{get_phuket_today().year}", "%d.%m.%Y").date()
    
    await callback.answer(f"Загружаю @{username}...")
    await _send_admin_sea_plans_single(username, target_date, callback.message)

async def _send_admin_sea_plans_single(target_username: str, date: datetime.date, message: types.Message):
    """Helper to fetch and send sea plans for a specific guide and date"""
    date_str = date.strftime("%d.%m")
    try:
        plans = await sea_plan_service.get_guide_sea_plan(target_username, date)
        if plans:
            day_response = f"👁 <b>Архив/Мониторинг МОРЕ: @{target_username}</b>\n\n"
            day_response += f"📅 <b>Дата: {date_str}</b>\n"
            for plan in plans:
                day_response += f"🚢 <b>Лодка:</b> {plan['boat']}\n"
                day_response += f"⚓️ <b>Пирс:</b> {plan['pier'] or '---'}\n"
                day_response += f"👤 <b>Thai Guide:</b> {plan['thai_guide'] or '---'}\n"
                day_response += f"👥 <b>Гид(ы):</b> {', '.join(plan['guides_list'])}\n"
                day_response += f"📝 <b>Программы:</b>\n"
                for prog in plan['programs']:
                    prog_text = f"{prog['name']} ({prog['pax']} pax)"
                    if len(plan['guides_list']) > 1 and prog.get('short_guide'):
                        prog_text += f" - {prog['short_guide']}"
                    day_response += f"  • {prog_text}\n"
                day_response += f"📊 <b>Total Pax:</b> {plan['total_pax']}\n"
            
            builder = InlineKeyboardBuilder()
            builder.button(text="📋 Список гостей", callback_data=f"guestlist_admin_{date_str}_{target_username}")
            await message.answer(day_response, parse_mode="HTML", reply_markup=builder.as_markup())
        else:
            await message.answer(f"❌ План на море для @{target_username} на {date_str} не найден.")
    except Exception as e:
        logger.error(f"Error in admin sea monitor single for {target_username} on {date_str}: {e}")
        await message.answer(f"❌ Произошла ошибка при получении плана для @{target_username} на {date_str}.")

async def _send_admin_sea_plans(target_username: str, message: types.Message):
    """Legacy helper (Today and Tomorrow) for manual entry with no state"""
    today = get_phuket_now().date()
    tomorrow = today + datetime.timedelta(days=1)
    found_any = False
    for date in [today, tomorrow]:
        plans = await sea_plan_service.get_guide_sea_plan(target_username, date)
        if plans:
            found_any = True
            await _send_admin_sea_plans_single(target_username, date, message)
    if not found_any:
        await message.answer(f"❌ План на море для @{target_username} на сегодня/завтра не найден.")

@router.callback_query(F.data.startswith("admsea_"))
async def process_admin_sea_guide_select_legacy(callback: types.CallbackQuery, state: FSMContext):
    # Fallback for old style buttons
    target_username = callback.data.split("_", 1)[1]
    await callback.answer(f"Выбран @{target_username}")
    await _send_admin_sea_plans(target_username, callback.message)
    await state.clear()

@router.message(F.text == "🚐 Мониторинг суши")
async def cmd_monitor_land(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Сегодня", callback_data="admland_date_today")
    builder.button(text="📅 Завтра", callback_data="admland_date_tomorrow")
    builder.adjust(2)
    
    await message.answer(
        "🚐 <b>Мониторинг суши</b>\n\nВыберите дату для просмотра списка работающих гидов:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await state.clear()

@router.callback_query(F.data.startswith("admland_date_"))
async def process_admin_land_date_select(callback: types.CallbackQuery, state: FSMContext):
    is_today = "today" in callback.data
    target_date = get_phuket_today() if is_today else get_phuket_today() + datetime.timedelta(days=1)
    date_str = target_date.strftime("%d.%m")
    
    await callback.answer(f"Ищу гидов на {date_str}...")
    active_guides = await sea_plan_service.get_active_land_guides([target_date])
    
    if active_guides:
        builder = InlineKeyboardBuilder()
        for uname in active_guides:
            builder.button(text=f"👤 @{uname}", callback_data=f"admland_user_{date_str}_{uname}")
        builder.adjust(2)
        await callback.message.answer(
            f"🚐 <b>Гиды переведенные на сушу ({date_str}):</b>\n"
            "Выберите гида для просмотра Job Order:",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.answer(
            f"🚐 На {date_str} активных гидов в наземной программе не найдено.\n"
            "Вы можете ввести username вручную (например, @username):"
        )
        await state.set_state(AdminStates.waiting_for_land_monitor_username)
        await state.update_data(target_date=target_date.isoformat())

@router.callback_query(F.data.startswith("admland_user_"))
async def process_admin_land_user_select(callback: types.CallbackQuery):
    # data: admland_user_{date_str}_{username}
    parts = callback.data.split("_", 3)
    date_str = parts[2]
    username = parts[3]
    
    target_date = datetime.datetime.strptime(f"{date_str}.{get_phuket_today().year}", "%d.%m.%Y").date()
    
    await callback.answer(f"Загружаю @{username}...")
    plans = await sea_plan_service.get_guide_land_plan(username, target_date)
    await _send_admin_land_plans(username, target_date, plans, callback.message)

@router.callback_query(F.data.startswith("admland_"))
async def process_admin_land_guide_select_legacy(callback: types.CallbackQuery, state: FSMContext):
    # Fallback for old buttons if any exist
    username = callback.data.split("_", 1)[1]
    await callback.answer(f"Выбран @{username}")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Сегодня", callback_data=f"admin_land_today_{username}")
    builder.button(text="Завтра", callback_data=f"admin_land_tomorrow_{username}")
    builder.adjust(2)
    
    await callback.message.answer(f"🚐 План на суше для @{username}:", reply_markup=builder.as_markup())
    await state.clear()

@router.message(AdminStates.waiting_for_guide_name_sea)
async def process_guide_monitor_sea(message: types.Message, state: FSMContext):
    target_username = message.text.replace("@", "").strip()
    data = await state.get_data()
    saved_date = data.get("target_date")
    
    await state.clear()
    
    if saved_date:
        target_date = datetime.date.fromisoformat(saved_date)
        await _send_admin_sea_plans_single(target_username, target_date, message)
    else:
        await _send_admin_sea_plans(target_username, message)

@router.message(AdminStates.waiting_for_land_monitor_username)
async def process_guide_monitor_land(message: types.Message, state: FSMContext):
    username = message.text.replace("@", "").strip()
    data = await state.get_data()
    saved_date = data.get("target_date")
    
    await state.clear()
    
    if saved_date:
        target_date = datetime.date.fromisoformat(saved_date)
        plans = await sea_plan_service.get_guide_land_plan(username, target_date)
        await _send_admin_land_plans(username, target_date, plans, message)
    else:
        # Fallback to choosing date
        builder = InlineKeyboardBuilder()
        builder.button(text="Сегодня", callback_data=f"admin_land_today_{username}")
        builder.button(text="Завтра", callback_data=f"admin_land_tomorrow_{username}")
        builder.adjust(2)
        await message.answer(f"🚐 Выберите дату для @{username}:", reply_markup=builder.as_markup())

async def _send_admin_land_plans(username: str, target_date: datetime.date, plans: list, message: types.Message):
    """Helper to format and send land plans in Admin view"""
    if not plans:
        await message.answer(f"🚐 План на суше для @{username} не найден на {target_date.strftime('%d.%m')}.")
        return

    for plan in plans:
        response = f"🚐 <b>ADMIN VIEW: @{username}</b>\n"
        response += f"🔹 <b>Program: {plan['program']}</b>\n"
        response += f"📅 <b>Date:</b> {plan['date']}\n\n"
        
        if plan['guides']:
            response += "👤 <b>Guide(s):</b>\n"
            for g in plan['guides']:
                response += f"  • {g['full_info']} (P/U: {g['pickup_time']} @ {g['pickup_location']})\n"
            response += "\n"
            
        if plan['bus']:
            response += f"🚌 <b>Bus:</b> <code>{plan['bus']}</code>\n"
        if plan['driver']:
            response += f"👨‍✈️ <b>Driver:</b> {plan['driver']}\n"
        
        if plan['guests']:
            response += "\n👥 <b>Guest List:</b>\n\n"
            for g in plan['guests']:
                response += f"  • <b>V/C:</b> <code>{g['voucher']}</code> | <b>Pax:</b> {g['pax']}\n"
                response += f"    <b>Pickup:</b> {g['pickup']}\n"
                response += f"    <b>Hotel:</b> {g['hotel']} ({g['area']}) (RM: {g['room']})\n"
                response += f"    <b>Name:</b> <code>{g['name']}</code>\n"
                if g['phone'] and g['phone'] != "-":
                    response += f"    <b>Phone:</b> <code>{g['phone']}</code>\n"
                if g['remarks'] and g['remarks'] != "-":
                    response += f"    <b>Remarks:</b> {g['remarks']}\n"
                response += f"    💰 <b>COT:</b> <code>{g['cot']}</code>\n"
                response += "\n"
        
        await message.answer(response, parse_mode="HTML")

@router.message(F.text == "📊 Статистика")
async def cmd_stats_kb(message: types.Message):
    async with AsyncSessionLocal() as session:
        # Get all users
        query_total = select(User)
        result_total = await session.execute(query_total)
        users = result_total.scalars().all()
        
        # Get interval from DB or config
        query_int = select(AppSettings).where(AppSettings.key == "polling_interval")
        res_int = await session.execute(query_int)
        setting_int = res_int.scalar_one_or_none()
        current_interval = int(setting_int.value) if setting_int else config.POLLING_INTERVAL
        
        # Sort users by activity: sum of all counters
        users_sorted = sorted(
            users, 
            key=lambda u: (u.count_today or 0) + (u.count_tomorrow or 0) + (u.count_sea_today or 0) + (u.count_sea_tomorrow or 0) + (u.count_feedback or 0) + (u.count_status or 0) + (u.count_start or 0),
            reverse=True
        )
        
        user_list_str = ""
        for u in users_sorted:
            last_contact_str = u.last_contact.strftime("%d.%m %H:%M") if u.last_contact else "---"
            total_act = (u.count_today or 0) + (u.count_tomorrow or 0) + (u.count_sea_today or 0) + (u.count_sea_tomorrow or 0) + (u.count_feedback or 0) + (u.count_status or 0) + (u.count_start or 0)
            
            user_list_str += (
                f"👤 @{u.username or 'no_user'}\n"
                f"  🕒 Активен: {last_contact_str}\n"
                f"  📊 Всего: {total_act}\n"
                f"  (📅 {u.count_today}/{u.count_tomorrow} | 🌊 {u.count_sea_today}/{u.count_sea_tomorrow} | 📝 {u.count_feedback} | 👤 {u.count_status})\n\n"
            )
            
    response = (
        f"📊 <b>Детальная статистика</b>\n"
        f"⏱ Опрос: {current_interval // 60} мин.\n"
        f"👥 Всего: {len(users)}\n\n"
        f"{user_list_str if user_list_str else 'Пользователей пока нет.'}"
    )
    
    # Telegram has a limit of 4096 characters per message
    if len(response) > 4000:
        response = response[:3900] + "... (список слишком длинный)"
        
    await message.answer(response, parse_mode="HTML")

@router.message(F.text == "⏱ Интервал", IsSuperAdminFilter())
async def cmd_set_interval_kb(message: types.Message):
    from utils.keyboards import get_interval_keyboard
    await message.answer(
        "⏱ <b>Настройка интервала опроса таблицы</b>\n\n"
        "Выбери, как часто бот должен проверять изменения в расписании:",
        reply_markup=get_interval_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("setint_"), IsSuperAdminFilter())
async def process_set_interval(callback: types.CallbackQuery, bot: Bot):
    new_seconds = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        query = select(AppSettings).where(AppSettings.key == "polling_interval")
        result = await session.execute(query)
        setting = result.scalar_one_or_none()
        
        if not setting:
            setting = AppSettings(key="polling_interval", value=str(new_seconds))
            session.add(setting)
        else:
            setting.value = str(new_seconds)
        
        await session.commit()
    
    # Update scheduler dynamically
    from services.scheduler import update_scheduler_interval
    await update_scheduler_interval(bot, new_seconds)
    
    await callback.message.edit_text(f"✅ Интервал обновления изменен на {new_seconds // 60} мин.")
    await callback.answer()

@router.message(Command("admin"))
async def cmd_admin_legacy(message: types.Message):
    # This just redirects to show the keyboard if they use the command
    from utils.keyboards import get_admin_menu_keyboard
    await message.answer("🛠 Панель администратора открыта. Используй кнопки меню.", reply_markup=get_admin_menu_keyboard())

@router.callback_query(IsAdminFilter(), F.data.startswith("guestlist_admin_"))
async def process_guest_list_admin(callback: types.CallbackQuery):
    try:
        # data is guestlist_admin_dd.mm_username
        # Split but only for the first 3 underscores to keep the username (which might have underscores) intact
        parts = callback.data.split('_', 3)
        date_str = parts[2]
        tgt_username = parts[3]
        target_date = datetime.datetime.strptime(f"{date_str}.{get_phuket_today().year}", "%d.%m.%Y").date()
    except (ValueError, IndexError):
        await callback.answer("Ошибка формата данных", show_alert=True)
        return

    plans = await sea_plan_service.get_guide_sea_plan(tgt_username, target_date)
    if not plans:
        await callback.answer("Не найдено программ на эту дату.", show_alert=True)
        return

    program_names = []
    for plan in plans:
        for prog in plan['programs']:
            if prog['name'] not in program_names:
                program_names.append(prog['name'])

    if not program_names:
        await callback.answer("У гида нет программ на эту дату.", show_alert=True)
        return

    await callback.answer("Загружаю список гостей...")

    guest_list = await sea_plan_service.get_guest_list(target_date, program_names)
    
    if not guest_list:
        await callback.message.answer(f"📋 Список гостей пуст или не найден для программ: {', '.join(program_names)}")
        return

    response = f"📋 <b>Список гостей ({date_str}) для @{tgt_username}</b>:\n\n"
    
    for item in guest_list:
        pname = item['program_name']
        guests = item['guests']
        response += f"🔹 <b>Program: {pname}</b>\n"
        
        for g in guests:
            response += f"  • <b>V/C:</b> <code>{g['voucher']}</code> | <b>Pax:</b> {g['pax']}\n"
            if g['pickup']:
                response += f"    <b>Pickup:</b> {g['pickup']}\n"
            response += f"    <b>Hotel:</b> {g['hotel']} (RM: {g['room']})\n"
            response += f"    <b>Name:</b> <code>{g['name']}</code>\n"
            if g['phone']:
                response += f"    <b>Phone:</b> <code>{g['phone']}</code>\n"
            if g['remarks']:
                response += f"    <b>Remarks:</b> {g['remarks']}\n"
            response += f"    💰 <b>COT:</b> <code>{g['cot']}</code>\n"
            response += "\n"
    
    await callback.message.answer(response, parse_mode="HTML")
