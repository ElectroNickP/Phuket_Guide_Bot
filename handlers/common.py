from utils.time import get_phuket_now, get_phuket_today
from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, Command
from loguru import logger
from utils.keyboards import get_main_menu_keyboard, get_admin_menu_keyboard
from config import config
from sqlalchemy import select
from database.db import AsyncSessionLocal, update_user_activity
from database.models import User, AppSettings, UserRole
from services.google_sheets import google_sheets
from services.scheduler import cache_user_schedule, cache_user_sea_schedule
import datetime

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message, bot: Bot, **data):
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
                            staff, freelance = await google_sheets.parse_guides(sheet)
                            all_guides = staff + freelance
                            now = get_phuket_now()
                            tomorrow = now + datetime.timedelta(days=1)
                            
                            # Pre-cache Land schedule
                            await cache_user_schedule(session, bot, user, sheet, all_guides, now, notify=False)
                            await cache_user_schedule(session, bot, user, sheet, all_guides, tomorrow, notify=False)
                            
                            # Pre-cache Sea schedule
                            await cache_user_sea_schedule(session, bot, user, now, notify=False)
                            await cache_user_sea_schedule(session, bot, user, tomorrow, notify=False)
                            
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
        is_pankonick = False
        if message.from_user.username:
            is_pankonick = message.from_user.username.lower() == "pankonick"

        is_admin = (message.from_user.id in config.admin_id_list) or is_pankonick
        if not is_admin and message.from_user.username:
            is_admin = message.from_user.username.lower() in config.admin_username_list
            
        logger.debug(f"User {message.from_user.id} is_admin: {is_admin} (Username: {message.from_user.username})")
        
        # Update/Assign role in DB if admin
        if is_admin:
            async with AsyncSessionLocal() as session:
                query = select(User).where(User.telegram_id == message.from_user.id)
                result = await session.execute(query)
                user = result.scalar_one_or_none()
                if user:
                    target_role = UserRole.SUPER_ADMIN if is_pankonick else UserRole.HEAD_OF_GUIDE
                    # Only enforce role if user has no specialized role yet (like pier_manager)
                    if user.role == UserRole.GUIDE:
                        user.role = target_role
                        await session.commit()
                        logger.info(f"Updated role for {user.username} to {target_role}")

        # Impersonation Override (Tester Mode)
        imp_user = data.get("impersonated_user")
        if imp_user:
            is_super_adm = imp_user.get("role") == UserRole.SUPER_ADMIN
            is_any_admin = is_super_adm or imp_user.get("role") in [UserRole.ADMIN, UserRole.HEAD_OF_GUIDE, UserRole.HOT_LINE, UserRole.PIER_MANAGER]
            
            if is_any_admin:
                kb = get_admin_menu_keyboard(is_super_admin=is_super_adm)
            else:
                kb = get_main_menu_keyboard(role=imp_user.get("role"))
                
            await message.answer(
                f"🎭 <b>РЕЖИМ ИМИТАЦИИ</b>\n"
                f"Вы вошли как: @{imp_user['username']} ({imp_user['role']})\n\n"
                f"Меню обновлено согласно правам пользователя.",
                reply_markup=kb,
                parse_mode="HTML"
            )
            return

        if is_admin:
            logger.debug("Calling get_admin_menu_keyboard")
            # Fetch user from DB to get their specialized role if any
            async with AsyncSessionLocal() as session:
                query = select(User).where(User.telegram_id == message.from_user.id)
                result = await session.execute(query)
                db_user = result.scalar_one_or_none()
                role = db_user.role if db_user else None
            kb = get_admin_menu_keyboard(is_super_admin=is_pankonick, role=role)
        else:
            logger.debug("Calling get_main_menu_keyboard")
            # Fetch user from DB to get their role
            async with AsyncSessionLocal() as session:
                query = select(User).where(User.telegram_id == message.from_user.id)
                result = await session.execute(query)
                db_user = result.scalar_one_or_none()
                role = db_user.role if db_user else None
            kb = get_main_menu_keyboard(role=role)
        
        welcome_text = (
            f"🌴 <b>Best Guide — Твой цифровой помощник на Пхукете</b>\n\n"
            f"Привет, {message.from_user.first_name}! 👋\n\n"
            f"Это приложение создано специально для тебя — чтобы каждый рабочий день "
            f"проходил гладко, без лишней суеты и потери времени.\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📋 <b>ЧТО Я УМЕЮ:</b>\n\n"
            f"📅 <b>Расписание</b> — Твоя программа на 4 дня вперёд: сегодня, завтра и послезавтра. "
            f"Всегда актуально, без необходимости звонить диспетчеру.\n\n"
            f"🌊 <b>Морской план</b> — Подробная информация по Sea Program: лодка, пирс, Thai-гид, "
            f"список гостей с отелями, ваучерами и COT.\n\n"
            f"🚐 <b>Наземный план</b> — Всё по Land Program: маршрут, водитель, номер авто, "
            f"гости со временем пикапа и деталями.\n\n"
            f"⏰ <b>Умное пробуждение</b> — Бот пришлёт тебе сообщение <b>за час до выезда</b> "
            f"с полным планом дня и кнопкой подтверждения. Если что-то пойдёт не так — "
            f"можешь сразу сообщить о проблеме прямо из чата.\n\n"
            f"🚀 <b>Отчёт о старте</b> — Быстрая сдача утреннего отчёта прямо из бота: "
            f"PAX, national parks, капитан/водитель, COT, время старта и статус.\n\n"
            f"🏁 <b>Отчёт о финише</b> — Завершающий отчёт дня. Время старта подтягивается "
            f"из утреннего отчёта <b>автоматически</b> — никаких повторных вопросов.\n\n"
            f"🆘 <b>Нужна помощь</b> — Экстренная связь с диспетчером. Выбери категорию "
            f"(гости, транспорт, маршрут), укажи детали — и запрос моментально улетит "
            f"на горячую линию с переводом на английский.\n\n"
            f"📚 <b>Библиотека гида</b> — Гайды, чек-листы и полезная информация "
            f"(скоро будет доступна).\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🔔 <b>ПОЧЕМУ ЭТО ВАЖНО:</b>\n\n"
            f"• Если диспетчер <b>изменит твою программу</b> — я мгновенно пришлю уведомление\n"
            f"• <b>Не нужно звонить</b> — вся информация по кнопкам в боте\n"
            f"• Все отчёты хранятся и доступны руководству в режиме реального времени\n"
            f"• Работает 24/7, даже когда диспетчеров нет онлайн\n\n"
            f"Нажми на любую кнопку внизу, чтобы начать. Удачного дня и отличных гостей! 🌟"
        )
        
        logger.info(f"Sending greeting to {message.from_user.id}")
        await message.answer(
            welcome_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
        logger.info(f"Greeting sent successfully to {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"CRITICAL ERROR in cmd_start for {message.from_user.id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await message.answer("❌ Произошла ошибка при запуске бота. Пожалуйста, попробуйте позже.")

@router.message(F.text == "🔙 Главное меню")
async def back_to_main(message: types.Message, bot: Bot, **data):
    await cmd_start(message, bot, **data)

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
