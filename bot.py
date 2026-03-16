import asyncio
import sys
from typing import Any
from aiogram import Bot, Dispatcher, types
from aiogram.types import ErrorEvent
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.methods import SendMessage, EditMessageText, SendPhoto, SendDocument, SendVideo, SendAudio, SendVoice, SendVenue, SendLocation
from aiogram.methods.base import TelegramMethod
from config import config
from database.db import init_db
from handlers import common, guide, admin, feedback, reports
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


class MonitoringBot(Bot):
    """
    Custom Bot subclass that duplicates outgoing messages to the log channel.
    Only duplicates messages sent to guides (skips admins).
    """
    # map chat_id -> string (username or full name)
    user_info_cache: dict[int, str] = {}

    async def __call__(self, method: TelegramMethod, request_timeout: int | None = None) -> Any:
        # Execute the original method first
        result = await super().__call__(method, request_timeout)

        # Skip if monitoring is disabled or no log channel set
        if not config.ACTION_LOG_ENABLED or not config.ACTION_LOG_CHANNEL_ID:
            return result

        # Define methods to duplicate
        trackable_methods = (
            SendMessage, EditMessageText, SendPhoto, SendDocument, 
            SendVideo, SendAudio, SendVoice, SendVenue, SendLocation
        )

        if isinstance(method, trackable_methods):
            chat_id = getattr(method, 'chat_id', None)
            
            # Skip if destination is the log channel itself (to avoid infinite loop)
            if chat_id == config.ACTION_LOG_CHANNEL_ID:
                return result
                
            # Skip if destination is an admin
            if chat_id in config.admin_id_list:
                return result

            try:
                # Resolve chat_id to name from cache
                destination_name = self.user_info_cache.get(chat_id, str(chat_id))
                
                # Prepare log text
                text_content = ""
                if hasattr(method, 'text'): text_content = method.text
                elif hasattr(method, 'caption'): text_content = method.caption
                
                method_name = method.__class__.__name__
                
                # We use a separate background task to avoid slowing down the main response
                asyncio.create_task(self.send_message(
                    chat_id=config.ACTION_LOG_CHANNEL_ID,
                    text=f"🤖 <b>Bot Response</b>\n➡️ to: <b>{destination_name}</b>\n📝 type: <code>{method_name}</code>\n\n{text_content[:500]}",
                    parse_mode="HTML"
                ))
            except Exception as e:
                logger.error(f"Error duplicating outgoing message to log: {e}")

        return result


async def main():
    # Initialize Database
    await init_db()

    # Initialize Bot & Dispatcher
    bot = MonitoringBot(token=config.BOT_TOKEN.get_secret_value())
    storage = RedisStorage.from_url(config.REDIS_URL)
    dp = Dispatcher(storage=storage)

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
    dp.message.outer_middleware(LoggingMiddleware())
    dp.callback_query.outer_middleware(LoggingMiddleware())

    # ─── Register Routers ─────────────────────────────────────────────────────
    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(feedback.router)
    dp.include_router(guide.router)
    dp.include_router(reports.router)

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
