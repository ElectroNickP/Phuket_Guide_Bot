import asyncio
import os
from aiogram import Bot

async def main():
    token = os.getenv('BOT_TOKEN')
    if not token:
        print("No token found")
        return
        
    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        print(f"Bot: @{me.username} (ID: {me.id})")
        
        updates = await bot.get_updates(offset=-1) # Get only the latest
        if not updates:
            print("No updates found. Please send a message in the group.")
            return
            
        for u in updates:
            msg = u.message or u.edited_message or (u.callback_query.message if u.callback_query else None)
            if msg:
                print(f"Chat: '{msg.chat.title}' (ID: {msg.chat.id}), Thread: {msg.message_thread_id}, Text: {getattr(msg, 'text', 'N/A')}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
