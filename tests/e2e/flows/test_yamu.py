import pytest
from tests.e2e.runner import run_flow

@pytest.mark.asyncio
async def test_pier_manager_boats_yamu():
    """Test Pier Manager Boats checking for Yamu specifically."""
    flow = [
        ("send", "/start"),
        ("expect", "Твой цифровой помощник", False),
        ("send", "⚓️ Панель Пирс-Менеджера"),
        ("expect", "Пожалуйста, выберите пирс для работы", True),
        ("click", 1), # Yamu is index 1
        ("expect", "Выберите нужное действие", False),
        ("send", "⛴ Лодки сегодня"),
        # The expected output should NOT be "Данных для пирса Yamu на ... не найдено."
        # It should show "Лодки на пирсе Yamu" or similar
        ("expect", "⛴ Лодки на пирсе Yamu", False)
    ]
    await run_flow(flow)
