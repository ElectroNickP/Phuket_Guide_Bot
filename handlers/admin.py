from utils.time import get_phuket_now, get_phuket_today
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db import AsyncSessionLocal
from database.models import User, AppSettings, UserRole
from utils.permissions import RoleFilter
from services.google_sheets import google_sheets
from sqlalchemy import select, update
from loguru import logger
from config import config
import re
import asyncio
import datetime
import html
from services.sea_plan import sea_plan_service
from services.image_generator import job_order_generator
from utils.message_utils import send_long_message
from utils.keyboards import get_job_order_date_keyboard, get_general_schedule_date_keyboard

# List of all reply keyboard buttons to prevent state hijacking
MENU_BUTTONS = [
    "📅 Моё расписание", "🌊 План на море", "🚐 План на суше", "👤 Мой статус", "📝 Обратная связь",
    "👁 Мониторинг гидов", "🌊 Мониторинга моря", "🚐 Мониторинг суши", "📊 Статистика", "🔍 Тест-Аудит", 
    "📋 Job Order", "📅 Общее расписание",
    "⏱ Интервал", "📋 Логи", "🔗 Сменить таблицу", "🔗 Сменить таблицу (Море)", "🔙 Главное меню"
]



class IsAdminFilter(BaseFilter):
    """Router-level filter: silently ignores non-admin users."""
    async def __call__(self, event: types.Message | types.CallbackQuery, **data) -> bool:
        user = event.from_user if hasattr(event, 'from_user') else None
        if not user:
            return False
            
        # Impersonation Check (Tester Mode)
        imp_user = data.get("impersonated_user")
        if imp_user:
            # If impersonating, check if the target role is an admin role
            return imp_user.get("role") in [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE, UserRole.HOT_LINE, UserRole.PIER_MANAGER]

        # Check by ID
        if user.id in config.admin_id_list:
            return True
            
        # Check by Username
        if user.username:
            uname = user.username.lower()
            return uname in config.admin_username_list or uname in config.tester_username_list
            
        return False


class IsSuperAdminFilter(BaseFilter):
    """Router-level filter: only allows super admins (@Pankonick)."""
    async def __call__(self, event: types.Message | types.CallbackQuery, **data) -> bool:
        user = event.from_user if hasattr(event, 'from_user') else None
        if not user:
            return False
            
        # Impersonation Check (Tester Mode)
        imp_user = data.get("impersonated_user")
        if imp_user:
            return imp_user.get("role") == UserRole.SUPER_ADMIN

        if not user.username:
            return False
        return user.username.lower() == "pankonick"


# Role definition groups for cleaner filters
ADMIN_ALL = [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE, UserRole.HOT_LINE, UserRole.PIER_MANAGER]
ADMIN_MANAGEMENT = [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE]
SYSTEM_ADMIN = [UserRole.SUPER_ADMIN]

router = Router()
# Apply admin guard to ALL message and callback handlers in this router
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

class IsTesterFilter(BaseFilter):
    """Only allowing authorized testers."""
    async def __call__(self, event: types.Message | types.CallbackQuery) -> bool:
        user = event.from_user
        if not user or not user.username:
            return False
        return user.username.lower() in config.tester_username_list

class AdminStates(StatesGroup):
    waiting_for_spreadsheet_id = State()
    waiting_for_sea_spreadsheet_id = State()
    waiting_for_monitor_username = State()
    waiting_for_land_monitor_username = State()
    waiting_for_guide_name_sea = State()
    waiting_for_job_order_guide = State()

@router.message(F.text == "🔗 Сменить таблицу", RoleFilter(SYSTEM_ADMIN))
async def cmd_set_sheet_kb(message: types.Message, state: FSMContext):
    await message.answer("📝 Пришли мне URL или ID новой Google таблицы:")
    await state.set_state(AdminStates.waiting_for_spreadsheet_id)

@router.message(AdminStates.waiting_for_spreadsheet_id, IsSuperAdminFilter(), ~F.text.in_(MENU_BUTTONS))
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

