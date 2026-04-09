import asyncio
import datetime
from services.sea_plan import sea_plan_service
from services.scheduler import check_guide_wakeups
from database.db import AsyncSessionLocal
from sqlalchemy import select
from database.models import User
from aiogram import Bot
from config import config

async def debug_land_plan():
    target_date = datetime.date(2026, 3, 22)
    print(f"Checking land plan for {target_date}")
    
    # 1. Get active land guides
    guides = await sea_plan_service.get_active_land_guides([target_date])
    print(f"Active land guides: {guides}")
    
    for username in guides:
        print(f"\n--- Checking guide: @{username} ---")
        plans = await sea_plan_service.get_guide_land_plan(username, target_date)
        print(f"Found {len(plans)} plans")
        for i, plan in enumerate(plans):
            print(f"Plan {i+1}: {plan.program}")
            for g in plan.guides:
                if g.is_me:
                    print(f"  Guide Info: {g.full_info}")
                    print(f"  Pickup Time: '{g.pickup_time}'")
                    print(f"  Pickup Location: {g.pickup_location}")

async def main():
    await debug_land_plan()

if __name__ == '__main__':
    asyncio.run(main())
