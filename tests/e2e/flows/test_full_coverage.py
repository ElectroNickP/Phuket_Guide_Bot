import pytest
from tests.e2e.runner import run_flow

@pytest.mark.asyncio
async def test_main_menu_status():
    """Test standard main menu status check."""
    flow = [
        ("send", "/start"),
        ("expect", "Твой цифровой помощник", False),
        ("send", "👤 Мой статус"),
        ("expect", "Твой статус:", False), 
    ]
    await run_flow(flow)

@pytest.mark.asyncio
async def test_land_plan():
    """Test viewing land plan."""
    flow = [
        ("send", "/start"),
        ("expect", "Твой цифровой помощник", False),
        ("send", "🚐 План на суше"),
        ("expect", "Выберите день", True), # Should see inline buttons Сегодня / Завтра
        ("click", 1), # Click 'Завтра' (Tomorrow) inline button
        ("expect", "на суше", False)
    ]
    await run_flow(flow)

@pytest.mark.asyncio
async def test_schedule_4day():
    """Test 4-day schedule directly."""
    flow = [
        ("send", "/start"),
        ("expect", "Твой цифровой помощник", False),
        ("send", "📅 Моё расписание"),
        ("expect", "Загружаю твоё расписание на 4 дня", False) 
    ]
    await run_flow(flow)

@pytest.mark.asyncio
async def test_start_program_flow():
    """Test the Start Program initiation."""
    flow = [
        ("send", "/start"),
        ("expect", "Твой цифровой помощник", False),
        ("send", "🚀 Начать программу"),
        ("expect", "Ищу программы для", False)
    ]
    await run_flow(flow)

@pytest.mark.asyncio
async def test_pier_manager_dashboard_access():
    """Test Pier Manager workflow access."""
    flow = [
        ("send", "/start"),
        ("expect", "Твой цифровой помощник", False),
        ("send", "⚓️ Панель Пирс-Менеджера"),
        ("expect", "Пожалуйста, выберите пирс для работы", True),
        # Click on the first pier (RPM)
        ("click", 0),
        ("expect", "Выберите нужное действие", False),
        # Try to open Pier ops
        ("send", "🚪 Открыть пирс RPM"),
        ("expect", "Операции на пирсе RPM", False),
        # See NP calculation
        ("send", "📩 Конверты NP"),
        ("expect", "Рассчитываю конверты для лодок на пирсе", False),
        # Go back to Main Menu
        ("send", "🔙 Главное меню"),
        ("expect", "Твой цифровой помощник", False)
    ]
    await run_flow(flow)

@pytest.mark.asyncio
async def test_pier_manager_boats_today():
    """Test Pier Manager Boats checking."""
    flow = [
        ("send", "/start"),
        ("expect", "Твой цифровой помощник", False),
        ("send", "⚓️ Панель Пирс-Менеджера"),
        ("expect", "Пожалуйста, выберите пирс для работы", True),
        ("click", 0), # RPM
        ("expect", "Выберите нужное действие", False),
        ("send", "⛴ Лодки сегодня"),
        ("expect", "Загружаю данные из Google Таблицы", False)
    ]
    await run_flow(flow)
