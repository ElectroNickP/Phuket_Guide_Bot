from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from config import config

def get_tourist_menu_keyboard(auth_token: str | None = None):
    url = f"{config.WEBAPP_URL}/tourist"
    if auth_token:
        url += f"?token={auth_token}"
        
    keyboard = [
        [KeyboardButton(text="🛍 Buddy shop", web_app=WebAppInfo(url=url))],
        [KeyboardButton(text="📦 Заказать в чате")],
        [KeyboardButton(text="🆘 Поддержка")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_main_menu_keyboard(role: str | None = None, auth_token: str | None = None):
    # IF BOT_MODE is tourist, ignore EVERYTHING and show tourist menu
    if config.BOT_MODE == "tourist":
        return get_tourist_menu_keyboard(auth_token=auth_token)

    # Original staff-aware logic for other modes
    from database.models import UserRole
    staff_roles = (UserRole.GUIDE, UserRole.PIER_MANAGER, UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE, UserRole.HOT_LINE)
    
    if not role or role not in staff_roles:
        return get_tourist_menu_keyboard(auth_token=auth_token)

    url = f"{config.WEBAPP_URL}/"
    if auth_token:
        url += f"?token={auth_token}"
        
    keyboard = [
        [KeyboardButton(text="🛍 Buddy shop", web_app=WebAppInfo(url=f"{config.WEBAPP_URL}/tourist?token={auth_token}" if auth_token else f"{config.WEBAPP_URL}/tourist"))],
        [KeyboardButton(text="📱 Моя Панель (Mini App)", web_app=WebAppInfo(url=url))],
        [KeyboardButton(text="📅 Моё расписание"), KeyboardButton(text="🌊 План на море")],
        [KeyboardButton(text="🚐 План на суше"), KeyboardButton(text="👤 Мой статус")],
        [KeyboardButton(text="🚀 Начать программу"), KeyboardButton(text="🏁 Завершить программу")],
        [KeyboardButton(text="📝 Обратная связь"), KeyboardButton(text="🆘 Нужна помощь")],
        [KeyboardButton(text="📚 Библиотека гида")]
    ]
    
    if role in (UserRole.PIER_MANAGER, UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE):
        keyboard.insert(2, [KeyboardButton(text="⚓️ Панель Пирс-Менеджера")])
        
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_menu_keyboard(is_super_admin: bool = False, role: str | None = None, auth_token: str | None = None):
    # IF BOT_MODE is tourist, ignore EVERYTHING and show tourist menu
    if config.BOT_MODE == "tourist":
        return get_tourist_menu_keyboard(auth_token=auth_token)

    url = f"{config.WEBAPP_URL}/"
    tourist_url = f"{config.WEBAPP_URL}/tourist"
    if auth_token:
        url += f"?token={auth_token}"
        
    keyboard = [
        [KeyboardButton(text="🛍 Buddy shop", web_app=WebAppInfo(url=f"{config.WEBAPP_URL}/tourist?token={auth_token}" if auth_token else f"{config.WEBAPP_URL}/tourist"))],
        [KeyboardButton(text="📱 Моя Панель (Mini App)", web_app=WebAppInfo(url=url))],
        [KeyboardButton(text="👤 Управление пользователями")],
        [KeyboardButton(text="👁 Мониторинг гидов"), KeyboardButton(text="👁 Контроль Смены")],
        [KeyboardButton(text="🌊 Мониторинг моря"), KeyboardButton(text="🚐 Мониторинг суши")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🔍 Тест-Аудит")],
        [KeyboardButton(text="📋 Job Order"), KeyboardButton(text="📅 Общее расписание")],
        [KeyboardButton(text="📝 Отчет за гида"), KeyboardButton(text="🔍 Тест Пробуждения")],
        [KeyboardButton(text="🆘 Тест SOS"), KeyboardButton(text="⚙️ Настройки ИИ")]
    ]
    
    from database.models import UserRole
    if role in (UserRole.PIER_MANAGER, UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE) or is_super_admin:
        keyboard.insert(2, [KeyboardButton(text="⚓️ Панель Пирс-Менеджера")])
    if is_super_admin:
        keyboard.append([KeyboardButton(text="⏱ Интервал"), KeyboardButton(text="📋 Логи")])
        keyboard.append([KeyboardButton(text="🔗 Сменить таблицу"), KeyboardButton(text="🔗 Сменить таблицу (Море)")])
    
    keyboard.append([KeyboardButton(text="🔙 Главное меню")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_schedule_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Сегодня", callback_data="sched_today")],
        [InlineKeyboardButton(text="Завтра", callback_data="sched_tomorrow")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_interval_keyboard():
    intervals = [
        ("1 мин", 60), ("5 мин", 300), ("10 мин", 600),
        ("15 мин", 900), ("30 мин", 1800), ("1 час", 3600)
    ]
    buttons = []
    for i in range(0, len(intervals), 2):
        row = [
            InlineKeyboardButton(text=intervals[i][0], callback_data=f"setint_{intervals[i][1]}"),
            InlineKeyboardButton(text=intervals[i+1][0], callback_data=f"setint_{intervals[i+1][1]}")
        ]
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_sea_plan_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Сегодня", callback_data="sea_today")],
        [InlineKeyboardButton(text="Завтра", callback_data="sea_tomorrow")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_land_plan_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Сегодня", callback_data="land_today")],
        [InlineKeyboardButton(text="Завтра", callback_data="land_tomorrow")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_job_order_date_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Сегодня", callback_data="jo_date_today")],
        [InlineKeyboardButton(text="Завтра", callback_data="jo_date_tomorrow")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_general_schedule_date_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Сегодня", callback_data="gs_date_today")],
        [InlineKeyboardButton(text="Завтра", callback_data="gs_date_tomorrow")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_monitor_date_keyboard():
    buttons = [
        [
            InlineKeyboardButton(text="⏮ Вчера", callback_data="mon_date_yesterday"),
            InlineKeyboardButton(text="📅 Сегодня", callback_data="mon_date_today")
        ],
        [
            InlineKeyboardButton(text="📅 Завтра", callback_data="mon_date_tomorrow"),
            InlineKeyboardButton(text="⏭ Послезавтра", callback_data="mon_date_after")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_suggested_pax_keyboard(suggested_pax: str):
    buttons = [
        [InlineKeyboardButton(text=f"✅ {suggested_pax} (как в плане)", callback_data=f"report_pax_{suggested_pax}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_suggested_cot_keyboard(suggested_cot: str):
    buttons = [
        [InlineKeyboardButton(text=f"✅ {suggested_cot} (как в плане)", callback_data=f"report_cot_{suggested_cot}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_suggested_captain_keyboard(suggested_captain: str):
    buttons = [
        [InlineKeyboardButton(text=f"✅ {suggested_captain} (по плану)", callback_data="report_captain_suggested")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_suggested_status_keyboard():
    buttons = [
        [
            InlineKeyboardButton(text="✅ No problem", callback_data="report_status_ok"),
            InlineKeyboardButton(text="⚠️ Problem", callback_data="report_status_problem"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_np_keyboard():
    # Helper for selecting National Parks
    buttons = [
        [InlineKeyboardButton(text="NP PP", callback_data="report_np_PP")],
        [InlineKeyboardButton(text="NP GB", callback_data="report_np_GB")],
        [InlineKeyboardButton(text="NP HG", callback_data="report_np_HG")],
        [InlineKeyboardButton(text="✅ Готово (Далее)", callback_data="report_np_done")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
