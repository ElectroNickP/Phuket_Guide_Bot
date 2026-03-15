from utils.time import get_phuket_now, get_phuket_today
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from services.google_sheets import google_sheets
from services.sea_plan import sea_plan_service
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from database.models import UserRole
from utils.keyboards import get_schedule_keyboard, get_sea_plan_keyboard, get_land_plan_keyboard, get_report_date_keyboard, get_np_keyboard, get_suggested_pax_keyboard, get_suggested_cot_keyboard, get_suggested_captain_keyboard, get_suggested_status_keyboard

router = Router()

class ReportStates(StatesGroup):
    waiting_for_report_date = State()
    waiting_for_report_type = State() # Sea or Land
    waiting_for_report_pax = State()
    waiting_for_report_np = State()
    waiting_for_report_captain = State()
    waiting_for_report_cot = State()
    waiting_for_report_start_time = State()
    waiting_for_report_status = State()
    waiting_for_report_confirm = State()

@router.message(F.text == "🚀 Начать программу")
async def cmd_start_report(message: types.Message, state: FSMContext):
    """Entry point for Start Program report"""
    await message.answer(
        "🚀 <b>Начинаем формирование отчета!</b>\n\n"
        "Для какого дня вы хотите создать отчет?",
        parse_mode="HTML",
        reply_markup=get_report_date_keyboard()
    )
    await state.set_state(ReportStates.waiting_for_report_date)

