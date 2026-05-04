import pytest
from tests.e2e.runner import run_flow

@pytest.mark.asyncio
async def test_schedule_flow():
    """Test clicking on the Schedule button and getting the inline keyboard."""
    flow = [
        ("send", "/start"),
        ("expect", "Твой цифровой помощник", False),
        ("send", "📅 Моё расписание"),
        ("expect", "Выберите день", True), # Expect to see date selection keyboard
        ("click", 0), # Click 'Сегодня' (Today) inline button
        ("expect", "Нет данных", False) # Expect schedule result or no plan
    ]
    await run_flow(flow)

@pytest.mark.asyncio
async def test_sea_plan_flow():
    """Test viewing sea plan."""
    flow = [
        ("send", "🌊 План на море"),
        ("expect", "Выберите день", True),
        ("click", 1), # Click 'Завтра' (Tomorrow) inline button
        ("expect", "Нет данных", False)  # The DB is probably empty for tomorrow for the tester user
    ]
    await run_flow(flow)
