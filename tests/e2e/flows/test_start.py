import pytest
from tests.e2e.runner import run_flow

@pytest.mark.asyncio
async def test_start():
    flow = [
        ("send", "/start"),
        ("expect", "Твой цифровой помощник"),
    ]
    await run_flow(flow)
