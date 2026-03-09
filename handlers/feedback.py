from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import config
from database.db import update_user_activity

router = Router()

class FeedbackState(StatesGroup):
    waiting_for_feedback = State()

@router.message(Command("feedback"))
@router.message(F.text == "📝 Обратная связь")
async def cmd_feedback(message: types.Message, state: FSMContext):
    """Start feedback process"""
    await message.answer("📝 Напиши свое сообщение для администратора (предложение, ошибка или отзыв):")
    await state.set_state(FeedbackState.waiting_for_feedback)

@router.message(FeedbackState.waiting_for_feedback)
async def process_feedback(message: types.Message, state: FSMContext, bot: Bot):
    """Process and forward feedback to admin"""
    feedback_text = message.text
    user_info = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
    
    admin_msg = (
        f"📩 <b>Новое сообщение от гида!</b>\n\n"
        f"От: {user_info} ({message.from_user.full_name})\n"
        f"Сообщение: {feedback_text}"
    )
    
    try:
        await bot.send_message(config.ADMIN_ID, admin_msg, parse_mode="HTML")
        await message.answer("✅ Твое сообщение отправлено администратору. Спасибо!")
        # Track activity
        await update_user_activity(message.from_user.id, "feedback")
    except Exception as e:
        await message.answer("❌ Произошла ошибка при отправке сообщения. Попробуй позже.")
        
    await state.clear()
