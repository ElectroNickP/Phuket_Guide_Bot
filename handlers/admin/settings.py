import re
import html
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from loguru import logger
from database.db import AsyncSessionLocal
from database.models import AppSettings
from services.google_sheets import google_sheets
from utils.permissions import RoleFilter
from .base import IsAdminFilter, IsSuperAdminFilter, SYSTEM_ADMIN, MENU_BUTTONS

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

class AdminStates(StatesGroup):
    waiting_for_spreadsheet_id = State()
    waiting_for_sea_spreadsheet_id = State()

@router.message(F.text == "🔗 Сменить таблицу", RoleFilter(SYSTEM_ADMIN))
async def cmd_set_sheet_kb(message: types.Message, state: FSMContext):
    await message.answer("📝 Пришли мне URL или ID новой Google таблицы:")
    await state.set_state(AdminStates.waiting_for_spreadsheet_id)

@router.message(AdminStates.waiting_for_spreadsheet_id, IsSuperAdminFilter(), ~F.text.in_(MENU_BUTTONS))
async def process_sheet_url(message: types.Message, state: FSMContext):
    raw_input = message.text
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", raw_input)
    sheet_id = match.group(1) if match else raw_input

    async with AsyncSessionLocal() as session:
        query = select(AppSettings).where(AppSettings.key == "spreadsheet_id")
        result = await session.execute(query)
        setting = result.scalars().first()
        
        if not setting:
            setting = AppSettings(key="spreadsheet_id", value=sheet_id)
            session.add(setting)
        else:
            setting.value = sheet_id
            
        await session.commit()
    
    # Reload spreadsheet in service
    try:
        await google_sheets.get_spreadsheet()
        await message.answer(f"✅ Таблица успешно обновлена и подгружена!\nID: <code>{sheet_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при подгрузке таблицы: {e}")
        
    await state.clear()

@router.message(F.text == "🔗 Сменить таблицу (Море)", RoleFilter(SYSTEM_ADMIN))
async def cmd_set_sea_sheet_kb(message: types.Message, state: FSMContext):
    await message.answer("📝 Пришли мне URL или ID новой Google таблицы (ПЛАН НА МОРЕ):")
    await state.set_state(AdminStates.waiting_for_sea_spreadsheet_id)

@router.message(AdminStates.waiting_for_sea_spreadsheet_id, IsSuperAdminFilter(), ~F.text.in_(MENU_BUTTONS))
async def process_sea_sheet_url(message: types.Message, state: FSMContext):
    raw_input = message.text
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", raw_input)
    sheet_id = match.group(1) if match else raw_input

    async with AsyncSessionLocal() as session:
        query = select(AppSettings).where(AppSettings.key == "sea_spreadsheet_id")
        result = await session.execute(query)
        setting = result.scalars().first()
        
        if not setting:
            setting = AppSettings(key="sea_spreadsheet_id", value=sheet_id)
            session.add(setting)
        else:
            setting.value = sheet_id
            
        await session.commit()
    
    # Reload in service
    from services.sea_plan import sea_plan_service
    try:
        await sea_plan_service.get_spreadsheet()
        await message.answer(f"✅ Таблица (Море) успешно обновлена!\nID: <code>{sheet_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при подгрузке таблицы (Море): {e}")
        
    await state.clear()

@router.message(F.text == "📋 Логи", RoleFilter(SYSTEM_ADMIN))
async def cmd_logs_kb(message: types.Message):
    try:
        with open("logs/bot.log", "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        last_lines = lines[-30:]
        log_text = "".join(last_lines)
        
        if len(log_text) > 3500:
            log_text = "..." + log_text[-3500:]
        
        await message.answer(
            f"📋 <b>Последние 30 строк логов:</b>\n\n<code>{html.escape(log_text)}</code>",
            parse_mode="HTML"
        )
    except FileNotFoundError:
        await message.answer("⚠️ Файл логов не найден. Бот ещё ничего не записал в файл.")
    except Exception as e:
        logger.exception(f"Error reading logs: {e}")
        await message.answer(f"❌ Ошибка при чтении логов: {e}")

@router.message(F.text == "⏱ Интервал", RoleFilter(SYSTEM_ADMIN))
async def cmd_set_interval_kb(message: types.Message):
    from utils.keyboards import get_interval_keyboard
    await message.answer(
        "⏱ <b>Настройка интервала опроса таблицы</b>\n\n"
        "Выбери, как часто бот должен проверять изменения в расписании:",
        reply_markup=get_interval_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("setint_"), IsSuperAdminFilter())
async def process_set_interval(callback: types.CallbackQuery, bot: Bot):
    new_seconds = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        query = select(AppSettings).where(AppSettings.key == "polling_interval")
        result = await session.execute(query)
        setting = result.scalars().first()
        
        if not setting:
            setting = AppSettings(key="polling_interval", value=str(new_seconds))
            session.add(setting)
        else:
            setting.value = str(new_seconds)
        
        await session.commit()
    
    # Update scheduler dynamically
    from services.scheduler import update_scheduler_interval
    await update_scheduler_interval(bot, new_seconds)
    
    await callback.message.edit_text(f"✅ Интервал обновления изменен на {new_seconds // 60} мин.")
    await callback.answer()
