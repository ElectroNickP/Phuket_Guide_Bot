import asyncio
import os
import sys
from dotenv import load_dotenv
load_dotenv()
from telethon import TelegramClient, events
from telethon.tl.types import ReplyKeyboardMarkup, KeyboardButtonRow, KeyboardButton

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

# Mock env for Settings validation
os.environ.setdefault('BOT_TOKEN', '123:abc')
os.environ.setdefault('ADMIN_ID', '123')
from config import config

async def test_dual_bots():
    # Load env for testing tokens
    # Note: TELETHON_BOT_USERNAME might be @BESTTour_v1_Bot (Tourist)
    # the staff bot is @TEST_best_job_orders_land_bot
    
    api_id = int(os.environ.get('TELETHON_API_ID'))
    api_hash = os.environ.get('TELETHON_API_HASH')
    
    # Session name
    session_name = '/tmp/telethon_dual_test'
    
    async with TelegramClient(session_name, api_id, api_hash) as client:
        # 1. Test Staff Bot
        staff_bot = "@TEST_best_job_orders_land_bot"
        print(f"Testing Staff Bot: {staff_bot}")
        await client.send_message(staff_bot, "/start")
        await asyncio.sleep(2)
        
        history = await client.get_messages(staff_bot, limit=1)
        msg = history[0]
        print(f"Staff Bot Response: {msg.text[:50]}...")
        
        # Check for staff-only buttons
        has_schedule = any("Расписание" in b.text for row in (msg.reply_markup.rows if msg.reply_markup else []) for b in row.buttons)
        print(f"Has Schedule button: {has_schedule}")
        
        # 2. Test Tourist Bot
        tourist_bot = "@BESTTour_v1_Bot"
        print(f"Testing Tourist Bot: {tourist_bot}")
        await client.send_message(tourist_bot, "/start")
        await asyncio.sleep(2)
        
        history_t = await client.get_messages(tourist_bot, limit=1)
        msg_t = history_t[0]
        print(f"Tourist Bot Response: {msg_t.text[:50]}...")
        
        # Check for tourist-only buttons and LACK of staff buttons
        has_shop = any("Заказать онлайн" in b.text for row in (msg_t.reply_markup.rows if msg_t.reply_markup else []) for b in row.buttons)
        not_has_schedule = not any("Расписание" in b.text for row in (msg_t.reply_markup.rows if msg_t.reply_markup else []) for b in row.buttons)
        
        print(f"Has Shop button: {has_shop}")
        print(f"Lacks Schedule button: {not_has_schedule}")
        
        if has_schedule and has_shop and not_has_schedule:
            print("\n✅ DUAL BOT VERIFICATION SUCCESSFUL!")
        else:
            print("\n❌ DUAL BOT VERIFICATION FAILED!")
            if not has_schedule: print("- Staff bot missing schedule button")
            if not has_shop: print("- Tourist bot missing shop button")
            if not not_has_schedule: print("- Tourist bot has staff buttons (Lockdown failed)")

if __name__ == "__main__":
    asyncio.run(test_dual_bots())
