import asyncio
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from tests.e2e.runner import run_flow
from tests.e2e.flows.audit_flows import TOURIST_SHOP_FLOW, STAFF_DASHBOARD_FLOW
from loguru import logger

async def main():
    logger.info("🚀 Starting Phuket Buddy E2E Verification Suite...")
    
    try:
        # 1. Run Tourist Bot Audit
        logger.info("--- 🏝 Auditing Tourist Bot Persona ---")
        await run_flow(TOURIST_SHOP_FLOW)
        logger.info("✅ Tourist Bot Audit: SUCCESS")
        
        # 2. Run Staff Bot Audit
        logger.info("--- ⚓️ Auditing Staff Bot Persona ---")
        await run_flow(STAFF_DASHBOARD_FLOW)
        logger.info("✅ Staff Bot Audit: SUCCESS")
        
        logger.info("✨ ALL AUDITS PASSED!")
        
    except Exception as e:
        logger.error(f"❌ AUDIT FAILED: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
