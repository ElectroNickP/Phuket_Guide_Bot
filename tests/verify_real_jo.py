import asyncio
import os
import sys
import datetime
from loguru import logger

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.getcwd()))

from services.sea_plan import sea_plan_service
from services.image_generator import job_order_generator
from utils.time import get_phuket_now

async def verify_real_data():
    logger.info("Starting real-data verification...")
    
    # Target: LV_Viacheslav on 14.03 (he had work then)
    target_uname = "LV_Viacheslav"
    target_date = datetime.date(2026, 3, 14)
    
    logger.info(f"Fetching Sea Plan for @{target_uname} on {target_date}...")
    sea_plans = await sea_plan_service.get_guide_sea_plan(target_uname, target_date)
    
    if not sea_plans:
        logger.error(f"No sea plan found for {target_uname} on {target_date}!")
        return

    plan = sea_plans[0]
    logger.info(f"Found plan: Boat={plan.boat}, Programs={[p.name for p in plan.programs]}")
    
    # Fetch guests
    prog_names = [p.name for p in plan.programs]
    logger.info(f"Fetching guests for programs: {prog_names}")
    guests = await sea_plan_service.get_guest_list(target_date, prog_names)
    
    logger.info(f"Found {len(guests)} guests.")
    
    # Generate image
    logger.info("Generating Job Order image...")
    photo_bytes = job_order_generator.generate_sea_job_order(plan, guests)
    
    output_path = "real_verification_jo.png"
    with open(output_path, "wb") as f:
        f.write(photo_bytes.getvalue())
        
    logger.info(f"✅ Real-data Job Order generated: {output_path}")
    logger.info(f"Image size: {os.path.getsize(output_path)} bytes")

if __name__ == "__main__":
    asyncio.run(verify_real_data())
