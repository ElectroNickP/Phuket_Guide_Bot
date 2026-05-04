import asyncio
from telethon import TelegramClient
from tests.e2e.config import API_ID, API_HASH, SESSION_NAME

async def main():
    print("This script will help you authorize your Telegram test account.")
    print("It will create the necessary .session file so pytest can run without interactive prompts.")
    
    # Telethon handles the prompts for Phone Number and Auth Code automatically
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    
    me = await client.get_me()
    print(f"\n✅ Authenticated successfully as '{me.first_name}' (@{me.username})")
    print(f"Session saved to '{SESSION_NAME}.session'")
    print("You can now run 'pytest tests/e2e/flows/ test_start.py' safely.")

if __name__ == "__main__":
    asyncio.run(main())
