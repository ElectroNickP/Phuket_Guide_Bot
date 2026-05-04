import asyncio
from telethon import TelegramClient
from telethon.tl.patched import Message
from loguru import logger
from tests.e2e.config import API_ID, API_HASH, SESSION_NAME, BOT_USERNAME

class TestClient:
    def __init__(self):
        self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        self.bot_username = BOT_USERNAME

    async def connect(self):
        logger.info("Connecting to Telegram...")
        await self.client.start()
        logger.info("Connected successfully!")

    async def disconnect(self):
        await self.client.disconnect()

    async def send(self, text: str):
        logger.debug(f">> Sending: {text}")
        await self.client.send_message(self.bot_username, text)

    async def get_last_messages(self, limit=1) -> list[Message]:
        return await self.client.get_messages(self.bot_username, limit=limit)

    async def click(self, button_index: int):
        messages = await self.get_last_messages(1)
        if not messages:
            raise ValueError("No message to click.")
        msg = messages[0]
        
        # Click inline button by index (flatten rows into one list)
        if msg.buttons:
            all_buttons = [btn for row in msg.buttons for btn in row]
            if button_index < len(all_buttons):
                logger.debug(f">> Clicking button [{button_index}]: {all_buttons[button_index].text}")
                await all_buttons[button_index].click()
                return
            
        raise ValueError(f"Button index {button_index} not found on the last message. Available buttons: {msg.buttons}")

    async def clear_chat(self):
        # Clears chat history to start clean
        try:
            await self.client.delete_dialog(self.bot_username)
            logger.debug("Chat history cleared.")
        except Exception as e:
            logger.warning(f"Failed to clear chat: {e}")
