from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_keyboard():
    keyboard = [
        [KeyboardButton(text="📅 Моё расписание")],
        [KeyboardButton(text="👤 Мой статус"), KeyboardButton(text="📝 Обратная связь")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_menu_keyboard():
    keyboard = [
        [KeyboardButton(text="👁 Мониторинг гидов")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⏱ Интервал")],
        [KeyboardButton(text="🔗 Сменить таблицу"), KeyboardButton(text="📋 Логи")],
        [KeyboardButton(text="🔙 Главное меню")]
    ]
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
