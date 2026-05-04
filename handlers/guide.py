import datetime
import re
from utils.time import get_phuket_now, get_phuket_today
from sqlalchemy import update, select
import html
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from services.google_sheets import google_sheets
from services.sea_plan import sea_plan_service
from services.translator import translate_to_english
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from config import config
from database.models import UserRole, ReportSubmission, WakeUpConfirmation
from database.db import AsyncSessionLocal, update_user_activity
from utils.keyboards import get_schedule_keyboard, get_sea_plan_keyboard, get_land_plan_keyboard, get_np_keyboard, get_suggested_pax_keyboard, get_suggested_cot_keyboard, get_suggested_captain_keyboard, get_suggested_status_keyboard
from utils.message_utils import send_long_message
from loguru import logger

router = Router()

class ReportStates(StatesGroup):
    waiting_for_report_type = State() # Sea or Land
    waiting_for_report_pax = State()
    waiting_for_report_np = State()
    waiting_for_report_captain = State()
    waiting_for_report_cot = State()
    waiting_for_report_start_time = State()
    waiting_for_report_end_time = State()
    waiting_for_report_status = State()
    waiting_for_problem_description = State()
    waiting_for_report_confirm = State()

class WakeUpStates(StatesGroup):
    waiting_for_problem_description = State()

@router.message(F.text == "🚀 Начать программу")
async def cmd_start_report(message: types.Message, state: FSMContext, **data):
    """Entry point for Start Program report"""
    await state.update_data(is_end_report=False)
    target_date = get_phuket_now().date()
    await _initiate_report_filling(message, state, target_date, **data)

@router.message(F.text == "🏁 Завершить программу")
async def cmd_finish_report(message: types.Message, state: FSMContext, **data):
    """Entry point for Finish Program report"""
    await state.update_data(is_end_report=True)
    target_date = get_phuket_now().date()
    await _initiate_report_filling(message, state, target_date, **data)

