from utils.time import get_phuket_now, get_phuket_today
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.google_sheets import google_sheets
from database.db import AsyncSessionLocal
from database.models import User, ScheduleCache, AppSettings
from sqlalchemy import select, update
from aiogram import Bot
from loguru import logger
import datetime
from config import config
from services.sea_plan import sea_plan_service

scheduler = AsyncIOScheduler()

async def cache_user_schedule(session, bot: Bot, user: User, sheet, all_guides_sheet, target_date: datetime.datetime, notify: bool = True):
    """Caches schedule for a specific user and date, optionally notifying on change."""
    day = target_date.day
    guide_info = next((g for g in all_guides_sheet if g['username'].lower() == user.username.lower()), None)
    if not guide_info:
        return

    # Get current value from sheet
    current_program = await google_sheets.get_guide_schedule(sheet, guide_info['row'], day=day) or "---"
    
    # Check last cached value
    date_normalized = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    cache_query = select(ScheduleCache).where(
        ScheduleCache.guide_username == user.username,
        ScheduleCache.date == date_normalized
    )
    cache_result = await session.execute(cache_query)
    cache_entry = cache_result.scalar_one_or_none()
    
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
            cache_entry.last_updated = datetime.datetime.utcnow()
            
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
    cache_entry = cache_result.scalar_one_or_none()
    
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
            cache_entry.last_updated = datetime.datetime.utcnow()
            
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
        setting = result.scalar_one_or_none()
        interval = int(setting.value) if setting else config.POLLING_INTERVAL

    scheduler.add_job(
        check_schedule_changes, 
        "interval", 
        seconds=interval, 
        args=[bot], 
        id='check_schedule_job'
    )
    scheduler.start()
    logger.info(f"Scheduler started with interval: {interval} seconds")
