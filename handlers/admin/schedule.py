import datetime
import html
import re
import asyncio
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from loguru import logger

from services.scheduler import get_phuket_now, get_phuket_today
from services.sea_plan import sea_plan_service
from services.google_sheets import google_sheets
from database.db import AsyncSessionLocal
from database.models import User
from utils.permissions import RoleFilter

from .base import ADMIN_MANAGEMENT, IsAdminFilter
from utils.keyboards import get_job_order_date_keyboard, get_general_schedule_date_keyboard
from services.image_generator import job_order_generator

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

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

    for i, plan in enumerate(plans):
        # Format Phone Number with Robust Global Matcher
        driver_info = plan.driver or "---"
        # We escape the whole string first for safety
        driver_display = html.escape(driver_info)
        
        def _replace_phone(m):
            raw_inside = m.group(1)
            # Remove all non-digits to check if it's a phone number
            digits = re.sub(r'\D', '', raw_inside)
            if len(digits) >= 9:
                return f"(<a href=\"tel:{digits}\">{raw_inside}</a>)"
            return m.group(0) # String already escaped, group(0) includes escaped chars
            
        # Global replace for all occurrences in parentheses
        driver_display = re.sub(r'\(([^)]+)\)', _replace_phone, driver_display)

        # First Hotel info
        first_hotel_info = "---"
        if plan.guests:
            first = plan.guests[0]
            first_hotel_info = f"{first.pickup} <code>{first.hotel}</code>"

        # COT summing or listing
        cot_info = "---"
        if plan.guests:
            cots = []
            for g in plan.guests:
                try:
                    cot_val = str(g.cot).strip()
                    if cot_val and cot_val != "0" and cot_val != "-":
                        cots.append(f"{cot_val} ({g.name})")
                except: continue
            if cots:
                cot_info = "\n" + "\n".join(cots)

        response = (
            f"🚐 <b>ADMIN VIEW: @{username}</b>\n"
            f"📅 <b>Date:</b> {plan.date}\n"
            f"🏝️ <b>Program:</b> {plan.program}\n"
        )
        if getattr(plan, 'thai_guide', None):
            response += f"👤 <b>Thai guide:</b> {plan.thai_guide}\n"
        response += f"🪑 <b>Total PAX:</b> {plan.pax_string}\n"
        
        if plan.guides:
            guide_infos = []
            for g in plan.guides:
                parts = g.full_info.split('@')
                uname_tag = f"@{parts[1].strip()}" if len(parts) > 1 else g.full_info
                guide_infos.append(f"{uname_tag} (P/U: {g.pickup_time} @ {g.pickup_location})")
            response += f"🧭 <b>Guide(s):</b> {', '.join(guide_infos)}\n"
            
        if plan.bus:
            response += f"🚌 <b>Bus:</b> <code>{plan.bus}</code>\n"
        
        response += f"👨‍✈️ <b>Driver:</b> {driver_display}\n"
        response += f"💵 <b>COT:</b> {cot_info}\n\n"
        response += f"🏨 <b>First hotel (P/U):</b> {first_hotel_info}\n"
        
        # Add Guest List button
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Список гостей", callback_data=f"guestlist_land_{plan.date}_{i}_{username}")
        
        await message.answer(response, parse_mode="HTML", reply_markup=builder.as_markup())


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
            user = result.scalars().first()
            
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
