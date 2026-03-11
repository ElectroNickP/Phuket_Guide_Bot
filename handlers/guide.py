from aiogram import Router, types, F
from aiogram.filters import Command
from services.google_sheets import google_sheets
from services.sea_plan import sea_plan_service
from database.db import update_user_activity
from utils.keyboards import get_schedule_keyboard, get_sea_plan_keyboard, get_land_plan_keyboard
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

    staff, freelance = await google_sheets.parse_guides(sheet)
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
    schedule = await google_sheets.get_guide_schedule(sheet, guide_info['row'], day=day)

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
async def cmd_sea_plan(message: types.Message):
    await message.answer("Выберите день для просмотра плана на море:", reply_markup=get_sea_plan_keyboard())

@router.message(F.text == "🚐 План на суше")
async def cmd_land_plan(message: types.Message):
    await message.answer("Выберите день для просмотра плана на суше:", reply_markup=get_land_plan_keyboard())

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
                if len(plan['guides_list']) > 1 and prog['guide']:
                    response += f"  • {prog_text} - {prog['short_guide']}\n"
                else:
                    response += f"  • {prog_text}\n"
            response += f"📊 <b>Total Pax:</b> {plan['total_pax']}\n\n"
        
        # Add a Guest List button if there are programs 
        guest_list_btn = None
        has_programs = any(len(p['programs']) > 0 for p in plans)
        if has_programs:
            builder = InlineKeyboardBuilder()
            builder.button(text="📋 Список гостей", callback_data=f"guestlist_guide_{target_date.strftime('%d.%m')}")
            guest_list_btn = builder.as_markup()
        
        await callback.message.edit_text(response, parse_mode="HTML", reply_markup=guest_list_btn)
        await callback.answer()
        
        # Track activity
        action = "sea_tomorrow" if is_tomorrow else "sea_today"
        await update_user_activity(callback.from_user.id, action)
        
    except Exception as e:
        logger.exception(f"Error fetching sea plan for @{user_username}: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при получении плана на море.")

@router.message(F.text == "👤 Мой статус")
async def cmd_status(message: types.Message):
    # Track activity
    await update_user_activity(message.from_user.id, "status")
    
    sheet = await google_sheets.get_current_month_sheet()
    if not sheet:
        await message.answer("❌ Нет связи с таблицей.")
        return

    staff, freelance = await google_sheets.parse_guides(sheet)
    
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

@router.callback_query(F.data.startswith("guestlist_guide_"))
async def process_guest_list_guide(callback: types.CallbackQuery):
    try:
        # data is guestlist_guide_dd.mm
        date_str = callback.data.split('_')[2]
        target_date = datetime.datetime.strptime(f"{date_str}.{datetime.date.today().year}", "%d.%m.%Y").date()
    except ValueError:
        await callback.answer("Ошибка формата даты", show_alert=True)
        return

    username = callback.from_user.username
    if not username:
        await callback.answer("Для работы требуется @username в Telegram.", show_alert=True)
        return

    plans = await sea_plan_service.get_guide_sea_plan(username, target_date)
    if not plans:
        await callback.answer("Не найдено программ на эту дату.", show_alert=True)
        return

    program_names = []
    for plan in plans:
        for prog in plan['programs']:
            if prog['name'] not in program_names:
                program_names.append(prog['name'])

    if not program_names:
        await callback.answer("У вас нет программ на эту дату.", show_alert=True)
        return

    await callback.answer("Загружаю список гостей...")

    guest_list = await sea_plan_service.get_guest_list(target_date, program_names)
    
    if not guest_list:
        await callback.message.answer(f"📋 Список гостей пуст или не найден для программ: {', '.join(program_names)}")
        return

    response = f"📋 <b>Список гостей ({date_str})</b>:\n\n"
    
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
            response += "\n"
    
    await callback.message.answer(response, parse_mode="HTML")

@router.callback_query(F.data.startswith("land_"))
async def process_land_plan_guide(callback: types.CallbackQuery):
    is_today = callback.data == "land_today"
    target_date = datetime.date.today() if is_today else datetime.date.today() + datetime.timedelta(days=1)
    date_str = target_date.strftime("%d.%m")

    username = callback.from_user.username
    if not username:
        await callback.answer("Для работы требуется @username в Telegram.", show_alert=True)
        return

    await callback.answer(f"Загружаю план на суше ({date_str})...")
    
    plans = await sea_plan_service.get_guide_land_plan(username, target_date)
    
    if not plans:
        await callback.message.answer(f"🚐 <b>План на суше ({date_str})</b>\n\nНа этот день ваших заказов не найдено.", parse_mode="HTML")
        return

    for plan in plans:
        response = f"🚐 <b>JOB ORDER: {plan['program']}</b>\n"
        response += f"📅 <b>DATE:</b> {plan['date']}\n\n"
        
        if plan['guides']:
            response += "👤 <b>GUIDE(S):</b>\n"
            for g in plan['guides']:
                me_tag = " (ВЫ)" if g['is_me'] else ""
                response += f"• {g['full_info']}{me_tag} (P/U: {g['pickup_time']} @ {g['pickup_location']})\n"
            response += "\n"
            
        if plan['bus']:
            response += f"🚌 <b>BUS:</b> <code>{plan['bus']}</code>\n"
        if plan['driver']:
            response += f"👨‍✈️ <b>DRIVER:</b> {plan['driver']}\n"
        
        if plan['guests']:
            response += "\n👥 <b>GUEST LIST:</b>\n"
            for i, g in enumerate(plan['guests'], 1):
                response += f"{i}. <b>V/C:</b> <code>{g['voucher']}</code> | <b>Pax:</b> {g['pax']}\n"
                response += f"   <b>Hotel:</b> {g['hotel']} (RM: {g['room']})\n"
                response += f"   <b>Name:</b> <code>{g['name']}</code>\n"
                if g['phone'] and g['phone'] != "-":
                    response += f"   <b>Phone:</b> <code>{g['phone']}</code>\n"
                if g['remarks'] and g['remarks'] != "-":
                    response += f"   <b>Remarks:</b> {g['remarks']}\n"
                response += "\n"
        
        await callback.message.answer(response, parse_mode="HTML")
