import os
from dotenv import load_dotenv

load_dotenv()

# Telethon credentials from my.telegram.org
API_ID = int(os.getenv("TELETHON_API_ID", "123456"))
API_HASH = os.getenv("TELETHON_API_HASH", "test_hash_xxx")

# Bots to test against
STAFF_BOT_USERNAME = os.getenv("STAFF_BOT_USERNAME", "@TEST_best_job_orders_land_bot")
TOURIST_BOT_USERNAME = os.getenv("TOURIST_BOT_USERNAME", "@BESTTour_v1_Bot")
BOT_USERNAME = STAFF_BOT_USERNAME # Default

# File to store telethon session
SESSION_NAME = "tests/e2e/test_session"

# Test configuration
TIMEOUT = 5
RETRIES = 3
