import asyncio
from database.db import AsyncSessionLocal
from database.models import User
from sqlalchemy import select

async def dump_users():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        print(f"Total users in DB: {len(users)}")
        for u in users:
            print(f"ID: {u.telegram_id}, Username: \"{u.username}\", Last Contact: {u.last_contact}, Last Action: \"{u.last_action}\", Start/Finish: {u.count_start}/{u.count_finish}")

if __name__ == '__main__':
    asyncio.run(dump_users())
