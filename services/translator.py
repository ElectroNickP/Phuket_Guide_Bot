"""
Async-friendly translation helper.
Uses deep-translator (GoogleTranslator) — free, no API key needed.
Runs in a thread pool to avoid blocking the async event loop.
"""
import asyncio
from loguru import logger

try:
    from deep_translator import GoogleTranslator
    _translator_available = True
except ImportError:
    _translator_available = False
    logger.warning("deep-translator not installed; auto-translation disabled.")


async def translate_to_english(text: str) -> str | None:
    """
    Translate text to English.
    Returns translated string, or None if translation fails / lib not available.
    Silently swallows all errors so the bot never breaks because of translation.
    """
    if not _translator_available or not text or not text.strip():
        return None

    def _do_translate():
        return GoogleTranslator(source="auto", target="en").translate(text)

    try:
        result = await asyncio.to_thread(_do_translate)
        if result and result.strip().lower() != text.strip().lower():
            return result.strip()
        # If the result is identical to the input, the text was probably already
        # in English — skip the translation line.
        return None
    except Exception as e:
        logger.warning(f"Translation failed: {e}")
        return None
