import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from config import config
from database.db import init_db
from handlers import common, guide, admin, feedback
from services.scheduler import setup_scheduler
from loguru import logger
import sys

# Configure Loguru
logger.remove()
logger.add(sys.stderr, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
logger.add("logs/bot.log", rotation="10 MB", retention="10 days", level="INFO")

async def main():
    # Initialize Database
    await init_db()
    
    # Initialize Bot & Dispatcher
    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()

    # Setup Scheduler
    await setup_scheduler(bot)

    # Register Routers
    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(feedback.router)
    dp.include_router(guide.router)

    # Start Polling
    logger.info("Bot started and polling...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
