import asyncio
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.types import ErrorEvent
from config import config
from database.db import init_db
from handlers import common, guide, admin, feedback
from services.scheduler import setup_scheduler
from utils.logging_middleware import LoggingMiddleware
from loguru import logger

# ─── Logging Configuration ────────────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "logs/bot.log",
    rotation="10 MB",
    retention="30 days",
    compression="gz",       # Compress old logs
    level="DEBUG",          # Write DEBUG level to file for full trace
    enqueue=True,           # Thread-safe async-friendly logging
    backtrace=True,         # Full traceback on exceptions
    diagnose=True           # Variable values in tracebacks
)


# ─── Global Error Handler ─────────────────────────────────────────────────────
async def handle_error(event: ErrorEvent):
    """Catches all unhandled aiogram exceptions and logs them with full context."""
    update = event.update
    user_info = "unknown"
    if update.message:
        u = update.message.from_user
        user_info = f"@{u.username or u.id}"
    elif update.callback_query:
        u = update.callback_query.from_user
        user_info = f"@{u.username or u.id}"

    logger.exception(
        f"Unhandled exception | user={user_info} | update_id={update.update_id} | {event.exception}"
    )


async def main():
    # Initialize Database
    await init_db()

    # Initialize Bot & Dispatcher
    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()

    # ─── Startup Diagnostics ──────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("🤖 Bot starting up...")
    logger.info(f"   Admin IDs     : {config.admin_id_list}")
    logger.info(f"   Spreadsheet   : {config.DEFAULT_SPREADSHEET_ID}")
    logger.info(f"   Sea Plan Sheet: {config.DEFAULT_SEA_SPREADSHEET_ID}")
    logger.info(f"   DB            : {config.DB_URL}")
    logger.info(f"   Poll interval : {config.POLLING_INTERVAL}s")
    logger.info("=" * 60)

    # Setup Scheduler
    await setup_scheduler(bot)

    # ─── Register Global Error Handler ───────────────────────────────────────
    dp.errors.register(handle_error)

    # ─── Register Middleware (applies to all routers) ─────────────────────────
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())

    # ─── Register Routers ─────────────────────────────────────────────────────
    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(feedback.router)
    dp.include_router(guide.router)

    # Start Polling
    logger.info("Bot started and polling...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.exception(f"Fatal error in polling: {e}")
    finally:
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