@router.callback_query(F.data.startswith("report_date_"), ReportStates.waiting_for_report_date)
async def process_report_date(callback: types.CallbackQuery, state: FSMContext, **data):
    # Impersonation Check (Tester Mode)
    imp_user = data.get("impersonated_user")
    
    is_tomorrow = "tomorrow" in callback.data
    target_date = get_phuket_now().date()
    if is_tomorrow:
        target_date += datetime.timedelta(days=1)
    
    date_str = target_date.strftime("%d.%m")
    await state.update_data(target_date=target_date.isoformat(), date_str=date_str)
    
    data = await state.get_data()
    username = data.get("proxy_username") or (imp_user["username"] if imp_user else callback.from_user.username)
    
    if not username:
        await callback.message.answer("❌ Ошибка: Не удалось определить @username.")
        await state.clear()
        return

    await callback.message.edit_text(f"🔍 Ищу программы для @{username} на {date_str}...")
    
    # Check Sea Plan first
    sea_plans = await sea_plan_service.get_guide_sea_plan(username, target_date)
    
    if sea_plans:
        # For now, we take the first plan if multiple (unlikely for a single guide start)
        plan = sea_plans[0]
        
        prog_names = [p.name for p in plan.programs]
        guests = await sea_plan_service.get_guest_list(target_date, prog_names)
        
        calculated_cot = 0
        for g in guests:
            try:
                cot_str = str(g.cot).strip()
                if '+' in cot_str:
                    calculated_cot += sum(int(x) for x in cot_str.split('+') if x.strip().isdigit())
                elif cot_str.isdigit():
                    calculated_cot += int(cot_str)
            except Exception:
                pass
                
        await state.update_data(
            report_type="SEA",
            boat=plan.boat,
            thai_guide=plan.thai_guide or "---",
            program=", ".join(prog_names),
            suggested_pax=plan.pax_string,
            suggested_cot=str(calculated_cot),
            np_data={} # To store PP, GB, HG
        )
        
        await callback.message.answer(
            f"🌊 <b>Программа:</b> {', '.join([p.name for p in plan.programs])}\n"
            f"🚢 <b>Лодка:</b> {plan.boat}\n"
            f"👥 Введите <b>фактическое</b> количество пассажиров (взр/дет/инф) или нажмите кнопку ниже, если ничего не изменилось:\n"
            f"<i>Например: 35/2/1</i>",
            parse_mode="HTML",
            reply_markup=get_suggested_pax_keyboard(plan.pax_string)
        )
        await state.set_state(ReportStates.waiting_for_report_pax)
    else:
        # Check Land Plan
        land_plans = await sea_plan_service.get_guide_land_plan(username, target_date)
        if land_plans:
            plan = land_plans[0]
            # Correctly use pre-calculated pax_string from DTO
            pax_str = plan.pax_string
            
            calculated_cot = 0
            if plan.guests:
                for g in plan.guests:
                    try:
                        cot_str = str(g.cot).strip()
                        if '+' in cot_str:
                            calculated_cot += sum(int(x) for x in cot_str.split('+') if x.strip().isdigit())
                        elif cot_str.isdigit():
                            calculated_cot += int(cot_str)
                    except Exception:
                        pass
                        
            await state.update_data(
                report_type="LAND",
                program=plan.program,
                suggested_pax=pax_str, 
                suggested_cot=str(calculated_cot),
                suggested_captain=plan.driver,
                thai_guide="---"
            )
            
            reply_markup = get_suggested_pax_keyboard(pax_str) if pax_str != "0/0/0" else None
            
            await callback.message.answer(
                f"🚐 <b>Программа:</b> {plan.program}\n\n"
                f"👥 Введите <b>фактическое</b> количество пассажиров (взр/дет/инф)" + 
                (" или нажмите кнопку ниже, если ничего не изменилось:\n" if reply_markup else ":\n") +
                f"<i>Например: 10/1/0</i>",
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            await state.set_state(ReportStates.waiting_for_report_pax)
        else:
            await callback.message.edit_text(f"❌ На {date_str} программы для @{username} не найдены.")
            await state.clear()
    
    await callback.answer()

@router.message(ReportStates.waiting_for_report_captain)
async def process_report_captain(message: types.Message, state: FSMContext):
    await state.update_data(captain=message.text.strip())
    data = await state.get_data()
    suggested_cot = data.get("suggested_cot", "0")
    
    await message.answer(
        "💵 Введите собранный <b>COT (Cash on Tour)</b> или нажмите кнопку (если есть):",
        parse_mode="HTML",
        reply_markup=get_suggested_cot_keyboard(suggested_cot)
    )
    await state.set_state(ReportStates.waiting_for_report_cot)

@router.callback_query(F.data == "report_captain_suggested", ReportStates.waiting_for_report_captain)
async def process_report_captain_suggested(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    captain_val = data.get("suggested_captain", "---")
    await callback.message.edit_reply_markup(reply_markup=None)
    
    await state.update_data(captain=captain_val)
    
    suggested_cot = data.get("suggested_cot", "0")
    
    await callback.message.answer(
        f"✅ Выбрано: {captain_val}\n\n"
        "💵 Введите собранный <b>COT (Cash on Tour)</b> или нажмите кнопку (если есть):",
        parse_mode="HTML",
        reply_markup=get_suggested_cot_keyboard(suggested_cot)
    )
    await state.set_state(ReportStates.waiting_for_report_cot)
    await callback.answer()

@router.callback_query(F.data.startswith("report_cot_"), ReportStates.waiting_for_report_cot)
async def process_report_cot_callback(callback: types.CallbackQuery, state: FSMContext):
    cot_val = callback.data.replace("report_cot_", "")
    await callback.message.edit_reply_markup(reply_markup=None)
    
    await state.update_data(cot=cot_val)
    
    await callback.message.answer(
        f"✅ Выбрано: {cot_val}\n\n"
        "🕘 Введите <b>время старта</b> программы (например, 8:30):",
        parse_mode="HTML"
    )
    await state.set_state(ReportStates.waiting_for_report_start_time)
    await callback.answer()

@router.message(ReportStates.waiting_for_report_cot)
async def process_report_cot(message: types.Message, state: FSMContext):
    await state.update_data(cot=message.text.strip())
    await message.answer("🕘 Введите <b>время старта</b> программы (например, 8:30):")
    await state.set_state(ReportStates.waiting_for_report_start_time)

@router.message(ReportStates.waiting_for_report_start_time)
async def process_report_start_time(message: types.Message, state: FSMContext):
    await state.update_data(start_time=message.text.strip())
    await message.answer(
        "📝 Есть ли какие-то проблемы или пожелания?\n(Если всё хорошо, нажмите «No problem»)",
        reply_markup=get_suggested_status_keyboard()
    )
    await state.set_state(ReportStates.waiting_for_report_status)

async def _send_final_report(message_or_callback, state: FSMContext, status_text: str):
    await state.update_data(status=status_text)
    data = await state.get_data()
    user = message_or_callback.from_user
    username = data.get("proxy_username") or user.username
    np_lines = "".join([f"NP {k}: {v}\n" for k, v in data.get("np_data", {}).items()])
    
    date_formatted = data.get('date_str', '').replace('.', '_')
    hashtags = f"#Start_program_report\n#Start_program_report_{date_formatted}"
    
    is_sea = data.get('report_type') == "SEA"
    boat_line = f"🚢 <b>Boat:</b> {data.get('boat', '---')}\n" if is_sea else ""
    captain_label = "Captain" if is_sea else "Driver"
    
    status_icon = "✅" if status_text.strip().lower() == "no problem" else "⚠️"
    
    report = (
        f"🚀 <b>Start program report</b>\n"
        f"{status_icon} <b>Status:</b> {status_text}\n"
        f"👤 <b>Guide:</b> @{username}\n\n"
        f"📋 <b>Program:</b> {data.get('program')}\n"
        f"📅 <b>Date:</b> {data.get('date_str')}\n"
        f"👤 <b>Thai guide:</b> {data.get('thai_guide')}\n"
        f"{boat_line}"
        f"👥 <b>Pax:</b> {data.get('pax_actual')}\n"
        f"{np_lines}"
        f"👨‍✈️ <b>{captain_label}:</b> {data.get('captain')}\n"
        f"💵 <b>COT collected:</b> {data.get('cot')}\n"
        f"🚀 <b>Start program:</b> {data.get('start_time')}\n\n"
        f"{hashtags}"
    )
    
    if status_text.strip().lower() != "no problem":
        report += "\n\nNotify Hotline: @HOT_LINE"
        
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить", callback_data="report_confirm")
    kb.button(text="✏️ Изменить", callback_data="report_edit")
    kb.adjust(1)
    
    if isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.answer(report, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await message_or_callback.answer(report, parse_mode="HTML", reply_markup=kb.as_markup())
    await state.set_state(ReportStates.waiting_for_report_confirm)

@router.callback_query(F.data == "report_status_ok", ReportStates.waiting_for_report_status)
async def process_report_status_ok(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await _send_final_report(callback, state, "No problem")
    await callback.answer()

@router.message(ReportStates.waiting_for_report_status)
async def process_report_status(message: types.Message, state: FSMContext):
    await _send_final_report(message, state, message.text.strip())

@router.callback_query(F.data == "report_confirm", ReportStates.waiting_for_report_confirm)
async def process_report_confirm(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply("✅ <b>Отчет успешно отправлен!</b>\n\nСпасибо, удачной программы!", parse_mode="HTML")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "report_edit", ReportStates.waiting_for_report_confirm)
async def process_report_edit(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Заполнение отчета отменено. Вы можете начать заново, выбрав дату.", reply_markup=None)
    
    data = await state.get_data()
    proxy_username = data.get("proxy_username")
    
    await state.clear()
    
    if proxy_username:
        await state.update_data(proxy_username=proxy_username)
        await callback.message.answer(
            f"Выберите дату отчета за гида @{proxy_username}:",
            reply_markup=get_report_date_keyboard()
        )
        await state.set_state(ReportStates.waiting_for_report_date)
    else:
        await callback.message.answer(
            "Выберите дату для отчета:",
            reply_markup=get_report_date_keyboard()
        )
        await state.set_state(ReportStates.waiting_for_report_date)
        
    await callback.answer()

@router.callback_query(F.data.startswith("report_pax_"), ReportStates.waiting_for_report_pax)
async def process_report_pax_callback(callback: types.CallbackQuery, state: FSMContext):
    pax_val = callback.data.replace("report_pax_", "")
    await callback.message.edit_reply_markup(reply_markup=None)
    
    await state.update_data(pax_actual=pax_val)
    data = await state.get_data()
    
    if data.get("report_type") == "SEA":
        await callback.message.answer(
            f"✅ Выбрано: {pax_val}\n\n"
            "🏞 <b>Национальные Парки</b>\n\n"
            "Выберите парк, чтобы указать сумму, или нажмите «Готово», если сборов нет или вы закончили ввод:",
            parse_mode="HTML",
            reply_markup=get_np_keyboard()
        )
        await state.set_state(ReportStates.waiting_for_report_np)
    else:
        suggested_captain = data.get("suggested_captain")
        reply_markup = get_suggested_captain_keyboard(suggested_captain) if suggested_captain else None
        
        caption_label = "капитана" if data.get("report_type") == "SEA" else "водителя"
        
        await callback.message.answer(
            f"✅ Выбрано: {pax_val}\n\n"
            f"👨‍✈️ Введите имя {caption_label}" + (" или выберите из списка:" if reply_markup else ":"),
            reply_markup=reply_markup
        )
        await state.set_state(ReportStates.waiting_for_report_captain)
    await callback.answer()

@router.message(ReportStates.waiting_for_report_pax)
async def process_report_pax(message: types.Message, state: FSMContext):
    pax_text = message.text.strip()
    if "/" not in pax_text and not pax_text.isdigit():
        await message.answer("❌ Пожалуйста, введите количество пассажиров в формате Взр/Дет/Инф (например: 35/2/1)")
        return
    await state.update_data(pax_actual=pax_text)
    data = await state.get_data()
    if data.get("report_type") == "SEA":
        await message.answer(
            "🏞 <b>Национальные Парки</b>\n\n"
            "Выберите парк, чтобы указать сумму, или нажмите «Готово», если сборов нет или вы закончили ввод:",
            parse_mode="HTML",
            reply_markup=get_np_keyboard()
        )
        await state.set_state(ReportStates.waiting_for_report_np)
    else:
        suggested_captain = data.get("suggested_captain")
        reply_markup = get_suggested_captain_keyboard(suggested_captain) if suggested_captain else None
        
        caption_label = "капитана" if data.get("report_type") == "SEA" else "водителя"
        
        await message.answer(
            f"👨‍✈️ Введите имя {caption_label}" + (" или выберите из списка:" if reply_markup else ":"),
            reply_markup=reply_markup
        )
        await state.set_state(ReportStates.waiting_for_report_captain)

@router.callback_query(F.data.startswith("report_np_"), ReportStates.waiting_for_report_np)
async def process_report_np_select(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "report_np_done":
        data = await state.get_data()
        suggested_captain = data.get("suggested_captain")
        reply_markup = get_suggested_captain_keyboard(suggested_captain) if suggested_captain else None
        
        caption_label = "капитана" if data.get("report_type") == "SEA" else "водителя"
        
        await callback.message.edit_text(
            f"👨‍✈️ Введите имя {caption_label}" + (" или выберите из списка:" if reply_markup else ":"),
            reply_markup=reply_markup
        )
        await state.set_state(ReportStates.waiting_for_report_captain)
        return
    np_type = callback.data.replace("report_np_", "")
    await state.update_data(current_np=np_type)
    await callback.message.answer(f"💵 Введите сумму для <b>{np_type}</b>:", parse_mode="HTML")

@router.message(ReportStates.waiting_for_report_np)
async def process_report_np_amount(message: types.Message, state: FSMContext):
    amount = message.text.strip()
    if not amount.isdigit():
        await message.answer("❌ Введите сумму цифрами.")
        return
    data = await state.get_data()
    np_type = data.get("current_np")
    if not np_type: return
    np_data = data.get("np_data", {})
    np_data[np_type] = amount
    await state.update_data(np_data=np_data, current_np=None)
    np_summary = "\n".join([f"• {k}: {v}" for k, v in np_data.items()])
    await message.answer(f"✅ <b>Введено:</b>\n{np_summary}\n\nПожалуйста, выберите следующий парк или нажмите «Готово»:", parse_mode="HTML", reply_markup=get_np_keyboard())
@router.message(F.text == "📅 Моё расписание")
async def cmd_schedule_buttons(message: types.Message):
    """Show schedule buttons"""
    await message.answer("📆 На какой день ты хочешь посмотреть расписание?", reply_markup=get_schedule_keyboard())

@router.callback_query(F.data.startswith("sched_"))
async def process_schedule_query(callback: types.CallbackQuery, **data):
    """Process inline buttons for schedule"""
    # Impersonation Check (Tester Mode)
    imp_user = data.get("impersonated_user")
    
    await callback.message.edit_text("🔍 Ищу расписание...")
    
    sheet = await google_sheets.get_current_month_sheet()
    if not sheet:
        await callback.message.edit_text("❌ Не удалось найти лист с расписанием на текущий месяц.")
        return

    staff, freelance = await google_sheets.parse_guides(sheet)
    all_guides = staff + freelance
    
    user_username = imp_user["username"] if imp_user else callback.from_user.username
    if not user_username:
        await callback.message.edit_text("❌ У тебя не установлен username в Телеграм. Пожалуйста, установи его.")
        return

    guide_info = next((g for g in all_guides if g['username'].lower() == user_username.lower()), None)
    
    if not guide_info:
        await callback.message.edit_text(f"❌ Я не нашел гида с username @{user_username} в таблице.")
        return

    is_tomorrow = "tomorrow" in callback.data
    target_date = get_phuket_now()
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
async def process_sea_query(callback: types.CallbackQuery, **data):
    """Process inline buttons for sea plan"""
    # Impersonation Check (Tester Mode)
    imp_user = data.get("impersonated_user")
    
    is_tomorrow = "tomorrow" in callback.data
    target_date = get_phuket_now().date()
    if is_tomorrow:
        target_date += datetime.timedelta(days=1)
        
    user_username = imp_user["username"] if imp_user else callback.from_user.username
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
            response += f"🚢 <b>Лодка:</b> {plan.boat}\n"
            response += f"⚓️ <b>Пирс:</b> {plan.pier or '---'}\n"
            response += f"👤 <b>Thai Guide:</b> {plan.thai_guide or '---'}\n"
            response += f"👥 <b>Гид(ы):</b> {', '.join([g.full_info for g in plan.guides])}\n"
            response += f"📝 <b>Программы:</b>\n"
            for prog in plan.programs:
                prog_text = f"{prog.name} ({prog.pax} pax)"
                if len(plan.guides) > 1 and prog.guide:
                    response += f"  • {prog_text} - {prog.short_guide}\n"
                else:
                    response += f"  • {prog_text}\n"
            response += f"📊 <b>GRAND TOTAL:</b> {plan.total_pax}\n\n"
        
        # Add a Guest List button if there are programs 
        guest_list_btn = None
        has_programs = any(len(p.programs) > 0 for p in plans)
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
async def cmd_status(message: types.Message, **data):
    # Impersonation Check (Tester Mode)
    imp_user = data.get("impersonated_user")
    
    # Track activity
    await update_user_activity(message.from_user.id, "status")
    
    sheet = await google_sheets.get_current_month_sheet()
    if not sheet:
        await message.answer("❌ Нет связи с таблицей.")
        return

    staff, freelance = await google_sheets.parse_guides(sheet)
    
    user_username = imp_user["username"] if imp_user else message.from_user.username
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
async def process_guest_list_guide(callback: types.CallbackQuery, **data):
    # Impersonation Check (Tester Mode)
    imp_user = data.get("impersonated_user")
    try:
        # data is guestlist_guide_dd.mm
        date_str = callback.data.split('_')[2]
        target_date = datetime.datetime.strptime(f"{date_str}.{get_phuket_today().year}", "%d.%m.%Y").date()
    except ValueError:
        await callback.answer("Ошибка формата даты", show_alert=True)
        return

    username = imp_user["username"] if imp_user else callback.from_user.username
    if not username:
        await callback.answer("Для работы требуется @username в Telegram.", show_alert=True)
        return

    plans = await sea_plan_service.get_guide_sea_plan(username, target_date)
    if not plans:
        await callback.answer("Не найдено программ на эту дату.", show_alert=True)
        return

    program_names = []
    for plan in plans:
        for prog in plan.programs:
            if prog.name not in program_names:
                program_names.append(prog.name)

    if not program_names:
        await callback.answer("У вас нет программ на эту дату.", show_alert=True)
        return

    await callback.answer("Загружаю список гостей...")

    guest_list = await sea_plan_service.get_guest_list(target_date, program_names)
    
    if not guest_list:
        await callback.message.answer(f"📋 Список гостей пуст или не найден для программ: {', '.join(program_names)}")
        return

    response = f"📋 <b>Список гостей ({date_str})</b>:\n\n"
    
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
    
    await send_long_message(callback.message, response)

@router.callback_query(F.data.startswith("land_"))
async def process_land_plan_guide(callback: types.CallbackQuery, **data):
    # Impersonation Check (Tester Mode)
    imp_user = data.get("impersonated_user")
    
    is_today = callback.data == "land_today"
    target_date = get_phuket_today() if is_today else get_phuket_today() + datetime.timedelta(days=1)
    date_str = target_date.strftime("%d.%m")

    username = imp_user["username"] if imp_user else callback.from_user.username
    if not username:
        await callback.answer("Для работы требуется @username в Telegram.", show_alert=True)
        return

    await callback.answer(f"Загружаю план на суше ({date_str})...")
    
    plans = await sea_plan_service.get_guide_land_plan(username, target_date)
    
    if not plans:
        await callback.message.answer(f"🚐 <b>План на суше ({date_str})</b>\n\nНа этот день ваших заказов не найдено.", parse_mode="HTML")
        return

    for plan in plans:
        response = f"🚐 <b>Job Order: {plan.program}</b>\n"
        response += f"📅 <b>Date:</b> {plan.date}\n\n"
        
        if plan.guides:
            response += "👤 <b>Guide(s):</b>\n"
            for g in plan.guides:
                me_tag = " (ВЫ)" if g.is_me else ""
                response += f"  • {g.full_info}{me_tag} (P/U: {g.pickup_time} @ {g.pickup_location})\n"
            response += "\n"
            
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
        
        await send_long_message(callback.message, response)
