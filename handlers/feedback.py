from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import config
from database.db import update_user_activity
from loguru import logger

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
async def process_feedback(message: types.Message, state: FSMContext, bot: Bot, **data):
    """Process and forward feedback to admin"""
    # 🛡 Safeguard: if user clicks a menu button or types a command, cancel feedback
    MENU_BUTTONS = [
        "📅 Моё расписание", "🌊 План на море", "🚐 План на суше", "👤 Мой статус",
        "🚀 Начать программу", "🏁 Завершить программу", "📝 Обратная связь",
        "🆘 Нужна помощь", "📚 Библиотека гида", "🔙 Главное меню",
        "👁 Мониторинг гидов", "👁 Контроль Смены", "🌊 Мониторинг моря",
        "🚐 Мониторинг суши", "📊 Статистика", "🔍 Тест-Аудит",
        "📋 Job Order", "📅 Общее расписание", "📝 Отчет за гида",
        "🔍 Тест Пробуждения", "🆘 Тест SOS", "⏱ Интервал", "📋 Логи",
        "🔗 Сменить таблицу", "🔗 Сменить таблицу (Море)"
    ]
    
    if message.text in MENU_BUTTONS or (message.text and message.text.startswith("/")):
        await state.clear()
        await message.answer(
            f"⚠️ <b>Отправка обратной связи отменена.</b>\n\n"
            f"Пожалуйста, нажмите кнопку «{message.text}» ещё раз, чтобы выполнить команду.",
            parse_mode="HTML"
        )
        return

    # Impersonation Check (Tester Mode)
    imp_user = data.get("impersonated_user")
    
    feedback_text = message.text
    if imp_user:
        user_info = f"@{imp_user['username']} (ИМИТАЦИЯ от @{message.from_user.username})"
    else:
        user_info = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
    
    admin_msg = (
        f"📩 <b>Новое сообщение от гида!</b>\n\n"
        f"От: {user_info} ({message.from_user.full_name})\n"
        f"Сообщение: {feedback_text}"
    )
    
    try:
        # Forward to all admins
        for admin_id in config.admin_id_list:
            await bot.send_message(admin_id, admin_msg, parse_mode="HTML")
        await message.answer("✅ Твое сообщение отправлено администратору. Спасибо!")
        await update_user_activity(message.from_user.id, "feedback")
    except Exception as e:
        logger.exception(f"Error sending feedback from {message.from_user.id}: {e}")
        await message.answer("❌ Произошла ошибка при отправке сообщения. Попробуй позже.")
    
    await state.clear()
