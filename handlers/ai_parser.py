from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
import json

from ai_core.service import ai_core
from database.db import AsyncSessionLocal
from database.models import OperationalReport
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State, any_state
from aiogram.filters import StateFilter

router = Router()

class AIReportState(StatesGroup):
    waiting_for_confirmation = State()

@router.message(Command("smart_report"))
async def handle_smart_report_command(message: types.Message):
    await message.answer("🤖 Отправьте мне текст в свободной форме (например: 'Залил Sea Ray 120 литров, сломалась рация'), и я сам сгенерирую отчет!")

@router.message(F.text.lower().startswith("отчет:"))
async def handle_free_form_report(message: types.Message, state: FSMContext):
    """
    Passes any message starting with 'Отчет:' to the AI parsing service.
    """
    text_to_parse = message.text[6:].strip() # remove "Отчет:"
    
    if len(text_to_parse) < 10:
        await message.answer("⚠️ Отчет слишком короткий. Напишите подробнее.")
        return
        
    wait_msg = await message.answer("⏳ <i>Анализирую отчет с помощью ИИ...</i>", parse_mode="HTML")
    
    try:
        parsed_data = await ai_core.parse_operational_report(text_to_parse)
        
        resp = "🧠 <b>Отчет распознан (Smart Parsing):</b>\n\n"
        resp += f"📝 <b>Тип:</b> {parsed_data.get('type')}\n"
        if parsed_data.get('boat_name'):
            resp += f"🚤 <b>Лодка:</b> {parsed_data.get('boat_name')}\n"
        if parsed_data.get('fuel_liters'):
            resp += f"⛽️ <b>Топливо:</b> {parsed_data.get('fuel_liters')} л.\n"
        if parsed_data.get('defects'):
            defects = "\n  - ".join(parsed_data.get('defects'))
            resp += f"⚒ <b>Дефекты:</b>\n  - {defects}\n"
        if parsed_data.get('comment'):
            resp += f"💬 <b>Комментарий:</b> {parsed_data.get('comment')}\n"
            
        resp += "\n<i>✅ Проверьте данные. Сохранить в базу?</i>"
        
        # Save to FSM
        await state.update_data(ai_report=parsed_data)
        await state.set_state(AIReportState.waiting_for_confirmation)
        
        # Inline Buttons
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Сохранить", callback_data="ai_report_save"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="ai_report_cancel")
        )
        
        await wait_msg.edit_text(resp, reply_markup=builder.as_markup(), parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"AI parsing error: {e}")
        await wait_msg.edit_text("❌ Произошла ошибка при анализе отчета. Попробуйте еще раз или напишите вручную.")

@router.callback_query(F.data == "ai_report_save")
async def save_ai_report(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    parsed_data = data.get("ai_report")
    
    if not parsed_data:
        await callback.message.edit_text("❌ Ошибка: Данные отчета устарели или утеряны.")
        await callback.answer()
        return
        
    try:
        async with AsyncSessionLocal() as session:
            new_report = OperationalReport(
                author_id=callback.from_user.id,
                author_username=callback.from_user.username or callback.from_user.full_name,
                report_type=parsed_data.get('type', 'general_note'),
                boat_name=parsed_data.get('boat_name'),
                fuel_liters=parsed_data.get('fuel_liters'),
                defects=",".join(parsed_data.get('defects', [])),
                comment=parsed_data.get('comment')
            )
            session.add(new_report)
            await session.commit()
            
        await callback.message.edit_text(callback.message.html_text + "\n\n<b>✅ Отчет успешно сохранен в базу данных!</b>", parse_mode="HTML")
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error saving AI report to DB: {e}")
        await callback.message.edit_text("❌ Ошибка при сохранении в базу данных.")
    finally:
        await callback.answer()

@router.callback_query(F.data == "ai_report_cancel")
async def cancel_ai_report(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Сохранение отчета отменено.")
    await callback.answer()

@router.message(F.text, StateFilter(any_state))
async def handle_conversational_chat(message: types.Message, state: FSMContext):
    """
    Catch-all conversational fallback for regular text messages using AICore.
    """
    # Clear state to rescue stuck users
    current_state = await state.get_state()
    if current_state is not None:
        logger.info(f"Clearing state {current_state} for user {message.from_user.id}")
        await state.clear()
        
    user_name = message.from_user.first_name or message.from_user.username or "Пользователь"
    
    if message.text.startswith("/"):
        return
        
    # Send typing action
    try:
        from aiogram.enums import ChatAction
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    except Exception:
        pass
        
    response = await ai_core.get_conversational_response(message.text, user_name)
    await message.answer(response)
