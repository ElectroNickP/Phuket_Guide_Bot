from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database.models import Base
from config import config
from loguru import logger
import os

engine = create_async_engine(config.DB_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

from sqlalchemy import update
async def update_user_activity(telegram_id: int, action: str = None, last_action: str = None):
    """Updates last_contact and increments specific action counter for a user."""
    try:
        from database.models import User
        from utils.time import get_phuket_now
        
        async with AsyncSessionLocal() as session:
            # Prepare updates
            update_data = {"last_contact": get_phuket_now()}
            if last_action:
                update_data["last_action"] = last_action[:100] # Truncate if too long
            
            if action == "start":
                update_data["count_start"] = User.count_start + 1
            elif action == "today":
                update_data["count_today"] = User.count_today + 1
            elif action == "tomorrow":
                update_data["count_tomorrow"] = User.count_tomorrow + 1
            elif action == "sea_today":
                update_data["count_sea_today"] = User.count_sea_today + 1
            elif action == "sea_tomorrow":
                update_data["count_sea_tomorrow"] = User.count_sea_tomorrow + 1
            elif action == "feedback":
                update_data["count_feedback"] = User.count_feedback + 1
            elif action == "status":
                update_data["count_status"] = User.count_status + 1
            elif action == "finish":
                update_data["count_finish"] = User.count_finish + 1
                
            q = update(User).where(User.telegram_id == telegram_id).values(**update_data)
            await session.execute(q)
            await session.commit()
            logger.debug(f"Updated activity for {telegram_id}: {action}")
    except Exception as e:
        logger.error(f"Error updating user activity for {telegram_id}: {e}")
