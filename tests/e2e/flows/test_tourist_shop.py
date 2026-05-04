import pytest
from tests.e2e.runner import run_flow

@pytest.mark.asyncio
async def test_tourist_shop_chat():
    flow = [
        ("send", "/start"),
        # We check for the tourist-specific greeting
        ("expect", "Добро пожаловать на Пхукет"), 
        ("expect", "🛍 Заказать онлайн"),
        ("send", "🛍 Заказать онлайн"),
        ("expect", "Выберите категорию товаров"),
        ("click", 0), # Click first category
        ("expect", "Выберите товар"),
        ("click", 0), # Click first product
        ("expect", "Заказ #"),
        ("expect", "Оплатить (NSPK)"),
    ]
    await run_flow(flow)
