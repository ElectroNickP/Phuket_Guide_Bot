from utils.time import get_phuket_now, get_phuket_today
import asyncio
from services.sea_plan import sea_plan_service
from services.google_sheets import google_sheets
from loguru import logger
from database.db import init_db
import datetime

async def main():
    await init_db()
    # Force query for the admin just to see the sheet struct
    plans = await sea_plan_service.get_guide_sea_plan("SF_Fedor", get_phuket_today())
    print("Fetched plans")

if __name__ == "__main__":
    asyncio.run(main())
