from utils.time import get_phuket_now, get_phuket_today
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.google_sheets import google_sheets
from database.db import AsyncSessionLocal
from database.models import User, ScheduleCache, AppSettings
from sqlalchemy import select, update, func
from aiogram import Bot
from loguru import logger
import datetime
from config import config
from services.sea_plan import sea_plan_service
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models import WakeUpConfirmation

def get_wakeup_message_data(username: str, p_time_str: str, program_name: str, pickup_location: str):
    """Generates text and keyboard for wake-up message."""
    from aiogram.types import WebAppInfo
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Проснулся / Готов", callback_data=f"wakeup_ok_{p_time_str}_{username}")
    kb.button(text="🆘 Есть проблема!", callback_data=f"wakeup_problem_{p_time_str}_{username}")
    kb.button(text="📱 Открыть Mini App", web_app=WebAppInfo(url=config.WEBAPP_URL))
    kb.adjust(1)
    
    text = (
        f"🚐 <b>Доброе утро! Пора в новый день ☀️</b>\n\n"
        f"Твоя программа: <b>{program_name}</b>\n"
        f"📍 Место сбора: {pickup_location}\n"
        f"⏰ Пикап: <b>{p_time_str}</b>\n\n"
        f"Пожалуйста, подтверди готовность, нажав кнопку ниже 👇"
    )
    return text, kb.as_markup()

scheduler = AsyncIOScheduler()

async def cache_user_schedule(session, bot: Bot, user: User, sheet, all_guides_sheet, target_date: datetime.datetime, notify: bool = True):
    """Caches schedule for a specific user and date, optionally notifying on change."""
    day = target_date.day
    guide_info = next((g for g in all_guides_sheet if g['username'].lower() == user.username.lower()), None)
    if not guide_info:
        return

    # Get current value from sheet
    current_program = await google_sheets.get_guide_schedule(sheet, guide_info['row'], target_date=target_date.date()) or "---"
    
    # Check last cached value
    date_normalized = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    cache_query = select(ScheduleCache).where(
        ScheduleCache.guide_username == user.username,
        ScheduleCache.date == date_normalized
    )
    cache_result = await session.execute(cache_query)
    cache_entry = cache_result.scalars().first()
    
    if not cache_entry:
        # First time seeing this date for this user, just cache it
        new_cache = ScheduleCache(
            guide_username=user.username,
            date=date_normalized,
            program_name=current_program
        )
        session.add(new_cache)
        logger.info(f"Initial cache for @{user.username} on {day}: {current_program}")
    else:
        # Compare
        if cache_entry.program_name != current_program:
            old_program = cache_entry.program_name
            cache_entry.program_name = current_program
            cache_entry.last_updated = get_phuket_now()
            
            if notify:
                date_label = "сегодня" if target_date.date() == get_phuket_now().date() else "завтра"
                try:
                    await bot.send_message(
                        user.telegram_id,
                        f"⚠️ <b>Вниманию гида!</b>\n\n"
                        f"Твое расписание на {date_label} ({day}) изменилось:\n"
                        f"<s>{old_program}</s> ➡️ <b>{current_program}</b>",
                        parse_mode="HTML"
                    )
                    logger.info(f"Notification sent to @{user.username} about {date_label} change.")
                except Exception as e:
                    logger.error(f"Failed to send notification to @{user.username}: {e}")

