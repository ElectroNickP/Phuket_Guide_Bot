from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, update
from database.db import AsyncSessionLocal
from database.models import User, UserRole
from utils.permissions import RoleFilter
from .base import IsAdminFilter, ADMIN_MANAGEMENT, MENU_BUTTONS
from loguru import logger

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

class UserManagementStates(StatesGroup):
    waiting_for_search_query = State()

@router.message(F.text == "👤 Управление пользователями", RoleFilter(ADMIN_MANAGEMENT))
async def cmd_manage_users(message: types.Message):
    async with AsyncSessionLocal() as session:
        # Get last 20 active users
        query = select(User).order_by(User.last_contact.desc()).limit(20)
        result = await session.execute(query)
        users = result.scalars().all()
        
    builder = InlineKeyboardBuilder()
    for user in users:
        name = user.username or user.full_name or str(user.telegram_id)
        builder.button(text=f"👤 {name}", callback_data=f"manage_user_{user.telegram_id}")
    
    builder.adjust(1)
    # builder.row(types.InlineKeyboardButton(text="🔍 Поиск", callback_data="user_search"))
    
    await message.answer(
        "👤 <b>Управление пользователями</b>\n\n"
        "Ниже список последних 20 активных пользователей. Выберите пользователя для управления его ролью:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("manage_user_"))
async def process_manage_user(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    await show_user_details(callback, user_id)

async def show_user_details(callback: types.CallbackQuery, user_id: int):
    async with AsyncSessionLocal() as session:
        query = select(User).where(User.telegram_id == user_id)
        result = await session.execute(query)
        user = result.scalars().first()
    
    if not user:
        await callback.answer("❌ Пользователь не найден")
        return

    text = (
        f"👤 <b>Пользователь:</b> {user.full_name or 'N/A'}\n"
        f"🆔 <b>ID:</b> <code>{user.telegram_id}</code>\n"
        f"🔗 <b>Username:</b> @{user.username or 'N/A'}\n"
        f"🔑 <b>Текущая роль:</b> <code>{user.role}</code>\n"
        f"📅 <b>Последний контакт:</b> {user.last_contact.strftime('%d.%m.%Y %H:%M') if user.last_contact else 'N/A'}"
    )
    
    builder = InlineKeyboardBuilder()
    roles = [
        (UserRole.GUIDE, "Гид"),
        (UserRole.PIER_MANAGER, "Пирс-Менеджер"),
        (UserRole.HOT_LINE, "Hot Line"),
        (UserRole.HEAD_OF_GUIDE, "Head Guide"),
        (UserRole.ADMIN, "Админ")
    ]
    
    for role_val, role_name in roles:
        prefix = "✅ " if user.role == role_val else ""
        builder.button(text=f"{prefix}{role_name}", callback_data=f"set_role_{user.telegram_id}_{role_val}")
    
    builder.adjust(2)
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_users"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data == "back_to_users")
async def process_back_users(callback: types.CallbackQuery):
    await cmd_manage_users(callback.message)
    await callback.answer()

@router.callback_query(F.data.startswith("set_role_"))
async def process_set_role(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    new_role = "_".join(parts[3:])
    
    async with AsyncSessionLocal() as session:
        stmt = update(User).where(User.telegram_id == user_id).values(role=new_role)
        await session.execute(stmt)
        await session.commit()
    
    await callback.answer(f"✅ Роль успешно изменена на {new_role}")
    # Refresh view
    await show_user_details(callback, user_id)
