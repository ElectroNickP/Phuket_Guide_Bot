import asyncio
import datetime
import sys
import os
from loguru import logger

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.sea_plan import sea_plan_service
from database.dto import GuestDTO, SeaPlanDTO, LandPlanDTO

async def audit():
    today = datetime.date.today()
    # Audit for the next 7 days
    dates_to_test = [today + datetime.timedelta(days=i) for i in range(7)]
    
    logger.info(f"🚀 Starting Quality Assurance Audit for {len(dates_to_test)} days...")
    
    anomalies = []
    
    for date in dates_to_test:
        date_str = date.strftime("%d.%m")
        # logger.info(f"--- Auditing {date_str} ---")
        
        # 1. Audit Sea Plans
        try:
            sea_guides = await sea_plan_service.get_active_sea_guides([date])
            processed_boats = set()
            
            for guide in sea_guides:
                plans = await sea_plan_service.get_guide_sea_plan(guide, date)
                for plan in plans:
                    boat_key = f"{date_str}_{plan.pier}_{plan.boat}"
                    if boat_key in processed_boats:
                        continue
                    processed_boats.add(boat_key)
                    
                    # Anomaly: Missing important info
                    if not plan.boat:
                        anomalies.append(f"❌ [SEA] [{date_str}] Boat name is missing!")
                    if not plan.programs:
                        anomalies.append(f"❌ [SEA] [{date_str}] Boat '{plan.boat}' has no programs listed.")
                    
                    # Anomaly: Pax logic
                    for prog in plan.programs:
                        try:
                            pax_count = int(prog.pax)
                            if pax_count > 35:
                                anomalies.append(f"⚠️ [SEA] [{date_str}] '{plan.boat}' -> '{prog.name}' has unusually high pax: {pax_count}")
                        except ValueError:
                            pass # Not a simple number, maybe a range
                        
                    # Anomaly: Guest List validation
                    guest_list = await sea_plan_service.get_guest_list(date, [p.name for p in plan.programs])
                    if not guest_list:
                         anomalies.append(f"⚠️ [SEA] [{date_str}] Boat '{plan.boat}' has programs but NO guests found in the guest list section.")
        except Exception as e:
            logger.error(f"Error auditing SEA for {date_str}: {e}")

        # 2. Audit Land Plans
        try:
            land_guides = await sea_plan_service.get_active_land_guides([date])
            processed_land_progs = set()
            
            for guide in land_guides:
                plans = await sea_plan_service.get_guide_land_plan(guide, date)
                for plan in plans:
                    prog_key = f"{date_str}_{plan.program}"
                    if prog_key in processed_land_progs:
                        continue
                    processed_land_progs.add(prog_key)
                    
                    # Anomaly: Missing Bus/Driver
                    if not plan.bus:
                         anomalies.append(f"⚠️ [LAND] [{date_str}] Program '{plan.program}' is missing Bus assignment.")
                    if not plan.driver:
                         anomalies.append(f"⚠️ [LAND] [{date_str}] Program '{plan.program}' is missing Driver assignment.")
                    
                    # Anomaly: High Guest count
                    guest_count = len(plan.guests)
                    if guest_count > 25:
                         anomalies.append(f"⚠️ [LAND] [{date_str}] Program '{plan.program}' (Bus: {plan.bus}) has {guest_count} guests. Check if programs merged!")
                    
                    if guest_count == 0:
                         anomalies.append(f"❌ [LAND] [{date_str}] Program '{plan.program}' has NO guests.")
                         
                    # Anomaly: Guides per bus
                    if len(plan.guides) > 3:
                         anomalies.append(f"⚠️ [LAND] [{date_str}] '{plan.program}' has {len(plan.guides)} guides. Is this a combined block?")
        except Exception as e:
            logger.error(f"Error auditing LAND for {date_str}: {e}")

    print("\n" + "="*50)
    print(f"📊 AUDIT REPORT ({today.strftime('%Y-%m-%d %H:%M')})")
    print("="*50)
    
    if not anomalies:
        print("✅ No major anomalies detected. The system parsing looks stable.")
    else:
        print(f"🚨 Detected {len(anomalies)} potential issues:")
        for a in anomalies:
            print(f"  • {a}")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(audit())
