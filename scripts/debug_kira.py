import asyncio
import datetime
from services.sea_plan import sea_plan_service

async def debug_kira():
    target_date = datetime.date(2026, 3, 22)
    username = 'kk_kira69'
    print(f"Checking land plan for @{username} on {target_date}")
    
    plans = await sea_plan_service.get_guide_land_plan(username, target_date)
    print(f"Found {len(plans)} plans")
    for i, plan in enumerate(plans):
        print(f"Plan {i+1}: {plan.program}")
        for g in plan.guides:
            if g.is_me:
                print(f"  Guide Info: {g.full_info}")
                print(f"  Pickup Time: '{g.pickup_time}'")
                print(f"  Pickup Location: {g.pickup_location}")

if __name__ == '__main__':
    asyncio.run(debug_kira())