async def _initiate_report_filling(message: types.Message, state: FSMContext, target_date: datetime.date, **data):
    """Common logic to start report filling process for a specific date"""
    date_str = target_date.strftime("%d.%m")
    await state.update_data(target_date=target_date.isoformat(), date_str=date_str)
    
    # Impersonation Check (Tester Mode)
    imp_user = data.get("impersonated_user")
    
    state_data = await state.get_data()
    username = state_data.get("proxy_username") or (imp_user["username"] if imp_user else message.from_user.username)
    
    if not username:
        await message.answer("❌ Ошибка: Не удалось определить @username.")
        await state.clear()
        return

    # Use answer if it's a message, edit_text if it's a callback (though here it's always message now)
    sent_msg = await message.answer(f"🔍 Ищу программы для @{username} на {date_str}...")
    
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
        
        await message.answer(
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
            
            await message.answer(
                f"🚐 <b>Программа:</b> {plan.program}\n\n"
                f"👥 Введите <b>фактическое</b> количество пассажиров (взр/дет/инф)" + 
                (" или нажмите кнопку ниже, если ничего не изменилось:\n" if reply_markup else ":\n") +
                f"<i>Например: 10/1/0</i>",
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            await state.set_state(ReportStates.waiting_for_report_pax)
        else:
            await sent_msg.edit_text(f"❌ На {date_str} программы для @{username} не найдены.")
            await state.clear()
    

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

async def _ask_or_autofill_start_time(message: types.Message, state: FSMContext, prefix: str = ""):
    """
    For finish reports: tries to auto-fetch start_time from today's start report in DB.
    If found: fills it automatically and moves to end_time prompt.
    If not found: warns guide and asks them to input start_time manually.
    For start reports: simply asks for start_time.
    """
    data = await state.get_data()
    is_end_report = data.get("is_end_report", False)
    
    if is_end_report:
        # Look for today's start report for this guide+program
        username = data.get("proxy_username") or message.chat.username
        program = data.get("program", "")
        today_start = datetime.datetime.combine(get_phuket_today(), datetime.time.min)
        today_end = today_start + datetime.timedelta(days=1)
        
        async with AsyncSessionLocal() as session:
            q = select(ReportSubmission).where(
                ReportSubmission.guide_username == username,
                ReportSubmission.report_type == "start",
                ReportSubmission.program_name == program,
                ReportSubmission.date >= today_start,
                ReportSubmission.date < today_end,
                ReportSubmission.start_time.isnot(None)
            ).order_by(ReportSubmission.timestamp.desc())
            result = await session.execute(q)
            start_report = result.scalars().first()
        
        if start_report and start_report.start_time:
            # ✅ Auto-fill start_time from the start report
            await state.update_data(start_time=start_report.start_time)
            await message.answer(
                f"{prefix}"
                f"✅ <b>Время старта</b> автоматически взято из утреннего отчёта: "
                f"<b>{start_report.start_time}</b>\n\n"
                "🏁 Теперь введите <b>время завершения</b> программы (например, 18:30):",
                parse_mode="HTML"
            )
            await state.set_state(ReportStates.waiting_for_report_end_time)
        else:
            # ⚠️ No start report found — warn and ask manually
            await message.answer(
                f"{prefix}"
                "⚠️ <b>Внимание!</b> Не найден отчёт о <b>СТАРТЕ</b> программы на сегодня.\n"
                "Пожалуйста, не забудьте сдать его.\n\n"
                "🕘 Введите <b>время старта</b> программы вручную (например, 8:30):",
                parse_mode="HTML"
            )
            await state.set_state(ReportStates.waiting_for_report_start_time)
    else:
        # Start report: ask as normal
        await message.answer(
            f"{prefix}"
            "🕘 Введите <b>время старта</b> программы (например, 8:30):",
            parse_mode="HTML"
        )
        await state.set_state(ReportStates.waiting_for_report_start_time)

@router.callback_query(F.data.startswith("report_cot_"), ReportStates.waiting_for_report_cot)
async def process_report_cot_callback(callback: types.CallbackQuery, state: FSMContext):
    cot_val = callback.data.replace("report_cot_", "")
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.update_data(cot=cot_val)
    await _ask_or_autofill_start_time(callback.message, state, prefix=f"✅ Выбрано: {cot_val}\n\n")
    await callback.answer()

@router.message(ReportStates.waiting_for_report_cot)
async def process_report_cot(message: types.Message, state: FSMContext):
    await state.update_data(cot=message.text.strip())
    await _ask_or_autofill_start_time(message, state)

@router.message(ReportStates.waiting_for_report_start_time)
async def process_report_start_time(message: types.Message, state: FSMContext):
    await state.update_data(start_time=message.text.strip())
    data = await state.get_data()
    
    if data.get("is_end_report"):
        await message.answer("🏁 Введите <b>время завершения</b> программы (например, 18:30):", parse_mode="HTML")
        await state.set_state(ReportStates.waiting_for_report_end_time)
    else:
        await message.answer(
            "📝 Есть ли какие-то проблемы или пожелания?\n(Если всё хорошо, нажмите «No problem»)",
            reply_markup=get_suggested_status_keyboard()
        )
        await state.set_state(ReportStates.waiting_for_report_status)

@router.message(ReportStates.waiting_for_report_end_time)
async def process_report_end_time(message: types.Message, state: FSMContext):
    await state.update_data(end_time=message.text.strip())
    await message.answer(
        "📝 Есть ли какие-то проблемы или пожелания?\n(Если всё хорошо, нажмите «No problem»)",
        reply_markup=get_suggested_status_keyboard()
    )
    await state.set_state(ReportStates.waiting_for_report_status)

async def _send_final_report(message_or_callback, state: FSMContext, status_text: str):
    """Build and display the final report preview. status_text must be 'NO PROBLEM' or 'PROBLEM'."""
    await state.update_data(status=status_text)
    data = await state.get_data()
    user = message_or_callback.from_user
    username = data.get("proxy_username") or user.username
    np_lines = "".join([f"NP {k}: {v}\n" for k, v in data.get("np_data", {}).items()])

    is_end_report = data.get('is_end_report')
    date_formatted = data.get('date_str', '').replace('.', '_')

    is_problem = status_text.strip().upper() == "PROBLEM"
    status_suffix = "_problem" if is_problem else "_no_problem"

    if is_end_report:
        title_emoji = "🏁"
        hashtag = f"#End_program_report\n#End_program_report_{date_formatted}\n#End_program_report{status_suffix}"
        time_info = (
            f"🚀 <b>Start program:</b> {data.get('start_time')}\n"
            f"🏁 <b>End program:</b> {data.get('end_time')}\n"
        )
    else:
        title_emoji = "🚀"
        hashtag = f"#Start_program_report\n#Start_program_report_{date_formatted}\n#Start_program_report{status_suffix}"
        time_info = f"🚀 <b>Start program:</b> {data.get('start_time')}\n"

    is_sea = data.get('report_type') == "SEA"
    boat_line = f"🚢 <b>Boat:</b> {data.get('boat', '---')}\n" if is_sea else ""
    captain_label = "Captain" if is_sea else "Driver"

    status_icon = "✅" if not is_problem else "⚠️"
    program_name = data.get('program', '---')
    problem_description = data.get('problem_description', '')

    report = (
        f"{title_emoji} <b>{program_name}</b>\n"
        f"{status_icon} <b>Status:</b> {status_text.upper()}\n"
        f"👤 <b>Guide:</b> @{username}\n\n"
        f"📅 <b>Date:</b> {data.get('date_str')}\n"
        f"👤 <b>Thai guide:</b> {data.get('thai_guide')}\n"
        f"{boat_line}"
        f"👥 <b>Pax:</b> {data.get('pax_actual')}\n"
        f"{np_lines}"
        f"👨‍✈️ <b>{captain_label}:</b> {data.get('captain')}\n"
        f"💵 <b>COT collected:</b> {data.get('cot')}\n"
        f"{time_info}"
    )

    if is_problem and problem_description:
        report += f"⚠️ <b>Problem description:</b> {problem_description}\n"
        problem_description_en = data.get('problem_description_en', '')
        if problem_description_en:
            report += f"\n🇬🇧 <b>Auto translation:</b> {problem_description_en}\n"

    report += f"\n{hashtag}"

    if is_problem:
        report += "\n\nNotify Hotline: @HOT_LINE"

    await state.update_data(final_report_text=report)

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
    await state.update_data(problem_description='')
    await _send_final_report(callback, state, "NO PROBLEM")
    await callback.answer()

@router.callback_query(F.data == "report_status_problem", ReportStates.waiting_for_report_status)
async def process_report_status_problem(callback: types.CallbackQuery, state: FSMContext):
    """Guide pressed ⚠️ Problem — ask for a description."""
    await callback.message.edit_text("✏️ Опишите проблему:")
    await state.set_state(ReportStates.waiting_for_problem_description)
    await callback.answer()

@router.message(ReportStates.waiting_for_problem_description)
async def process_problem_description(message: types.Message, state: FSMContext):
    """Receive the guide's free-text problem description and auto-translate it."""
    description = message.text.strip()
    # Translate before building the report (runs in thread pool, bob never blocks)
    translation = await translate_to_english(description)
    await state.update_data(
        problem_description=description,
        problem_description_en=translation or '',
    )
    await _send_final_report(message, state, "PROBLEM")

@router.message(ReportStates.waiting_for_report_status)
async def process_report_status(message: types.Message, state: FSMContext):
    """Fallback: if guide types something instead of pressing a button."""
    await message.answer(
        "Пожалуйста, используйте кнопки выше для выбора статуса.",
        reply_markup=get_suggested_status_keyboard()
    )

@router.callback_query(F.data == "report_confirm", ReportStates.waiting_for_report_confirm)
async def process_report_confirm(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    
    data = await state.get_data()
    report_text = data.get("final_report_text")
    
    if report_text:
        try:
            is_end_report = data.get("is_end_report", False)
            topic_id = config.REPORT_FINISH_TOPIC_ID if is_end_report else config.REPORT_START_TOPIC_ID
            
            await callback.bot.send_message(
                chat_id=config.REPORT_GROUP_ID,
                message_thread_id=topic_id,
                text=report_text,
                parse_mode="HTML"
            )
            
            # Additional sending for LAND reports
            if data.get("report_type") == "LAND" and getattr(config, "LAND_REPORT_DUPLICATE_GROUP_ID", None):
                try:
                    await callback.bot.send_message(
                        chat_id=config.LAND_REPORT_DUPLICATE_GROUP_ID,
                        message_thread_id=getattr(config, "LAND_REPORT_DUPLICATE_TOPIC_ID", None),
                        text=report_text,
                        parse_mode="HTML"
                    )
                except Exception as e2:
                    logger.error(f"Failed to copy land report to duplicate group: {e2}")
        except Exception as e:
            logger.error(f"Failed to send report to group {config.REPORT_GROUP_ID}: {e}")
            await callback.message.answer(f"⚠️ Ошибка при отправке в группу: {e}")

    # Record submission in DB
    try:
        async with AsyncSessionLocal() as session:
            status_text = data.get("status", "No problem")
            status_val = "ok" if status_text.strip().lower() == "no problem" else "problem"
            
            is_end_report = data.get("is_end_report", False)
            report_type_val = "finish" if is_end_report else "start"
            
            submission = ReportSubmission(
                guide_username=data.get("proxy_username") or callback.from_user.username,
                program_name=data.get("program", "Unknown"),
                status=status_val,
                report_type=report_type_val,
                start_time=data.get("start_time") if not is_end_report else None,
                end_time=data.get("end_time") if is_end_report else None,
                date=get_phuket_now() # Normalized to today
            )
            session.add(submission)
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to record report submission: {e}")

    # Update activity counters
    try:
        from database.db import update_user_activity
        act_type = "finish" if data.get("is_end_report") else "start"
        await update_user_activity(callback.from_user.id, action=act_type)
    except Exception as e:
        logger.error(f"Failed to update activity counter on report: {e}")

    if data.get("is_end_report"):
        thanks_msg = "✅ <b>Отчет о завершении принят!</b>\n\nСпасибо за отличную работу сегодня! Отдыхай и набирайся сил, до встречи! 🌟"
    else:
        thanks_msg = "✅ <b>Отчет успешно отправлен!</b>\n\nСпасибо, удачной программы!"

    await callback.message.reply(thanks_msg, parse_mode="HTML")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "report_edit", ReportStates.waiting_for_report_confirm)
async def process_report_edit(callback: types.CallbackQuery, state: FSMContext, **data):
    await callback.message.edit_text("❌ Заполнение отчета отменено. Начинаем заново...", reply_markup=None)

    # Preserve key flags across state reset
    state_data = await state.get_data()
    proxy_username = state_data.get("proxy_username")
    is_end_report = state_data.get("is_end_report", False)  # BUG FIX: was lost on clear()

    await state.clear()
    await state.update_data(
        is_end_report=is_end_report,
        **({"proxy_username": proxy_username} if proxy_username else {}),
    )

    target_date = get_phuket_now().date()
    await _initiate_report_filling(callback.message, state, target_date, **data)
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
@router.message(F.text == "📚 Библиотека гида")
async def cmd_guide_library(message: types.Message):
    """Guide Library — Coming Soon"""
    await message.answer(
        "📚 <b>Библиотека гида</b>\n\n"
        "🚧 <i>Раздел находится в разработке.</i>\n\n"
        "Скоро здесь появятся:\n"
        "• 📖 Подробные описания программ и маршрутов\n"
        "• 🗺 Гайды по ключевым локациям Пхукета\n"
        "• 📋 Шаблоны и чек-листы для работы\n"
        "• 🌊 Информация по лодкам, пирсам и нацпаркам\n"
        "• 💡 Советы и лучшие практики для гидов\n\n"
        "Следите за обновлениями! 🌟",
        parse_mode="HTML"
    )

@router.message(F.text == "📅 Моё расписание")
async def cmd_schedule_4day(message: types.Message):
    """Show 4-day schedule report directly"""
    username = message.from_user.username
    if not username:
        await message.answer("❌ У тебя не установлен username в Телеграм. Пожалуйста, установи его.")
        return
        
    sent_msg = await message.answer("🔍 Загружаю твоё расписание на 4 дня...")
    
    try:
        data = await google_sheets.get_guide_4day_data(username)
        
        response = f"📋 <b>Расписание для @{username}</b>\n\n"
        for item in data:
            response += f"{item['label']} ({item['date'].strftime('%d.%m')}): <b>{item['sched']}</b>\n"
            
        await sent_msg.edit_text(response, parse_mode="HTML")
        
        # Track activity
        await update_user_activity(message.from_user.id, "schedule_4day")
    except Exception as e:
        logger.exception(f"Error fetching 4-day schedule for @{username}: {e}")
        await sent_msg.edit_text("❌ Произошла ошибка при получении расписания. Попробуй позже.")

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

@router.callback_query(F.data.startswith("guestlist_land_"))
async def process_guest_list_land(callback: types.CallbackQuery, **data):
    # Impersonation Check (Tester Mode)
    imp_user = data.get("impersonated_user")
    try:
        # data is guestlist_land_dd.mm_index_username
        parts = callback.data.split('_', 4)
        date_str = parts[2]
        plan_idx = int(parts[3])
        target_username = parts[4] if len(parts) > 4 else None
        target_date = datetime.datetime.strptime(f"{date_str}.{get_phuket_today().year}", "%d.%m.%Y").date()
    except (ValueError, IndexError):
        await callback.answer("Ошибка формата данных", show_alert=True)
        return

    username = target_username or (imp_user["username"] if imp_user else callback.from_user.username)
    if not username:
        await callback.answer("Для работы требуется @username в Telegram.", show_alert=True)
        return

    plans = await sea_plan_service.get_guide_land_plan(username, target_date)
    if not plans or plan_idx >= len(plans):
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    plan = plans[plan_idx]
    
    if not plan.guests:
        await callback.message.answer(f"📋 Список гостей пуст для программы: {plan.program}")
        return

    await callback.answer("Загружаю список гостей...")

    response = f"📋 <b>Список гостей ({date_str})</b>\n"
    response += f"🚐 <b>{plan.program}</b>\n\n"
    
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

@router.callback_query(F.data.startswith("land_"))
async def process_land_plan_guide(callback: types.CallbackQuery, **data):
    # Impersonation Check (Tester Mode)
    imp_user = data.get("impersonated_user")
    
    is_today = callback.data == "land_today"
    target_date = get_phuket_today() if is_today else get_phuket_today() + datetime.timedelta(days=1)
    
    username = imp_user["username"] if imp_user else callback.from_user.username
    if not username:
        await callback.answer("Для работы требуется @username в Telegram.", show_alert=True)
        return

    await callback.answer(f"Загружаю план на суше ({target_date.strftime('%d.%m')})...")
    await _send_land_plan_for_date(callback.message, username, target_date)

async def _send_land_plan_for_date(message: types.Message, username: str, target_date: datetime.date):
    """Helper to fetch and send land plan for a specific user and date"""
    date_str = target_date.strftime("%d.%m")
    plans = await sea_plan_service.get_guide_land_plan(username, target_date)
    
    if not plans:
        await message.answer(f"🚐 <b>План на суше ({date_str})</b>\n\nНа этот день ваших заказов не найдено.", parse_mode="HTML")
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
            f"📅 <b>Date:</b> {plan.date}\n"
            f"🏝️ <b>Program:</b> {plan.program}\n"
        )
        if getattr(plan, 'thai_guide', None):
            response += f"👤 <b>Thai guide:</b> {plan.thai_guide}\n"
        response += f"🪑 <b>Total PAX:</b> {plan.pax_string}\n"
        
        if plan.guides:
            response += "🧭 <b>Guide(s):</b>\n"
            for g in plan.guides:
                me_tag = " (ВЫ)" if g.is_me else ""
                response += f"  • {g.full_info}{me_tag} (P/U: {g.pickup_time} @ {g.pickup_location})\n"
        
        if plan.bus:
            response += f"🚌 <b>Bus:</b> <code>{plan.bus}</code>\n"
        
        response += f"👨‍✈️ <b>Driver:</b> {driver_display}\n"
        response += f"💵 <b>COT:</b> {cot_info}\n\n"
        response += f"🏨 <b>First hotel (P/U):</b> {first_hotel_info}\n"
        
        # Add Guest List button
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Список гостей", callback_data=f"guestlist_land_{date_str}_{i}_{username}")
        
        await message.answer(response, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("wakeup_ok_"))
async def process_wakeup_ok(callback: types.CallbackQuery):
    # Data format: wakeup_ok_{p_time}_{username}
    parts = callback.data.split("_", 3)
    p_time = parts[2]
    # Part 3 holds the username if present (from new callback data)
    username = parts[3] if len(parts) > 3 else callback.from_user.username
    
    now = get_phuket_now()
    today_min = datetime.datetime.combine(now.date(), datetime.time.min)
    
    prog_name = "---"
    async with AsyncSessionLocal() as session:
        # Get program name first
        q_fetch = select(WakeUpConfirmation).where(
            WakeUpConfirmation.guide_username == username,
            WakeUpConfirmation.date == today_min,
            WakeUpConfirmation.pickup_time == p_time
        )
        res = await session.execute(q_fetch)
        conf = res.scalars().first()
        if conf:
            prog_name = conf.program_name or "---"

        # Update status
        q = update(WakeUpConfirmation).where(
            WakeUpConfirmation.guide_username == username,
            WakeUpConfirmation.date == today_min,
            WakeUpConfirmation.pickup_time == p_time,
            WakeUpConfirmation.status == "pending"
        ).values(status="confirmed", confirmed_at=now)
        await session.execute(q)
        await session.commit()
    
    await callback.message.edit_text(f"✅ <b>Подтверждено!</b> (Пикап: {p_time})\nХорошей работы!", parse_mode="HTML")
    
    # Send Program Overview (Land Plan) automatically
    await _send_land_plan_for_date(callback.message, username, now.date())

    # Notify Good Morning topic
    try:
        msg = (
            f"☀️ <b>Good morning! Пора в новый день</b>\n\n"
            f"👤 <b>Guide:</b> @{username}\n"
            f"🏝️ <b>Program:</b> {prog_name}\n"
            f"⏰ <b>Pickup:</b> {p_time}\n"
            f"✅ <b>Confirmed:</b> {now.strftime('%H:%M')}"
        )
        await callback.bot.send_message(
            chat_id=config.REPORT_GROUP_ID,
            message_thread_id=config.WAKEUP_LOG_TOPIC_ID,
            text=msg,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send Good Morning notification: {e}")

    await callback.answer("Подтверждено!")

@router.callback_query(F.data.startswith("wakeup_problem_"))
async def process_wakeup_problem(callback: types.CallbackQuery, state: FSMContext):
    # Data format: wakeup_problem_{p_time}_{username}
    parts = callback.data.split("_", 3)
    if len(parts) >= 4:
        p_time = parts[2]
        username = parts[3]
    else:
        # fallback if format is somehow wakeup_problem_08:50 without username
        p_time = parts[2]
        username = callback.from_user.username
        
    await state.update_data(wakeup_p_time=p_time, wakeup_username=username)
    await state.set_state(WakeUpStates.waiting_for_problem_description)
    
    await callback.message.edit_text("Пожалуйста, коротко опишите проблему в одном сообщении:", parse_mode="HTML")
    await callback.answer()

@router.message(WakeUpStates.waiting_for_problem_description)
async def process_wakeup_problem_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    p_time = data.get("wakeup_p_time")
    username = data.get("wakeup_username")
    
    if not p_time or not username:
        await state.clear()
        return
        
    problem_text = message.text.strip()
    
    # Auto-translate
    translation = await translate_to_english(problem_text)
    
    now = get_phuket_now()
    today_min = datetime.datetime.combine(now.date(), datetime.time.min)
    
    # Save problem to DB
    try:
        async with AsyncSessionLocal() as session:
            q = update(WakeUpConfirmation).where(
                WakeUpConfirmation.guide_username == username,
                WakeUpConfirmation.date == today_min,
                WakeUpConfirmation.pickup_time == p_time
            ).values(status="problem", confirmed_at=now)
            await session.execute(q)
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to update wakeup status to problem for {username}: {e}")
        
    await message.answer("⚠️ <b>Передано в HOT LINE!</b>\nПожалуйста, свяжитесь с координатором.", parse_mode="HTML")
    await state.clear()
    
    # Notify Hotline
    try:
        async with AsyncSessionLocal() as session:
            q = select(WakeUpConfirmation).where(
                WakeUpConfirmation.guide_username == username,
                WakeUpConfirmation.date == today_min,
                WakeUpConfirmation.pickup_time == p_time
            )
            res = await session.execute(q)
            conf = res.scalars().first()
            prog_name = conf.program_name if conf else "---"
            
        msg = (
            f"🆘 <b>ПРОБЛЕМА У ГИДА (ПРОБУЖДЕНИЕ)!</b>\n\n"
            f"Программа: <b>{prog_name}</b>\n"
            f"Гид: @{username}\n"
            f"Пикап: {p_time}\n"
            f"⚠️ <b>ОПИСАНИЕ ПРИЧИНЫ:</b> {problem_text}\n"
        )
        if translation:
            msg += f"\n🇬🇧 <b>Auto translation:</b> {translation}\n"
            
        await message.bot.send_message(config.REPORT_GROUP_ID, msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to notify hotline about guide problem: {e}")
