import asyncio
import datetime
from services.scheduler import check_guide_wakeups
from aiogram import Bot
from config import config
from unittest.mock import AsyncMock, patch

import pytest

@pytest.mark.asyncio
async def test_notifications():
    # Mock bot

    bot = AsyncMock(spec=Bot)
    
    # Mock time to 6:45 AM (when 7:30 pickups should trigger wake-up at 6:30)
    mock_now = datetime.datetime(2026, 3, 22, 6, 45, tzinfo=datetime.timezone(datetime.timedelta(hours=7)))
    
    with patch('services.scheduler.get_phuket_now', return_value=mock_now):
        print(f"Running wake-up check test at {mock_now}...")
        await check_guide_wakeups(bot)
    
    print("\nCheck finished. Examine logs for 'Guide @... found in land plan but NOT registered'")

if __name__ == '__main__':
    asyncio.run(test_notifications())
