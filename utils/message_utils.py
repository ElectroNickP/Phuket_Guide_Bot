from aiogram import types

MAX_MSG_LEN = 4096

async def send_long_message(message: types.Message, text: str, parse_mode: str = "HTML", **kwargs):
    """Splits and sends a message that may exceed Telegram's 4096 character limit."""
    while text:
        chunk = text[:MAX_MSG_LEN]
        # Try to split at the last newline to avoid cutting mid-line
        if len(text) > MAX_MSG_LEN:
            split_at = chunk.rfind("\n")
            if split_at > 0:
                chunk = text[:split_at]
        await message.answer(chunk, parse_mode=parse_mode, **kwargs)
        text = text[len(chunk):].lstrip("\n")
