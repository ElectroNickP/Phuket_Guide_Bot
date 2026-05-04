import os
from dotenv import load_dotenv

load_dotenv()

# Telethon credentials from my.telegram.org
API_ID = int(os.getenv("TELETHON_API_ID", "123456"))
API_HASH = os.getenv("TELETHON_API_HASH", "test_hash_xxx")

# Bot to test against
BOT_USERNAME = os.getenv("TELETHON_BOT_USERNAME", "@your_bot_username")

# File to store telethon session
SESSION_NAME = "tests/e2e/test_session"

# Test configuration
TIMEOUT = 5
RETRIES = 3