async def cache_user_sea_schedule(session, bot: Bot, user: User, target_date: datetime.datetime, notify: bool = True):
    """Caches sea schedule for a specific user and date, notifying on change."""
    day_str = target_date.strftime("%d.%m")
    
    # Fetch sea plan
    plans = await sea_plan_service.get_guide_sea_plan(user.username, target_date.date())
    
    if not plans:
        current_program = "---"
    else:
        # Serialize the plan into a comparable string
        plan_strs = []
        for p in plans:
            boat = p.boat
            progs = ", ".join([f"{prog.name} ({prog.pax}pax)" for prog in p.programs])
            plan_strs.append(f"🚢 {boat}: {progs}")
        current_program = "\n".join(plan_strs)
        
    date_normalized = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    sea_cache_key = f"sea_{user.username}"
    
    cache_query = select(ScheduleCache).where(
        ScheduleCache.guide_username == sea_cache_key,
        ScheduleCache.date == date_normalized
    )
    cache_result = await session.execute(cache_query)
    cache_entry = cache_result.scalars().first()
    
    if not cache_entry:
        new_cache = ScheduleCache(
            guide_username=sea_cache_key,
            date=date_normalized,
            program_name=current_program
        )
        session.add(new_cache)
        logger.info(f"Initial sea cache for @{user.username} on {day_str}: {current_program}")
    else:
        if cache_entry.program_name != current_program:
            old_program = cache_entry.program_name
            cache_entry.program_name = current_program
            cache_entry.last_updated = get_phuket_now()
            
            if notify and current_program != "---":
                date_label = "сегодня" if target_date.date() == get_phuket_now().date() else "завтра"
                try:
                    old_text = f"<s>{old_program}</s> ➡️\n" if old_program != "---" else ""
                    await bot.send_message(
                        user.telegram_id,
                        f"🌊 <b>Вниманию гида (МОРЕ)!</b>\n\n"
                        f"Твой морской план на {date_label} ({day_str}) изменился:\n"
                        f"{old_text}<b>{current_program}</b>",
                        parse_mode="HTML"
                    )
                    logger.info(f"Sea notification sent to @{user.username} about {date_label} change.")
                except Exception as e:
                    logger.error(f"Failed to send sea notification to @{user.username}: {e}")

