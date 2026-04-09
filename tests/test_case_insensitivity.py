import asyncio
import datetime
from services.scheduler import check_guide_wakeups
from aiogram import Bot
from unittest.mock import AsyncMock, patch
from database.db import AsyncSessionLocal
from database.models import User
from sqlalchemy import select

import pytest

@pytest.mark.asyncio
async def test_case_insensitivity():
    # Mock bot

    bot = AsyncMock(spec=Bot)
    
    # Mock time to 2:00 AM (when 2:50 pickup should trigger wake-up at 1:50)
    mock_now = datetime.datetime(2026, 3, 22, 2, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=7)))
    
    # Verify User exists in DB with mixed case
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.username == 'KK_Kira69'))
        user = res.scalars().first()
        if user:
            print(f"Found User in DB: {user.username} (ID: {user.telegram_id})")
        else:
            print("User @KK_Kira69 not found in DB!")
            return

    with patch('services.scheduler.get_phuket_now', return_value=mock_now):
        print(f"Running wake-up check test at {mock_now}...")
        await check_guide_wakeups(bot)
    
    # Check if send_message was called
    if bot.send_message.called:
        print("SUCCESS: bot.send_message was called!")
        for call in bot.send_message.call_args_list:
            print(f"  Sent to: {call.args[0]}")
    else:
        print("FAILURE: bot.send_message was NOT called for @KK_Kira69!")

if __name__ == '__main__':
    asyncio.run(test_case_insensitivity())
