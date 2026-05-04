import pytest
from tests.e2e.runner import run_flow

@pytest.mark.asyncio
async def test_role_change_dump():
    """Test what menu the user gets on /start after a role change."""
    flow = [
        ("send", "/start"),
        ("expect", "Твой цифровой помощник", False),
        ("expect", "Панель Пирс-Менеджера", True) # Should pass if user is admin or pier manager
    ]
    await run_flow(flow)
