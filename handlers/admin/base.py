from aiogram import types
from aiogram.filters import BaseFilter
from config import config
from database.models import UserRole

# ----------------- FILTERS -----------------
class IsAdminFilter(BaseFilter):
    """Router-level filter: silently ignores non-admin users."""
    async def __call__(self, event: types.Message | types.CallbackQuery, **data) -> bool:
        user = event.from_user if hasattr(event, 'from_user') else None
        if not user:
            return False
            
        # Impersonation Check (Tester Mode)
        imp_user = data.get("impersonated_user")
        if imp_user:
            return imp_user.get("role") in [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE, UserRole.HOT_LINE, UserRole.PIER_MANAGER]

        # Check by ID
        if user.id in config.admin_id_list:
            return True
            
        # Check by Username
        if user.username:
            uname = user.username.lower()
            return uname in config.admin_username_list or uname in config.tester_username_list
            
        return False

class IsSuperAdminFilter(BaseFilter):
    """Router-level filter: only allows super admins (@Pankonick)."""
    async def __call__(self, event: types.Message | types.CallbackQuery, **data) -> bool:
        user = event.from_user if hasattr(event, 'from_user') else None
        if not user:
            return False
            
        # Impersonation Check (Tester Mode)
        imp_user = data.get("impersonated_user")
        if imp_user:
            return imp_user.get("role") == UserRole.SUPER_ADMIN

        if not user.username:
            return False
        return user.username.lower() == "pankonick"

class IsTesterFilter(BaseFilter):
    """Only allowing authorized testers."""
    async def __call__(self, event: types.Message | types.CallbackQuery) -> bool:
        user = event.from_user
        if not user or not user.username:
            return False
            
        # Optional: check if they are explicitly configured testers
        return user.username.lower() in config.tester_username_list

# ----------------- CONSTANTS -----------------
# Role definition groups for cleaner filters
ADMIN_ALL = [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE, UserRole.HOT_LINE, UserRole.PIER_MANAGER]
ADMIN_MANAGEMENT = [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE]
SYSTEM_ADMIN = [UserRole.SUPER_ADMIN]

MENU_BUTTONS = [
    "📅 Моё расписание", "🌊 План на море", "🚐 План на суше", "👤 Мой статус", "📝 Обратная связь",
    "👁 Мониторинг гидов", "👁 Контроль Смены", "🌊 Мониторинг моря", "🚐 Мониторинг суши", "📊 Статистика", "🔍 Тест-Аудит", 
    "📋 Job Order", "📅 Общее расписание", "🔍 Тест Пробуждения", "🆘 Тест SOS",
    "⏱ Интервал", "📋 Логи", "🔗 Сменить таблицу", "🔗 Сменить таблицу (Море)", "🔙 Главное меню"
]

