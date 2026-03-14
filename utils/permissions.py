from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from typing import List, Union
from database.db import AsyncSessionLocal
from database.models import User, UserRole
from sqlalchemy import select
from config import config

class RoleFilter(BaseFilter):
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        user_id = event.from_user.id
        
        # Super admin bypass (Hardcoded to pankonick or based on config.ADMIN_ID)
        # Note: In a production system, we'd check the DB, but for immediate access, we check config
        is_pankonick = False
        if event.from_user.username:
            is_pankonick = event.from_user.username.lower() == "pankonick"
            
        if is_pankonick or user_id == config.ADMIN_ID:
            return True

        async with AsyncSessionLocal() as session:
            query = select(User).where(User.telegram_id == user_id)
            result = await session.execute(query)
            user = result.scalar_one_or_none()
            
            if not user:
                return False
            
            # Special case for 'admin' role in self.allowed_roles: 
            # it should include HEAD_OF_GUIDE, HOT_LINE, etc. unless specific check needed
            if user.role == UserRole.SUPER_ADMIN:
                return True
                
            return user.role in self.allowed_roles
