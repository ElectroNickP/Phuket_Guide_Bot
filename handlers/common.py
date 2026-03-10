from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, Command
from loguru import logger
from utils.keyboards import get_main_menu_keyboard, get_admin_menu_keyboard
from config import config
from sqlalchemy import select
from database.db import AsyncSessionLocal, update_user_activity
from database.models import User, AppSettings
from services.google_sheets import google_sheets
from services.scheduler import cache_user_schedule
import datetime

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message, bot: Bot):
    """Start command handler with detailed logging"""
    logger.info(f"Start command handler entered for {message.from_user.id}")
    try:
        async with AsyncSessionLocal() as session:
            logger.debug(f"Checking DB for user {message.from_user.id}")
            query = select(User).where(User.telegram_id == message.from_user.id)
            result = await session.execute(query)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.info(f"Registering new user {message.from_user.id}")
                # Registration logic
                try:
                    user = User(
                        telegram_id=message.from_user.id,
                        username=message.from_user.username,
                        full_name=message.from_user.full_name
                    )
                    session.add(user)
                    await session.commit()
                    logger.info(f"New user registered: {message.from_user.id} (@{message.from_user.username})")
                    
                    # Pre-cache schedule
                    try:
                        sheet = await google_sheets.get_current_month_sheet()
                        if sheet:
                            staff, freelance = google_sheets.parse_guides(sheet)
                            all_guides = staff + freelance
                            now = datetime.datetime.now()
                            tomorrow = now + datetime.timedelta(days=1)
                            await cache_user_schedule(session, bot, user, sheet, all_guides, now, notify=False)
                            await cache_user_schedule(session, bot, user, sheet, all_guides, tomorrow, notify=False)
                            await session.commit()
                    except Exception as cache_err:
                        logger.error(f"Failed to pre-cache for new user: {cache_err}")
                    
                except Exception as e:
                    await session.rollback()
                    logger.warning(f"Registration failed: {e}")
                    query = select(User).where(User.telegram_id == message.from_user.id)
                    result = await session.execute(query)
                    user = result.scalar_one_or_none()
            
            logger.debug(f"Updating activity for {message.from_user.id}")
            await update_user_activity(message.from_user.id, "start")
        
        logger.debug(f"Determining keyboard for {message.from_user.id}")
        is_admin = (message.from_user.id == config.ADMIN_ID)
        logger.debug(f"User {message.from_user.id} is_admin: {is_admin} (Config ADMIN_ID: {config.ADMIN_ID})")
        
        if is_admin:
            logger.debug("Calling get_admin_menu_keyboard")
            kb = get_admin_menu_keyboard()
        else:
            logger.debug("Calling get_main_menu_keyboard")
            kb = get_main_menu_keyboard()
        
        logger.info(f"Sending greeting to {message.from_user.id}")
        await message.answer(
            f"Привет, {message.from_user.first_name}! 👋\n\n"
            "Я бот для управления расписанием гидов.\n"
            "Используй кнопки ниже для навигации.",
            reply_markup=kb
        )
        logger.info(f"Greeting sent successfully to {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"CRITICAL ERROR in cmd_start for {message.from_user.id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await message.answer("❌ Произошла ошибка при запуске бота. Пожалуйста, попробуйте позже.")

@router.message(F.text == "🔙 Главное меню")
async def back_to_main(message: types.Message, bot: Bot):
    await cmd_start(message, bot)

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Help command handler"""
    await message.answer(
        "Доступные команды:\n"
        "/start - Начать работу\n"
        "/schedule - Мое расписание на сегодня/завтра\n"
        "/status - Мой статус (фикс/фриланс)\n"
        "/help - Справка"
    )
