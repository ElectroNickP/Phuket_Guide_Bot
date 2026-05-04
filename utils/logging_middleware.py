import time
import asyncio
import json
from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from loguru import logger
from config import config

class LoggingMiddleware(BaseMiddleware):
    """
    Middleware that logs incoming events and updates user activity.
    Uses background tasks to ensure no blocking calls affect bot responsiveness.
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any]
    ) -> Any:
        start_time = time.monotonic()
        user = event.from_user
        user_info = f"@{user.username}" if user.username else f"id:{user.id}"

        # 1. Impersonation Check (Async but fast if Cache-based)
        # We'll do this in-line because it modifies 'data' for the handler
        state = data.get("state")
        if state and hasattr(state, "storage") and hasattr(state.storage, "redis"):
            try:
                imp_key = f"impersonation:{user.id}"
                imp_data = await state.storage.redis.get(imp_key)
                if imp_data:
                    impersonated_user = json.loads(imp_data)
                    data["impersonated_user"] = impersonated_user
                    user_info += f" (as @{impersonated_user['username']})"
            except Exception as e:
                logger.error(f"Impersonation check error: {e}")

        # 2. Local Logging (Immediate)
        if isinstance(event, Message):
            content = event.text or f"[{event.content_type}]"
            logger.info(f"MSG  | {user_info} | {content[:80]}")
        elif isinstance(event, CallbackQuery):
            logger.info(f"CBQ  | {user_info} | data={event.data}")

        # 3. Background Tasks (Non-blocking)
        asyncio.create_task(self._process_background_tasks(event, user_info, data))

        # 4. Execute Handler
        try:
            result = await handler(event, data)
            elapsed = (time.monotonic() - start_time) * 1000
            logger.debug(f"DONE | {user_info} | {elapsed:.0f}ms")
            return result
        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            logger.exception(f"ERR  | {user_info} | {elapsed:.0f}ms | {e}")
            raise

    async def _process_background_tasks(self, event: Message | CallbackQuery, user_info: str, data: dict[str, Any]):
        """
        Gathers all slow/external calls into one background execution.
        """
        user = event.from_user
        bot = data.get("bot")

        # Update user cache (internal dict, very fast)
        if bot and hasattr(bot, 'user_info_cache'):
            name_val = f"@{user.username}" if user.username else user.full_name
            bot.user_info_cache[user.id] = name_val

        # Update DB Activity
        try:
            from database.db import update_user_activity
            raw_action = event.text if isinstance(event, Message) else f"CB:{event.data}"
            await update_user_activity(user.id, last_action=raw_action)
        except Exception as e:
            logger.error(f"BG: Activity update error: {e}")

        # Send to Log Channel (External Network)
        is_admin = user.id in config.admin_id_list or user.username in config.admin_username_list
        if config.ACTION_LOG_ENABLED and not is_admin:
            try:
                log_text = None
                if isinstance(event, Message):
                    content = event.text or f"[{event.content_type}]"
                    log_text = f"👤 <b>{user_info}</b>\n➡️ action: <code>{content[:200]}</code>"
                elif isinstance(event, CallbackQuery):
                    log_text = f"👤 <b>{user_info}</b>\n🔘 button: <code>{event.data}</code>"
                
                if log_text and bot:
                    await bot.send_message(
                        chat_id=config.ACTION_LOG_CHANNEL_ID,
                        text=log_text,
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.error(f"BG: Log channel error: {e}")
