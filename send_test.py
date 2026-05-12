import asyncio
import os
from aiogram import Bot

async def main():
    token = os.getenv('BOT_TOKEN')
    bot = Bot(token=token)
    chat_id = -1003556020066
    thread_id = 569
    
    print(f"Trying to send to {chat_id} (no thread)...")
    try:
        await bot.send_message(chat_id=chat_id, text="🚀 Test message (Main Chat)")
        print("✅ Success (Main Chat)")
    except Exception as e:
        print(f"❌ Failed (Main Chat): {e}")

    print(f"Trying to send to {chat_id} (Thread {thread_id})...")
    try:
        await bot.send_message(chat_id=chat_id, message_thread_id=thread_id, text="🚀 Test message (Topic)")
        print("✅ Success (Topic)")
    except Exception as e:
        print(f"❌ Failed (Topic): {e}")
        
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
