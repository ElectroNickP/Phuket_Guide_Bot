import asyncio
from services.ai_service import ai_service
from loguru import logger

async def test_ai_parsing():
    text = "Сегодня заправил лодку Sea Ray на 120 литров, починили помпу, все ок"
    logger.info(f"Testing text: {text}")
    try:
        result = await ai_service.parse_operational_report(text)
        logger.info(f"AI PARSED RESULT: {result}")
    except Exception as e:
        logger.error(f"AI ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_ai_parsing())