@router.message(F.text == "🔗 Сменить таблицу (Море)", RoleFilter(SYSTEM_ADMIN))
async def cmd_set_sea_sheet_kb(message: types.Message, state: FSMContext):
    await message.answer("📝 Пришли мне URL или ID новой Google таблицы (ПЛАН НА МОРЕ):")
    await state.set_state(AdminStates.waiting_for_sea_spreadsheet_id)

@router.message(AdminStates.waiting_for_sea_spreadsheet_id, IsSuperAdminFilter(), ~F.text.in_(MENU_BUTTONS))
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

@router.message(F.text == "📋 Логи", RoleFilter(SYSTEM_ADMIN))
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

class AdminReportStates(StatesGroup):
    waiting_for_username = State()

@router.message(F.text == "📝 Отчет за гида", RoleFilter(ADMIN_MANAGEMENT))
async def cmd_admin_report_proxy(message: types.Message, state: FSMContext):
    await message.answer("👥 Введите <b>@username</b> гида, за которого нужно сдать отчет:", parse_mode="HTML")
    await state.set_state(AdminReportStates.waiting_for_username)

@router.message(AdminReportStates.waiting_for_username)
async def process_admin_report_username(message: types.Message, state: FSMContext):
    username = message.text.strip().replace("@", "")
    await state.update_data(proxy_username=username)
    
    # We trigger the same start_report flow but with proxy_username in data
    from handlers.guide import ReportStates, get_report_date_keyboard
    await message.answer(
        f"👤 Вы сдаете отчет за <b>@{username}</b>.\n\n"
        "Для какого дня создать отчет?",
        parse_mode="HTML",
        reply_markup=get_report_date_keyboard()
    )
    await state.set_state(ReportStates.waiting_for_report_date)

@router.message(F.text == "👁 Мониторинг гидов", RoleFilter(ADMIN_ALL))
async def cmd_monitor_guides(message: types.Message, state: FSMContext):
    await message.answer("👥 Введи username гида (через @), чье расписание ты хочешь посмотреть:")
    await state.set_state(AdminStates.waiting_for_monitor_username)

@router.message(AdminStates.waiting_for_monitor_username, ~F.text.in_(MENU_BUTTONS))
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

@router.message(F.text == "🌊 Мониторинг моря", RoleFilter(ADMIN_ALL))
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
                day_response += f"🚢 <b>Лодка:</b> {plan.boat}\n"
                day_response += f"⚓️ <b>Пирс:</b> {plan.pier or '---'}\n"
                day_response += f"👤 <b>Thai Guide:</b> {plan.thai_guide or '---'}\n"
                day_response += f"👥 <b>Гид(ы):</b> {', '.join([g.full_info for g in plan.guides])}\n"
                day_response += f"📝 <b>Программы:</b>\n"
                for prog in plan.programs:
                    prog_text = f"{prog.name} ({prog.pax} pax)"
                    if len(plan.guides) > 1 and prog.short_guide:
                        prog_text += f" - {prog.short_guide}"
                    day_response += f"  • {prog_text}\n"
                day_response += f"📊 <b>GRAND TOTAL:</b> {plan.total_pax}\n"
            
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

@router.message(F.text == "🚐 Мониторинг суши", RoleFilter(ADMIN_ALL))
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

@router.message(AdminStates.waiting_for_guide_name_sea, ~F.text.in_(MENU_BUTTONS))
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

@router.message(AdminStates.waiting_for_land_monitor_username, ~F.text.in_(MENU_BUTTONS))
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

@router.message(F.text == "📋 Job Order", RoleFilter(ADMIN_MANAGEMENT))
async def cmd_job_order_menu(message: types.Message):
    """Ask for date first"""
    await message.answer(
        "📅 <b>Job Order</b>\nВыберите дату, за которую хотите посмотреть список:",
        reply_markup=get_job_order_date_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("jo_date_"))
