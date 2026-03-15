import time
from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from loguru import logger


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware that logs all incoming messages and callback queries.
    Helps trace user issues and understand usage patterns.
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any]
    ) -> Any:
        start_time = time.monotonic()

        # Extract user/event info
        user = event.from_user
        user_info = f"@{user.username}" if user.username else f"id:{user.id}"

        # Impersonation Check (Tester Mode)
        impersonated_user = None
        redis = data.get("state").storage.redis if hasattr(data.get("state"), "storage") and hasattr(data.get("state").storage, "redis") else None
        
        if redis:
            import json
            imp_key = f"impersonation:{user.id}"
            imp_data = await redis.get(imp_key)
            if imp_data:
                impersonated_user = json.loads(imp_data)
                user_info = f"@{user.username or user.id} (as @{impersonated_user['username']})"
                data["impersonated_user"] = impersonated_user

        if isinstance(event, Message):
            content = event.text or f"[{event.content_type}]"
            logger.info(f"MSG  | {user_info} | {content[:80]}")
        elif isinstance(event, CallbackQuery):
            logger.info(f"CBQ  | {user_info} | data={event.data}")

        try:
            result = await handler(event, data)
            elapsed = (time.monotonic() - start_time) * 1000
            logger.debug(f"DONE | {user_info} | {elapsed:.0f}ms")
            return result
        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            logger.exception(f"ERR  | {user_info} | {elapsed:.0f}ms | {e}")
            raise