async def check_guide_wakeups(bot: Bot):
    """
    Checks if guides need to be woken up (1 hour before land program pickup).
    Initially for Land Programs only.
    """
    now = get_phuket_now()
    today_date = now.date()
    
    logger.debug(f"Running wake-up check at {now.strftime('%H:%M:%S')}")
    unregistered_guides = set()
    
    async with AsyncSessionLocal() as session:
        # 1. Fetch all guides active on land today
        land_guides = await sea_plan_service.get_active_land_guides([today_date])
        
        for username in land_guides:
            # 2. Get their specific plan to find pickup time
            plans = await sea_plan_service.get_guide_land_plan(username, today_date)
            for plan in plans:
                # Find current guide's pickup info in this plan
                guide_info = next((g for g in plan.guides if g.is_me), None)
                if not guide_info or not guide_info.pickup_time:
                    continue
                
                # Parse pickup time (expected "HH:MM")
                try:
                    p_time_str = guide_info.pickup_time.strip()
                    h, m = map(int, p_time_str.split(':'))
                    pickup_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                except Exception:
                    logger.warning(f"Could not parse pickup time '{guide_info.pickup_time}' for @{username}")
                    continue
                
                # Wake-up time is 1 hour before pickup
                wake_up_dt = pickup_dt - datetime.timedelta(hours=1)
                
                # If current time is past wake_up time (but not too far, say within 30 min window)
                is_in_window = wake_up_dt <= now <= wake_up_dt + datetime.timedelta(minutes=30)
                logger.debug(f"Guide @{username}: pickup {p_time_str}, wake-up {wake_up_dt.strftime('%H:%M')}, sync window: {is_in_window}")
                
                if is_in_window:
                    # 3. Check if already notified
                    date_norm = datetime.datetime.combine(today_date, datetime.time.min)
                    q = select(WakeUpConfirmation).where(
                        WakeUpConfirmation.guide_username == username,
                        WakeUpConfirmation.date == date_norm,
                        WakeUpConfirmation.pickup_time == p_time_str
                    )
                    res = await session.execute(q)
                    conf = res.scalars().first()
                    
                    if not conf:
                        # 4. Send Notification
                        text, reply_markup = get_wakeup_message_data(username, p_time_str, plan.program, guide_info.pickup_location)
                        
                        # Find user telegram_id - Use case-insensitive search
                        user_q = select(User).where(func.lower(User.username) == username.lower())
                        user_res = await session.execute(user_q)
                        user_obj = user_res.scalars().first()
                        
                        if user_obj:
                            try:
                                await bot.send_message(
                                    user_obj.telegram_id,
                                    text,
                                    parse_mode="HTML",
                                    reply_markup=reply_markup
                                )
                                # Log record
                                new_conf = WakeUpConfirmation(
                                    guide_username=username,
                                    date=date_norm,
                                    pickup_time=p_time_str,
                                    program_name=plan.program,
                                    status="pending",
                                    sent_at=now
                                )
                                session.add(new_conf)
                                logger.info(f"Wake-up notification sent to @{username} for {p_time_str}")
                            except Exception as e:
                                logger.error(f"Failed to send wake-up to @{username}: {e}")
                        else:
                            logger.warning(f"Guide @{username} found in land plan but NOT registered in bot! (No telegram_id)")
                            unregistered_guides.add(username)
                
        # 5. Check for "No Response" escalations
        # Any pending confirmation sent > 15 mins ago
        pending_q = select(WakeUpConfirmation).where(
            WakeUpConfirmation.status == "pending",
            WakeUpConfirmation.sent_at <= now - datetime.timedelta(minutes=15)
        )
        pending_res = await session.execute(pending_q)
        to_escalate = pending_res.scalars().all()
        
        for item in to_escalate:
            item.status = "no_response"
            logger.warning(f"NO RESPONSE from @{item.guide_username} for wake-up at {item.pickup_time}")
            # Notify Hotline/Admin
            try:
                msg = (
                    f"‼️ <b>НЕТ ОТВЕТА ОТ ГИДА!</b>\n\n"
                    f"Программа: <b>{item.program_name or '---'}</b>\n"
                    f"Гид: @{item.guide_username}\n"
                    f"Пикап: {item.pickup_time}\n"
                    f"Статус: Не подтвердил готовность в течение 15 минут!"
                )
                # Send to admin_id_list or a specific channel if defined
                # For now, let's send to the first admin in list as a placeholder or a dedicated log channel
                await bot.send_message(config.REPORT_GROUP_ID, msg, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to escalate no-response for @{item.guide_username}: {e}")
                
        await session.commit()
        
        # 6. Notify about unregistered guides
        if unregistered_guides:
            try:
                # To avoid spamming, we only notify if it's "early morning" or something
                # But for now, let's just send it if it's the first check of the hour
                if now.minute < 5: 
                    usernames_str = ", ".join([f"@{u}" for u in sorted(list(unregistered_guides))])
                    alert_msg = (
                        f"⚠️ <b>ГИДЫ НЕ В БОТЕ!</b>\n\n"
                        f"Эти гиды есть в расписании (LAND), но не запустили бота:\n"
                        f"<b>{usernames_str}</b>\n\n"
                        f"Они не получат уведомление о пробуждении!"
                    )
                    await bot.send_message(config.REPORT_GROUP_ID, alert_msg, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to send unregistered guides alert: {e}")

async def check_schedule_changes(bot: Bot):
    """
    Checks for schedule changes for all registered guides for today and tomorrow.
    """
    logger.info("Checking schedule changes...")
    
    async with AsyncSessionLocal() as session:
        query = select(User).where(User.username.isnot(None))
        result = await session.execute(query)
        users = result.scalars().all()
        
        sheet = await google_sheets.get_current_month_sheet()
        if not sheet:
            logger.warning("Could not find sheet for change check.")
            return

        staff, freelance = await google_sheets.parse_guides(sheet)
        all_guides_sheet = staff + freelance
        
        today = get_phuket_now()
        tomorrow = today + datetime.timedelta(days=1)
        
        for user in users:
            # Check Land Today & Tomorrow
            await cache_user_schedule(session, bot, user, sheet, all_guides_sheet, today)
            await cache_user_schedule(session, bot, user, sheet, all_guides_sheet, tomorrow)
            
            # Check Sea Today & Tomorrow
            await cache_user_sea_schedule(session, bot, user, today)
            await cache_user_sea_schedule(session, bot, user, tomorrow)
        
        await session.commit()

async def update_scheduler_interval(bot: Bot, new_seconds: int):
    """Dynamically updates the scheduler interval."""
    # Remove existing job if it exists
    try:
        scheduler.remove_job('check_schedule_job')
    except:
        pass
        
    # Add new job with new interval
    scheduler.add_job(
        check_schedule_changes, 
        "interval", 
        seconds=new_seconds, 
        args=[bot], 
        id='check_schedule_job'
    )
    logger.info(f"Scheduler interval updated to {new_seconds} seconds")

async def setup_scheduler(bot: Bot):
    # Get interval from DB or config
    async with AsyncSessionLocal() as session:
        query = select(AppSettings).where(AppSettings.key == "polling_interval")
        result = await session.execute(query)
        setting = result.scalars().first()
        interval = int(setting.value) if setting else config.POLLING_INTERVAL

    scheduler.add_job(
        check_schedule_changes, 
        "interval", 
        seconds=interval, 
        args=[bot], 
        id='check_schedule_job'
    )
    
    # Wake-up check every 2 minutes
    scheduler.add_job(
        check_guide_wakeups,
        "interval",
        minutes=2,
        args=[bot],
        id='check_wakeups_job'
    )
    scheduler.start()
    logger.info(f"Scheduler started with interval: {interval} seconds")
