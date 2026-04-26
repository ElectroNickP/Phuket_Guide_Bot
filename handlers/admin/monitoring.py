import asyncio
import datetime
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from services.google_sheets import google_sheets
from services.sea_plan import sea_plan_service
from services.scheduler import get_phuket_now, get_phuket_today
from utils.permissions import RoleFilter
from database.models import WakeUpConfirmation, ReportSubmission, User
from database.db import AsyncSessionLocal
from sqlalchemy import select, desc, func
import html
import re
import gspread
from config import config

from .base import ADMIN_ALL, IsAdminFilter

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

@router.message(F.text == "👁 Мониторинг гидов", RoleFilter(ADMIN_ALL))
async def cmd_monitor_guides(message: types.Message, state: FSMContext):
    await _cmd_monitor_guides_base(message)

@router.callback_query(F.data == "mon_v2_main")
async def process_monitor_main(callback: types.CallbackQuery):
    await _cmd_monitor_guides_base(callback.message)
    await callback.answer()

async def _cmd_monitor_guides_base(message: types.Message):
    await message.edit_text("🔍 Загружаю список всех гидов...") if hasattr(message, 'edit_text') and message.reply_markup else None
    
    try:
        sheet = await google_sheets.get_current_month_sheet()
        if not sheet:
            await message.answer("❌ Не удалось найти лист с расписанием.")
            return

        staff, freelance = await google_sheets.parse_guides(sheet)
        
        if not staff and not freelance:
            await message.answer("❌ Гиды не найдены в таблице.")
            return

        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🏢 Штатные гиды", callback_data="mon_v2_list_staff"))
        builder.row(types.InlineKeyboardButton(text="🌍 Фрилансеры", callback_data="mon_v2_list_freelance"))
        builder.row(types.InlineKeyboardButton(text="📊 Показать всё расписание", callback_data="mon_v2_all"))
        
        await message.answer(
            f"👥 <b>Мониторинг гидов</b>\n"
            f"Штат: {len(staff)}, Фриланс: {len(freelance)}\n\n"
            "Выберите категорию или посмотрите общее расписание:",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except gspread.exceptions.APIError as e:
        if "403" in str(e) or "permission" in str(e).lower():
            service_account = "bot-reader-telegram@best-telegram-bots.iam.gserviceaccount.com"
            await message.answer(
                f"❌ <b>Ошибка доступа к Google Таблице (403)</b>\n\n"
                f"Пожалуйста, предоставь доступ сервисному аккаунту:\n"
                f"<code>{service_account}</code>\n"
                f"к таблице с расписанием с правами <b>Редактора</b> или <b>Читателя</b>.",
                parse_mode="HTML"
            )
        else:
            await message.answer(f"❌ Ошибка Google Sheets: {e}")
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка при загрузке данных: {e}")

@router.callback_query(F.data.startswith("mon_v2_list_"))
async def process_admin_monitor_type(callback: types.CallbackQuery):
    gtype = callback.data.replace("mon_v2_list_", "")
    
    sheet = await google_sheets.get_current_month_sheet()
    staff, freelance = await google_sheets.parse_guides(sheet)
    guides = staff if gtype == 'staff' else freelance
    
    builder = InlineKeyboardBuilder()
    for g in guides:
        builder.button(text=f"👤 @{g['username']}", callback_data=f"mon_v2_user_{g['username']}")
    
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="mon_v2_main"))
    builder.adjust(2)
    
    title = "🏢 Штатные гиды" if gtype == 'staff' else "🌍 Фрилансеры"
    await callback.message.edit_text(
        f"👥 <b>{title}</b>\n"
        f"Всего: {len(guides)}\n\n"
        "Выберите гида для просмотра расписания:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("mon_v2_user_"))
async def process_admin_monitor_user_v2(callback: types.CallbackQuery):
    username = callback.data.split("_", 3)[3]
    await callback.answer(f"Загружаю @{username}...")
    
    now = get_phuket_now().date()
    dates = [
        ("⏮ Вчера", now - datetime.timedelta(days=1)),
        ("📅 Сегодня", now),
        ("📅 Завтра", now + datetime.timedelta(days=1)),
        ("⏭ Послезавтра", now + datetime.timedelta(days=2))
    ]
    
    current_sheet = await google_sheets.get_current_month_sheet()
    staff, freelance = await google_sheets.parse_guides(current_sheet)
    all_current = staff + freelance
    guide_info = next((g for g in all_current if g['username'].lower() == username.lower()), None)
    
    if not guide_info:
        await callback.message.answer(f"❌ Гид @{username} не найден в текущем месяце.")
        return

    response = f"👁 <b>Архив/Мониторинг: @{username}</b>\n\n"
    
    for label, target_date in dates:
        sheet = await google_sheets.get_sheet_by_date(target_date)
        if not sheet:
            response += f"{label} ({target_date.strftime('%d.%m')}): ❌ Лист не найден\n"
            continue
            
        row_idx = guide_info['row']
        if sheet.title != current_sheet.title:
            s, f = await google_sheets.parse_guides(sheet)
            all_target = s + f
            target_guide = next((g for g in all_target if g['username'].lower() == username.lower()), None)
            if target_guide:
                row_idx = target_guide['row']
            else:
                response += f"{label} ({target_date.strftime('%d.%m')}): ❌ Не найден в листе {sheet.title}\n"
                continue

        sched = await google_sheets.get_guide_schedule(sheet, row_idx, target_date)
        response += f"{label} ({target_date.strftime('%d.%m')}): <b>{sched or '---'}</b>\n"

    await callback.message.answer(response, parse_mode="HTML")

@router.callback_query(F.data == "mon_v2_all")
async def process_admin_monitor_all_v2(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Собираю общее расписание...")
    
    current_sheet = await google_sheets.get_current_month_sheet()
    staff, freelance = await google_sheets.parse_guides(current_sheet)
    all_guides = staff + freelance
    
    now = get_phuket_now().date()
    dates = [
        ("⏮ Вчера", now - datetime.timedelta(days=1)),
        ("📅 Сегодня", now),
        ("📅 Завтра", now + datetime.timedelta(days=1)),
        ("⏭ Послезавтра", now + datetime.timedelta(days=2))
    ]
    
    date_sheets = {}
    sheet_guide_maps = {} 
    
    for _, dt in dates:
        sh = await google_sheets.get_sheet_by_date(dt)
        if sh:
            date_sheets[dt] = sh
            if sh.title not in sheet_guide_maps:
                s, f = await google_sheets.parse_guides(sh)
                sheet_guide_maps[sh.title] = {x['username'].lower(): x['row'] for x in s+f}

    await callback.message.answer(f"📊 <b>Сводное расписание ({len(all_guides)} гидов):</b>")
    
    for g in all_guides:
        uname_lower = g['username'].lower()
        response = f"👁 <b>Архив/Мониторинг: @{g['username']}</b>\n\n"
        has_data = False
        
        for label, dt in dates:
            sh = date_sheets.get(dt)
            if not sh:
                response += f"{label} ({dt.strftime('%d.%m')}): ❌ Лист не найден\n"
                continue
            
            row_map = sheet_guide_maps.get(sh.title, {})
            ridx = row_map.get(uname_lower)
            
            if ridx:
                sched = await google_sheets.get_guide_schedule(sh, ridx, dt)
                response += f"{label} ({dt.strftime('%d.%m')}): <b>{sched or '---'}</b>\n"
                if sched: has_data = True
            else:
                response += f"{label} ({dt.strftime('%d.%m')}): ❌ Не найден\n"
        
        if has_data:
            await callback.message.answer(response, parse_mode="HTML")
            await asyncio.sleep(0.3)

    await callback.message.answer("✅ Мониторинг завершен.")
    await state.clear()

@router.message(F.text == "👁 Контроль Смены", RoleFilter(ADMIN_ALL))
async def cmd_shift_control(message: types.Message):
    await message.answer("🔍 Собираю данные по текущей смене...")
    
    today = get_phuket_today()
    
    sea_guides = await sea_plan_service.get_active_sea_guides([today])
    land_guides = await sea_plan_service.get_active_land_guides([today])
    all_scheduled = list(set(sea_guides + land_guides))
    
    async with AsyncSessionLocal() as session:
        today_start = datetime.datetime.combine(today, datetime.time.min)
        q_reports = select(ReportSubmission).where(ReportSubmission.date >= today_start)
        res_reports = await session.execute(q_reports)
        reports = res_reports.scalars().all()
        
        report_map = {}
        for r in reports:
            uname = r.guide_username.lower()
            if uname not in report_map: report_map[uname] = {"start": False, "finish": False}
            if r.report_type == "start": report_map[uname]["start"] = True
            if r.report_type == "finish": report_map[uname]["finish"] = True
            
        q_wakeup = select(WakeUpConfirmation).where(WakeUpConfirmation.date == today_start)
        res_wakeup = await session.execute(q_wakeup)
        wakeups = res_wakeup.scalars().all()
        wakeup_map = {w.guide_username.lower(): w.status for w in wakeups}
        
        q_users = select(User.username)
        res_users = await session.execute(q_users)
        registered_usernames = [u.lower() for u in res_users.scalars().all() if u]

    response = f"👁 <b>КОНТРОЛЬ СМЕНЫ ({today.strftime('%d.%m')})</b>\n\n"
    
    if not all_scheduled:
        response += "🏝 Сегодня нет запланированных гидов."
    else:
        lines = []
        for uname in sorted(all_scheduled):
            ulower = uname.lower()
            reg_icon = "👤" if ulower in registered_usernames else "❓"
            
            wu_status = wakeup_map.get(ulower, "pending")
            wu_icon = "⏰✅" if wu_status == "confirmed" else "⏰⚠️" if wu_status == "problem" else "⏰⌛️"
            
            reps = report_map.get(ulower, {"start": False, "finish": False})
            st_icon = "🚀✅" if reps["start"] else "🚀❌"
            fn_icon = "🏁✅" if reps["finish"] else "🏁❌"
            
            lines.append(f"{reg_icon} @{uname}\n   {wu_icon} | {st_icon} | {fn_icon}")

        response += "\n\n".join(lines)
        
    response += (
        "\n\n---\n"
        "💡 <b>Легенда:</b>\n"
        "⏰: Пробуждение (⌛️-жду, ✅-ок, ⚠️-проблема)\n"
        "🚀: Старт программы, 🏁: Финиш программы\n"
        "❓: Гид НЕ зарегистрирован в боте!"
    )
    
    if len(response) > 4000:
        from utils.message_utils import send_long_message
        await send_long_message(message, response)
    else:
        await message.answer(response, parse_mode="HTML")
