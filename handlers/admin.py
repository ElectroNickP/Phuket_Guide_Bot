from aiogram import Router, types, F, Bot
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import AsyncSessionLocal
from database.models import User, AppSettings
from services.google_sheets import google_sheets
from sqlalchemy import select, update
from loguru import logger
from config import config
import re
import datetime


class IsAdminFilter(BaseFilter):
    """Router-level filter: silently ignores non-admin users."""
    async def __call__(self, event: types.Message | types.CallbackQuery) -> bool:
        user_id = event.from_user.id if hasattr(event, 'from_user') else None
        return user_id in config.admin_id_list


router = Router()
# Apply admin guard to ALL message and callback handlers in this router
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

class AdminStates(StatesGroup):
    waiting_for_sheet_url = State()
    waiting_for_sea_sheet_url = State()
    waiting_for_guide_name = State()
    waiting_for_guide_name_sea = State()

@router.message(F.text == "🔗 Сменить таблицу")
async def cmd_set_sheet_kb(message: types.Message, state: FSMContext):
    await message.answer("📝 Пришли мне URL или ID новой Google таблицы:")
    await state.set_state(AdminStates.waiting_for_sheet_url)

@router.message(AdminStates.waiting_for_sheet_url)
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

@router.message(F.text == "🔗 Сменить таблицу (Море)")
async def cmd_set_sea_sheet_kb(message: types.Message, state: FSMContext):
    await message.answer("📝 Пришли мне URL или ID новой Google таблицы (ПЛАН НА МОРЕ):")
    await state.set_state(AdminStates.waiting_for_sea_sheet_url)

@router.message(AdminStates.waiting_for_sea_sheet_url)
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

@router.message(F.text == "📋 Логи")
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
            f"📋 <b>Последние 30 строк логов:</b>\n\n<code>{log_text}</code>",
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
    await state.set_state(AdminStates.waiting_for_guide_name)

@router.message(AdminStates.waiting_for_guide_name)
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
        today = datetime.datetime.now().day
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).day
        
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
    await message.answer("🌊 Введи username гида (через @), чей ПЛАН НА МОРЕ ты хочешь посмотреть:")
    await state.set_state(AdminStates.waiting_for_guide_name_sea)

@router.message(AdminStates.waiting_for_guide_name_sea)
async def process_guide_monitor_sea(message: types.Message, state: FSMContext):
    target_username = message.text.replace("@", "").strip()
    
    from services.sea_plan import sea_plan_service
    
    # Try today and tomorrow
    today = datetime.datetime.now().date()
    tomorrow = today + datetime.timedelta(days=1)
    
    response = f"👁 <b>Архив/Мониторинг МОРЕ: @{target_username}</b>\n\n"
    
    found_any = False
    for date in [today, tomorrow]:
        date_str = date.strftime("%d.%m")
        try:
            plans = await sea_plan_service.get_guide_sea_plan(target_username, date)
            if plans:
                found_any = True
                response += f"📅 <b>Дата: {date_str}</b>\n"
                for plan in plans:
                    response += f"🚢 <b>Лодка:</b> {plan['boat']}\n"
                    response += f"⚓️ <b>Пирс:</b> {plan['pier'] or '---'}\n"
                    response += f"👤 <b>Thai Guide:</b> {plan['thai_guide'] or '---'}\n"
                    response += f"👥 <b>Гид(ы):</b> {', '.join(plan['guides_list'])}\n"
                    response += f"📝 <b>Программы:</b>\n"
                    for prog in plan['programs']:
                        prog_text = f"{prog['name']} ({prog['pax']} pax)"
                        if len(plan['guides_list']) > 1 and prog.get('short_guide'):
                            prog_text += f" - {prog['short_guide']}"
                        response += f"  • {prog_text}\n"
                    response += f"📊 <b>Total Pax:</b> {plan['total_pax']}\n"
                response += "\n"
        except Exception as e:
            logger.error(f"Error in admin sea monitor for {target_username} on {date_str}: {e}")

    if not found_any:
        await message.answer(f"❌ План на море для @{target_username} на сегодня/завтра не найден.")
    else:
        await message.answer(response, parse_mode="HTML")
    
    await state.clear()

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

@router.message(F.text == "⏱ Интервал")
async def cmd_set_interval_kb(message: types.Message):
    from utils.keyboards import get_interval_keyboard
    await message.answer(
        "⏱ <b>Настройка интервала опроса таблицы</b>\n\n"
        "Выбери, как часто бот должен проверять изменения в расписании:",
        reply_markup=get_interval_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("setint_"))
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
