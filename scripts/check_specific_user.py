import asyncio
from database.db import AsyncSessionLocal
from database.models import User
from sqlalchemy import select

async def check_user(username):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalars().first()
        print(f"User: {user.username if user else 'None'}")

if __name__ == '__main__':
    import sys
    username = sys.argv[1] if len(sys.argv) > 1 else 'kk_kira69'
    asyncio.run(check_user(username))