async def process_job_order_date(callback: types.CallbackQuery):
    date_type = callback.data.replace("jo_date_", "")
    now = get_phuket_now().date()
    target_date = now if date_type == "today" else now + datetime.timedelta(days=1)
    date_str = target_date.strftime('%d.%m')

    guides_with_work = set() # (username, display, type)
    
    try:
        # Load all valid guides from BTC Schedule for filtering and categorization
        guide_type_map = {} # username -> type
        btc_sheet = await google_sheets.get_current_month_sheet()
        if btc_sheet:
            staff, freelance = await google_sheets.parse_guides(btc_sheet)
            for g in staff: guide_type_map[g['username'].lower()] = 'staff'
            for g in freelance: guide_type_map[g['username'].lower()] = 'freelance'

        values = await sea_plan_service._get_worksheet_values(target_date)
        if not values:
            await callback.message.edit_text(f"📭 Лист на {date_str} пуст или не найден.")
            return

        # Scan ALL rows and ALL columns for @usernames
        for row in values:
            row_str = " ".join([str(v) for v in row if v])
            if "@" in row_str:
                matches = re.findall(r'([^@|,\t\n\r]+)?(@\w+)', row_str)
                for display, uname in matches:
                    u = uname.replace("@", "").lower().strip()
                    
                    # FILTER: Only include if guide exists in master schedule
                    if u not in guide_type_map:
                        continue
                    
                    g_type = guide_type_map[u]
                    d = display.strip() if display else u
                    d = re.sub(r'FL\s+|Guide\s+|\+\d+|[\d\s\.]+$', '', d, flags=re.IGNORECASE).strip()
                    if not d or d == u: d = u.upper()
                    
                    guides_with_work.add((u, d, g_type))

    except Exception as e:
        logger.exception(f"Error discovering guides for {date_str}")
        await callback.message.edit_text(f"❌ Ошибка поиска: {e}")
        return

    if not guides_with_work:
        await callback.message.edit_text(f"📭 На {date_str} работа для гидов не найдена.")
        return

    builder = InlineKeyboardBuilder()
    
    # Categorize and Sort
    staff_guides = sorted([g for g in guides_with_work if g[2] == 'staff'], key=lambda x: x[1])
    freelance_guides = sorted([g for g in guides_with_work if g[2] == 'freelance'], key=lambda x: x[1])
    
    # Staff Section
    if staff_guides:
        builder.row(types.InlineKeyboardButton(text="─── ШТАТНЫЕ ГИДЫ ───", callback_data="none"))
        for uname, display, _ in staff_guides:
            builder.row(types.InlineKeyboardButton(
                text=f"👤 {display} (@{uname})", 
                callback_data=f"gen_jo_{date_type}_{uname}"
            ))

    # Freelance Section
    if freelance_guides:
        builder.row(types.InlineKeyboardButton(text="─── ФРИЛАНСЕРЫ ───", callback_data="none"))
        for uname, display, _ in freelance_guides:
            builder.row(types.InlineKeyboardButton(
                text=f"👤 {display} (@{uname})", 
                callback_data=f"gen_jo_{date_type}_{uname}"
            ))

    await callback.message.edit_text(
        f"📅 <b>Job Orders на {date_str}</b>\n"
        "Выберите гида из списка:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "none")
async def process_none_callback(callback: types.CallbackQuery):
    await callback.answer()

@router.callback_query(F.data.startswith("gen_jo_"))
async def process_job_order_selection(callback: types.CallbackQuery):
    # Format: gen_jo_today_username or gen_jo_tomorrow_username
    # Usernames can have underscores, so we must limit splitting
    parts = callback.data.split("_", 3)
    if len(parts) < 4: return
    
    date_type = parts[2]
    uname = parts[3]
    
    now = get_phuket_now().date()
    target_date = now if date_type == "today" else now + datetime.timedelta(days=1)
    date_str = target_date.strftime('%d.%m')
    
    await callback.message.edit_text(f"⏳ Генерирую Job Order для @{uname} на {date_str}...")
    
    try:
        # 1. Try Sea Plan first
        sea_plans = await sea_plan_service.get_guide_sea_plan(uname, target_date)
        if sea_plans:
            plan = sea_plans[0]
            prog_names = [prog.name for prog in plan.programs]
            guests = await sea_plan_service.get_guest_list(target_date, prog_names)
            
            photo_bytes = job_order_generator.generate_sea_job_order(plan, guests)
            await callback.message.delete()
            await callback.message.answer_photo(
                types.BufferedInputFile(photo_bytes.getvalue(), filename=f"JobOrder_{uname}_{date_str}.png"),
                caption=f"📋 <b>SEA Job Order: @{uname}</b>\n📅 {date_str}\n🚢 {plan.boat}",
                parse_mode="HTML"
            )
            return

        # 2. Try Land Plan
        land_plans = await sea_plan_service.get_guide_land_plan(uname, target_date)
        if land_plans:
            plan = land_plans[0]
            photo_bytes = job_order_generator.generate_land_job_order(plan)
            await callback.message.delete()
            await callback.message.answer_photo(
                types.BufferedInputFile(photo_bytes.getvalue(), filename=f"JobOrder_{uname}_{date_str}.png"),
                caption=f"📋 <b>LAND Job Order: @{uname}</b>\n📅 {date_str}\n🚐 {plan.program}",
                parse_mode="HTML"
            )
            return

        await callback.message.edit_text(f"❌ Не удалось найти конкретные детали программы для @{uname} на {date_str}.")
    except Exception as e:
        logger.exception(f"Error generating job order for {uname}")
        await callback.message.edit_text(f"❌ Ошибка генерации: {str(e)}")

async def _send_admin_land_plans(username: str, target_date: datetime.date, plans: list, message: types.Message):
    """Helper to format and send land plans in Admin view"""
    if not plans:
        await message.answer(f"🚐 План на суше для @{username} не найден на {target_date.strftime('%d.%m')}.")
        return

    for plan in plans:
        response = f"🚐 <b>ADMIN VIEW: @{username}</b>\n"
        response += f"🏝️ <b>Program:</b> {plan.program}\n"
        response += f"📅 <b>Date:</b> {plan.date}\n"
        response += f"🪑 <b>Total PAX:</b> {plan.pax_string}\n"
        
        if plan.guides:
            guide_infos = []
            for g in plan.guides:
                # Try to extract @username from full_info if possible
                # full_info looks like "FALLA BOGOMOLETS   @BE_Ella00"
                parts = g.full_info.split('@')
                uname_tag = f"@{parts[1].strip()}" if len(parts) > 1 else g.full_info
                guide_infos.append(f"{uname_tag} (P/U: {g.pickup_time} @ {g.pickup_location})")
            
            response += f"🧭 <b>Guide(s):</b> {', '.join(guide_infos)}\n"
            
        if plan.bus:
            response += f"🚌 <b>Bus:</b> <code>{plan.bus}</code>\n"
        if plan.driver:
            response += f"👨‍✈️ <b>Driver:</b> {plan.driver}\n"
        
        if plan.guests:
            response += "\n👫 <b>Guest List:</b>\n\n"
            for g in plan.guests:
                response += f"  • <b>V/C:</b> <code>{g.voucher}</code> | <b>Pax:</b> {g.pax}\n"
                response += f"    <b>Pickup:</b> {g.pickup}\n"
                response += f"    <b>Hotel:</b> <code>{g.hotel} ({g.area})</code> (RM: {g.room})\n"
                response += f"    <b>Name:</b> <code>{g.name}</code>\n"
                if g.phone and g.phone != "-":
                    response += f"    <b>Phone:</b> <code>{g.phone}</code>\n"
                if g.remarks and g.remarks != "-":
                    response += f"    <b>Remarks:</b> {g.remarks}\n"
                response += f"    💵 <b>COT:</b> <code>{g.cot}</code>\n"
                response += "\n"
        
        await send_long_message(message, response, parse_mode="HTML")

@router.message(F.text == "📊 Статистика", RoleFilter(ADMIN_ALL))
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

@router.message(F.text == "⏱ Интервал", RoleFilter(SYSTEM_ADMIN))
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
        for prog in plan.programs:
            if prog.name not in program_names:
                program_names.append(prog.name)

    if not program_names:
        await callback.answer("У гида нет программ на эту дату.", show_alert=True)
        return

    await callback.answer("Загружаю список гостей...")

    guest_list = await sea_plan_service.get_guest_list(target_date, program_names)
    
    if not guest_list:
        await callback.message.answer(f"📋 Список гостей пуст или не найден для программ: {', '.join(program_names)}")
        return

    response = f"📋 <b>Список гостей ({date_str}) для @{tgt_username}</b>:\n\n"
    
    # Group guests by program
    grouped_guests = {}
    for g in guest_list:
        if g.program not in grouped_guests:
            grouped_guests[g.program] = []
        grouped_guests[g.program].append(g)

    for pname, guests in grouped_guests.items():
        response += f"🔹 <b>Program: {pname}</b>\n"
        for g in guests:
            response += f"  • <b>V/C:</b> <code>{g.voucher}</code> | <b>Pax:</b> {g.pax}\n"
            if g.pickup:
                response += f"    <b>Pickup:</b> {g.pickup}\n"
            response += f"    <b>Hotel:</b> <code>{g.hotel}</code> (RM: {g.room})\n"
            response += f"    <b>Name:</b> <code>{g.name}</code>\n"
            if g.phone and g.phone != "-":
                response += f"    <b>Phone:</b> <code>{g.phone}</code>\n"
            if g.remarks and g.remarks != "-":
                response += f"    <b>Remarks:</b> {g.remarks}\n"
            response += f"    💵 <b>COT:</b> <code>{g.cot}</code>\n"
            response += "\n"
    
    await callback.message.answer(response, parse_mode="HTML")

@router.message(F.text == "🔍 Тест-Аудит", RoleFilter(ADMIN_MANAGEMENT))
async def cmd_run_audit(message: types.Message):
    await message.answer("🧪 <b>Запускаю полное тестирование...</b>\n\nЯ прогню симуляцию ответов для всех гидов на сегодня и завтра. Это может занять около минуты из-за лимитов Google API.\n\n⏳ Пожалуйста, подожди...", parse_mode="HTML")
    
    try:
        from scripts.bot_audit import run_audit
        report_link = await run_audit()
        
        if report_link:
            await message.answer(
                f"✅ <b>Тестирование завершено!</b>\n\n"
                f"📊 Отчет сформирован и доступен по ссылке:\n{report_link}",
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Произошла ошибка при создании отчета. Проверь логи или права доступа к таблице.")
            
    except Exception as e:
        logger.exception(f"Error running audit from bot: {e}")
        await message.answer(f"❌ Критическая ошибка при выполнении аудита: {e}")
@router.message(F.text == "📅 Общее расписание", RoleFilter(ADMIN_MANAGEMENT))
async def cmd_general_schedule_menu(message: types.Message):
    """General Schedule: Today or Tomorrow"""
    await message.answer(
        "📅 <b>Общее расписание всех гидов</b>\nВыберите дату:",
        reply_markup=get_general_schedule_date_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("gs_date_"))
async def process_general_schedule_date(callback: types.CallbackQuery):
    date_type = callback.data.replace("gs_date_", "")
    now = get_phuket_now().date()
    target_date = now if date_type == "today" else now + datetime.timedelta(days=1)
    date_str = target_date.strftime('%d.%m')

    await callback.message.edit_text(f"📊 Генерирую общее расписание на {date_str}...")
    
    try:
        # 1. Fetch Master Schedule info
        master_schedule_map = {}
        sheet = await google_sheets.get_current_month_sheet()
        if sheet:
            staff, freelance = await google_sheets.parse_guides(sheet)
            all_guides = staff + freelance
            # Fetch all values once for efficiency
            all_values = await asyncio.to_thread(sheet.get_all_values)
            if all_values:
                header = all_values[0]
                day_num = str(target_date.day)
                col_idx = -1
                for i, val in enumerate(header):
                    if val.strip() == day_num:
                        col_idx = i
                        break
                
                if col_idx != -1:
                    for g in all_guides:
                        row_idx = g['row']
                        if row_idx <= len(all_values):
                            row = all_values[row_idx - 1]
                            if col_idx < len(row):
                                val = row[col_idx].strip()
                                # Simple lookback if empty (for merged cells)
                                if not val:
                                    for prev in range(col_idx-1, 1, -1):
                                        if row[prev].strip():
                                            val = row[prev].strip()
                                            break
                                if val:
                                    master_schedule_map[g['username'].lower()] = val

        # 2. Fetch ALL plans
        # Sea Plans
        sea_plans = []
        sea_guides = await sea_plan_service.get_active_sea_guides([target_date])
        for uname in sea_guides:
            p = await sea_plan_service.get_guide_sea_plan(uname, target_date)
            if p: sea_plans.extend(p)
            
        unique_sea = []
        seen_boats = set()
        for p in sea_plans:
            if p.boat not in seen_boats:
                unique_sea.append(p)
                seen_boats.add(p.boat)

        # Land Plans
        land_plans = []
        land_guides = await sea_plan_service.get_active_land_guides([target_date])
        for uname in land_guides:
            p = await sea_plan_service.get_guide_land_plan(uname, target_date)
            if p: land_plans.extend(p)

        # 3. Generate Image
        from services.image_generator import job_order_generator
        photo_bytes = job_order_generator.generate_general_schedule(date_str, unique_sea, land_plans, master_schedule_map)
        
        # 3. Send to Admin
        await callback.message.delete()
        builder = InlineKeyboardBuilder()
        builder.button(text="📢 Разослать гидам", callback_data=f"gs_broadcast_{date_type}")
        
        await callback.message.answer_photo(
            types.BufferedInputFile(photo_bytes.getvalue(), filename=f"Schedule_{date_str}.png"),
            caption=f"📅 <b>Общее расписание: {date_str}</b>\n\nВсе изменения в таблице учтены.",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logger.exception(f"Error generating general schedule for {date_str}")
        await callback.message.edit_text(f"❌ Ошибка генерации: {str(e)}")

@router.callback_query(F.data.startswith("gs_broadcast_"))
async def process_broadcast_schedule(callback: types.CallbackQuery, bot: Bot):
    date_type = callback.data.replace("gs_broadcast_", "")
    now = get_phuket_now().date()
    target_date = now if date_type == "today" else now + datetime.timedelta(days=1)
    date_str = target_date.strftime('%d.%m')
    
    await callback.answer("Начинаю рассылку...")
    msg = await callback.message.answer(f"⏳ Рассылаю расписание на {date_str}...")
    
    # Identify all guides with work
    guides_to_notify = set()
    try:
        sea_guides = await sea_plan_service.get_active_sea_guides([target_date])
        land_guides = await sea_plan_service.get_active_land_guides([target_date])
        guides_to_notify.update(sea_guides)
        guides_to_notify.update(land_guides)
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка получения списка гидов: {e}")
        return

    if not guides_to_notify:
        await msg.edit_text(f"📭 На {date_str} нет гидов с работой для рассылки.")
        return

    # Broadcast metrics
    success = 0
    failed = 0
    not_in_bot = []
    
    # Get the photo from the current message
    photo_file_id = callback.message.photo[-1].file_id

    async with AsyncSessionLocal() as session:
        for uname in guides_to_notify:
            # Find in DB
            query = select(User).where(User.username.ilike(uname))
            result = await session.execute(query)
            user = result.scalar_one_or_none()
            
            if not user or not user.telegram_id:
                not_in_bot.append(f"@{uname}")
                continue
                
            try:
                await bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=photo_file_id,
                    caption=f"📅 <b>Утвержденное расписание на {date_str}</b>\n\nПожалуйста, ознакомьтесь с вашим заданием.",
                    parse_mode="HTML"
                )
                success += 1
            except Exception as e:
                logger.error(f"Failed to send schedule to @{uname} ({user.telegram_id}): {e}")
                failed += 1

    report = (
        f"📢 <b>Рассылка на {date_str} завершена!</b>\n\n"
        f"✅ Успешно доставлено: <b>{success}</b>\n"
        f"❌ Ошибки доставки: <b>{failed}</b>\n"
        f"📭 Не начали диалог: <b>{len(not_in_bot)}</b>\n"
    )
    
    if not_in_bot:
        report += f"\n<b>Список гидов, не получивших расписание:</b>\n{', '.join(not_in_bot)}"

    await msg.edit_text(report, parse_mode="HTML")

# ─── Impersonation (Tester Mode) ───────────────────────────────────────────

@router.message(Command("become_user"), IsTesterFilter())
async def cmd_become_user(message: types.Message):
    """Tester: Choose a user to impersonate"""
    sheet = await google_sheets.get_current_month_sheet()
    if not sheet:
        await message.answer("❌ Не удалось загрузить расписание.")
        return

    staff, freelance = await google_sheets.parse_guides(sheet)
    all_guides = staff + freelance
    
    # Sort and remove duplicates from sheet
    unique_guide_names = sorted(list(set([g['username'].lower() for g in all_guides if g['username']])))
    
    builder = InlineKeyboardBuilder()
    
    # Add common roles for testing
    builder.row(types.InlineKeyboardButton(text="--- SYSTEM ROLES ---", callback_data="none"))
    builder.row(
        types.InlineKeyboardButton(text="👤 Admin", callback_data="imp_role_admin"),
        types.InlineKeyboardButton(text="👤 Super Admin", callback_data="imp_role_super_admin")
    )
    builder.row(
        types.InlineKeyboardButton(text="👤 Head of Guide", callback_data="imp_role_head_guide"),
        types.InlineKeyboardButton(text="👤 Hot Line", callback_data="imp_role_hotline")
    )
    
    builder.row(types.InlineKeyboardButton(text="--- GUIDES FROM SHEET ---", callback_data="none"))
    for uname in unique_guide_names:
        builder.button(text=f"👤 @{uname}", callback_data=f"imp_user_{uname}")
        
    builder.adjust(1, 2, 2, 1, 3)
    
    await message.answer(
        "🎭 <b>Режим имитации (Tester Mode)</b>\n\n"
        "Выберите пользователя или роль, которую хотите примерить.\n"
        "После выбора бот будет считать вас этим пользователем для ВСЕХ функций.",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.message(Command("exit_impersonation"))
async def cmd_exit_impersonation(message: types.Message, state: FSMContext):
    """Restore original identity"""
    redis = state.storage.redis if hasattr(state, "storage") and hasattr(state.storage, "redis") else None
    if redis:
        await redis.delete(f"impersonation:{message.from_user.id}")
        await message.answer("✅ <b>Режим имитации выключен.</b>\nВаша личность восстановлена. /start для обновления меню.", parse_mode="HTML")
    else:
        await message.answer("❌ Ошибка: Redis не доступен.")

@router.callback_query(F.data.startswith("imp_user_"), IsTesterFilter())
async def process_impersonate_user(callback: types.CallbackQuery, state: FSMContext):
    target_username = callback.data.replace("imp_user_", "")
    
    # Logic: Default to GUIDE role for impersonated guides unless specified
    imp_data = {
        "username": target_username,
        "role": UserRole.GUIDE,
        "id": 0 # Fake ID
    }
    
    redis = state.storage.redis if hasattr(state, "storage") and hasattr(state.storage, "redis") else None
    if redis:
        import json
        await redis.set(f"impersonation:{callback.from_user.id}", json.dumps(imp_data), ex=3600) # 1 hour expiry
        await callback.message.edit_text(f"✅ Теперь вы имитируете @{target_username}.\nИспользуйте /start для обновления интерфейса.")
    else:
        await callback.answer("Ошибка: Redis недоступен", show_alert=True)

@router.callback_query(F.data.startswith("imp_role_"), IsTesterFilter())
async def process_impersonate_role(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.replace("imp_role_", "")
    
    imp_data = {
        "username": f"TEST_{role.upper()}",
        "role": role,
        "id": 0
    }
    
    redis = state.storage.redis if hasattr(state, "storage") and hasattr(state.storage, "redis") else None
    if redis:
        import json
        await redis.set(f"impersonation:{callback.from_user.id}", json.dumps(imp_data), ex=3600)
        await callback.message.edit_text(f"✅ Теперь вы имитируете РОЛЬ: {role}.\nИспользуйте /start для обновления интерфейса.")
    else:
        await callback.answer("Ошибка: Redis недоступен", show_alert=True)
