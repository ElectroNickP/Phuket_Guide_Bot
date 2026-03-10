from aiogram import Router, types, F
from aiogram.filters import Command
from services.google_sheets import google_sheets
from services.sea_plan import sea_plan_service
from database.db import update_user_activity
from utils.keyboards import get_schedule_keyboard, get_sea_plan_keyboard
from loguru import logger
import datetime

router = Router()

@router.message(F.text == "📅 Моё расписание")
async def cmd_schedule_buttons(message: types.Message):
    """Show schedule buttons"""
    await message.answer("📆 На какой день ты хочешь посмотреть расписание?", reply_markup=get_schedule_keyboard())

@router.callback_query(F.data.startswith("sched_"))
async def process_schedule_query(callback: types.CallbackQuery):
    """Process inline buttons for schedule"""
    await callback.message.edit_text("🔍 Ищу расписание...")
    
    sheet = await google_sheets.get_current_month_sheet()
    if not sheet:
        await callback.message.edit_text("❌ Не удалось найти лист с расписанием на текущий месяц.")
        return

    staff, freelance = google_sheets.parse_guides(sheet)
    all_guides = staff + freelance
    
    user_username = callback.from_user.username
    if not user_username:
        await callback.message.edit_text("❌ У тебя не установлен username в Телеграм. Пожалуйста, установи его.")
        return

    guide_info = next((g for g in all_guides if g['username'].lower() == user_username.lower()), None)
    
    if not guide_info:
        await callback.message.edit_text(f"❌ Я не нашел гида с username @{user_username} в таблице.")
        return

    is_tomorrow = "tomorrow" in callback.data
    target_date = datetime.datetime.now()
    if is_tomorrow:
        target_date += datetime.timedelta(days=1)
    
    day = target_date.day
    schedule = google_sheets.get_guide_schedule(sheet, guide_info['row'], day=day)

    date_str = "Завтра" if is_tomorrow else "Сегодня"
    response = (
        f"📋 <b>Расписание для @{user_username}</b>\n\n"
        f"📅 {date_str} ({day}): <b>{schedule or 'Свободен'}</b>"
    )
    
    await callback.message.edit_text(response, parse_mode="HTML")
    await callback.answer()
    
    # Track activity
    action = "tomorrow" if is_tomorrow else "today"
    await update_user_activity(callback.from_user.id, action)

@router.message(F.text == "🌊 План на море")
async def cmd_sea_plan_buttons(message: types.Message):
    """Show sea plan buttons"""
    await message.answer("🌊 На какой день ты хочешь посмотреть план на море?", reply_markup=get_sea_plan_keyboard())

@router.callback_query(F.data.startswith("sea_"))
async def process_sea_query(callback: types.CallbackQuery):
    """Process inline buttons for sea plan"""
    is_tomorrow = "tomorrow" in callback.data
    target_date = datetime.datetime.now().date()
    if is_tomorrow:
        target_date += datetime.timedelta(days=1)
        
    user_username = callback.from_user.username
    if not user_username:
        await callback.message.edit_text("❌ У тебя не установлен username в Телеграм.")
        return

    await callback.message.edit_text("🔍 Запрашиваю план на море...")
    
    try:
        plans = await sea_plan_service.get_guide_sea_plan(user_username, target_date)
        
        if not plans:
            await callback.message.edit_text(f"❌ План на море на {target_date.strftime('%d.%m')} для @{user_username} не найден.")
            return

        response = f"🌊 <b>План на море ({target_date.strftime('%d.%m')})</b>\n\n"
        
        for plan in plans:
            response += f"🚢 <b>Лодка:</b> {plan['boat']}\n"
            response += f"⚓️ <b>Пирс:</b> {plan['pier'] or '---'}\n"
            response += f"👤 <b>Thai Guide:</b> {plan['thai_guide'] or '---'}\n"
            response += f"👥 <b>Гид(ы):</b> {', '.join(plan['guides_list'])}\n"
            response += f"📝 <b>Программы:</b>\n"
            for prog in plan['programs']:
                prog_text = f"{prog['name']} ({prog['pax']} pax)"
                if len(plan['guides_list']) > 1:
                    prog_text += f" - {prog['guide']}"
                response += f"  • {prog_text}\n"
            response += f"📊 <b>Total Pax:</b> {plan['total_pax']}\n\n"
        
        await callback.message.edit_text(response, parse_mode="HTML")
        await callback.answer()
        
        # Track activity
        action = "sea_tomorrow" if is_tomorrow else "sea_today"
        await update_user_activity(callback.from_user.id, action)
        
    except Exception as e:
        logger.error(f"Error fetching sea plan: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при получении плана на море.")

@router.message(F.text == "👤 Мой статус")
async def cmd_status(message: types.Message):
    # Track activity
    await update_user_activity(message.from_user.id, "status")
    
    sheet = await google_sheets.get_current_month_sheet()
    if not sheet:
        await message.answer("❌ Нет связи с таблицей.")
        return

    staff, freelance = google_sheets.parse_guides(sheet)
    
    user_username = message.from_user.username
    is_staff = any(g['username'].lower() == user_username.lower() for g in staff)
    is_freelance = any(g['username'].lower() == user_username.lower() for g in freelance)

    if is_staff:
        status = "Штатный гид ✅"
    elif is_freelance:
        status = "Фриланс 🤝"
    else:
        status = "Не найден в списке ❓"

    await message.answer(f"Твой статус: <b>{status}</b>", parse_mode="HTML")
