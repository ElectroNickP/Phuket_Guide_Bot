from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, Command
from loguru import logger
from utils.keyboards import get_main_menu_keyboard, get_admin_menu_keyboard
from config import config
from sqlalchemy import select
from database.db import AsyncSessionLocal, update_user_activity
from services.google_sheets import google_sheets
from services.scheduler import cache_user_schedule
import datetime

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message, bot: Bot):
    """Start command handler"""
    async with AsyncSessionLocal() as session:
        query = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
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
                
                # Pre-cache schedule to detect future changes
                try:
                    sheet = await google_sheets.get_current_month_sheet()
                    if sheet:
                        staff, freelance = google_sheets.parse_guides(sheet)
                        all_guides = staff + freelance
                        now = datetime.datetime.now()
                        tomorrow = now + datetime.timedelta(days=1)
                        # We don't notify on registration, just cache
                        await cache_user_schedule(session, bot, user, sheet, all_guides, now, notify=False)
                        await cache_user_schedule(session, bot, user, sheet, all_guides, tomorrow, notify=False)
                        await session.commit()
                except Exception as cache_err:
                    logger.error(f"Failed to pre-cache for new user: {cache_err}")
                
            except Exception as e:
                await session.rollback()
                logger.warning(f"Registration failed (likely concurrent): {e}")
                # Try to fetch again
                query = select(User).where(User.telegram_id == message.from_user.id)
                result = await session.execute(query)
                user = result.scalar_one_or_none()
        
        # Track activity
        await update_user_activity(message.from_user.id, "start")
             
    kb = get_admin_menu_keyboard() if message.from_user.id == config.ADMIN_ID else get_main_menu_keyboard()
    
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я бот для управления расписанием гидов.\n"
        "Используй кнопки ниже для навигации.",
        reply_markup=kb
    )

@router.message(F.text == "🔙 Главное меню")
async def back_to_main(message: types.Message):
    await cmd_start(message)

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
