from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_keyboard():
    keyboard = [
        [KeyboardButton(text="📅 Моё расписание"), KeyboardButton(text="🌊 План на море")],
        [KeyboardButton(text="🚐 План на суше"), KeyboardButton(text="👤 Мой статус")],
        [KeyboardButton(text="🚀 Начать программу"), KeyboardButton(text="📝 Обратная связь")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_menu_keyboard(is_super_admin: bool = False):
    keyboard = [
        [KeyboardButton(text="👁 Мониторинг гидов"), KeyboardButton(text="🌊 Мониторинг моря")],
        [KeyboardButton(text="🚐 Мониторинг суши"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🔍 Тест-Аудит"), KeyboardButton(text="📋 Job Order")],
        [KeyboardButton(text="📅 Общее расписание"), KeyboardButton(text="📝 Отчет за гида")]
    ]
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
        [InlineKeyboardButton(text="✅ No problem", callback_data="report_status_ok")]
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
