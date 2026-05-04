import datetime
from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import User, UserRole
from services.sea_plan import sea_plan_service
from loguru import logger

async def get_guides_list():
    """Returns a list of all registered guides and managers."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.role.in_([UserRole.GUIDE, UserRole.PIER_MANAGER, UserRole.ADMIN]))
            result = await session.execute(stmt)
            users = result.scalars().all()
            
            res = "👥 Список зарегистрированных сотрудников:\n"
            for u in users:
                res += f"- @{u.username or 'no_user'} ({u.full_name or 'No Name'}) - Роль: {u.role}\n"
            return res
    except Exception as e:
        logger.error(f"Tool error (get_guides_list): {e}")
        return f"Ошибка при получении списка гидов: {e}"

async def get_schedule_today():
    """Returns the combined schedule for today (Sea and Land)."""
    try:
        from utils.time import get_phuket_now
        today = get_phuket_now().date()
        expected = await sea_plan_service.get_expected_reports(today)
        
        if not expected:
            return f"📭 Расписание на сегодня ({today.strftime('%d.%m')}) пусто или не найдено в Google Sheets."
            
        res = f"📅 Расписание на сегодня ({today.strftime('%d.%m')}):\n"
        for uname, prog, category in expected:
            res += f"- [{category}] @{uname} -> {prog}\n"
        return res
    except Exception as e:
        logger.error(f"Tool error (get_schedule_today): {e}")
        return f"Ошибка при получении расписания: {e}"

async def get_schedule_tomorrow():
    """Returns the combined schedule for tomorrow (Sea and Land)."""
    try:
        from utils.time import get_phuket_now
        import datetime
        tomorrow = get_phuket_now().date() + datetime.timedelta(days=1)
        expected = await sea_plan_service.get_expected_reports(tomorrow)
        
        if not expected:
            return f"📭 Расписание на завтра ({tomorrow.strftime('%d.%m')}) пока пусто или не найдено."
            
        res = f"📅 Расписание на завтра ({tomorrow.strftime('%d.%m')}):\n"
        for uname, prog, category in expected:
            res += f"- [{category}] @{uname} -> {prog}\n"
        return res
    except Exception as e:
        logger.error(f"Tool error (get_schedule_tomorrow): {e}")
        return f"Ошибка при получении расписания на завтра: {e}"

async def check_google_sheets_connectivity():
    """Checks the connection to Googles Sheets and lists available worksheet titles."""
    try:
        spreadsheet = await sea_plan_service.get_spreadsheet()
        if not spreadsheet:
            return "❌ Ошибка: Не удалось открыть Google таблицу. Проверьте SERVICE_ACCOUNT_FILE и права доступа."
        
        wdict = await sea_plan_service._get_cached_worksheets_dict(spreadsheet)
        titles = list(wdict.keys())
        
        res = f"✅ Соединение с Google Sheets установлено успешно.\n"
        res += f"📄 Название таблицы: '{spreadsheet.title}'\n"
        res += f"📂 Доступные вкладки: {', '.join(titles)}"
        return res
    except Exception as e:
        logger.error(f"Tool error (check_google_sheets_connectivity): {e}")
        return f"Ошибка при проверке Google Sheets: {e}"

# Map tool names to actual functions for the service
TOOLS_MAP = {
    "get_guides_list": get_guides_list,
    "get_schedule_today": get_schedule_today,
    "get_schedule_tomorrow": get_schedule_tomorrow,
    "check_google_sheets_connectivity": check_google_sheets_connectivity
}

# OpenAI Tool Definitions
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_guides_list",
            "description": "Получить список всех зарегистрированных гидов и менеджеров в системе.",
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule_today",
            "description": "Посмотреть расписание всех туров (море и суша) на сегодня из Google Sheets.",
        }
    },
     {
        "type": "function",
        "function": {
            "name": "get_schedule_tomorrow",
            "description": "Посмотреть расписание всех туров на завтра из Google Sheets.",
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_google_sheets_connectivity",
            "description": "Проверить подключение к Google Sheets и получить список всех доступных вкладок (дата-листов).",
        }
    }
]
