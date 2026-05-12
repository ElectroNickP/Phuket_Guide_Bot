from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, update
from database.db import AsyncSessionLocal
from database.models import UserRole, AIRule
from loguru import logger

router = Router()

class AISettingsState(StatesGroup):
    waiting_for_rule_title = State()
    waiting_for_rule_content = State()
    editing_rule_id = State()

def get_categories_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🏝 Для Туристов", callback_data="ai_cat_tourist"))
    builder.row(types.InlineKeyboardButton(text="👔 Для Персонала", callback_data="ai_cat_staff"))
    builder.row(types.InlineKeyboardButton(text="⚙️ Общие правила", callback_data="ai_cat_general"))
    builder.row(types.InlineKeyboardButton(text="➕ Создать правило", callback_data="ai_rule_create"))
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_main_menu"))
    return builder.as_markup()

@router.message(F.text == "⚙️ Настройки ИИ")
async def ai_settings_main(message: types.Message):
    await message.answer(
        "⚙️ <b>Управление логикой ИИ Ассистента</b>\n\n"
        "Здесь вы можете настроить правила поведения ИИ для разных категорий пользователей.\n"
        "Активные правила автоматически добавляются в инструкции (System Prompt) ИИ.",
        reply_markup=get_categories_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("ai_cat_"))
async def list_rules_in_category(callback: types.CallbackQuery):
    category = callback.data.replace("ai_cat_", "")
    
    async with AsyncSessionLocal() as session:
        query = select(AIRule).where(AIRule.category == category)
        result = await session.execute(query)
        rules = result.scalars().all()
    
    text = f"📂 <b>Правила категории: {category.upper()}</b>\n\n"
    if not rules:
        text += "<i>Правил пока нет.</i>"
    
    builder = InlineKeyboardBuilder()
    for rule in rules:
        status_icon = "✅" if rule.is_active else "❌"
        builder.row(types.InlineKeyboardButton(
            text=f"{status_icon} {rule.title}", 
            callback_data=f"ai_rule_view_{rule.id}"
        ))
    
    builder.row(types.InlineKeyboardButton(text="🔙 К категориям", callback_data="ai_settings_home"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "ai_settings_home")
async def ai_settings_home_cb(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⚙️ <b>Управление логикой ИИ Ассистента</b>\n\nВыберите категорию:",
        reply_markup=get_categories_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("ai_rule_view_"))
async def view_rule(callback: types.CallbackQuery):
    rule_id = int(callback.data.replace("ai_rule_view_", ""))
    
    async with AsyncSessionLocal() as session:
        rule = await session.get(AIRule, rule_id)
        
    if not rule:
        await callback.answer("Ошибка: Правило не найдено.")
        return
    
    status = "АКТИВНО ✅" if rule.is_active else "ВЫКЛЮЧЕНО ❌"
    text = (
        f"📄 <b>Правило: {rule.title}</b>\n"
        f"🏷 Категория: <code>{rule.category}</code>\n"
        f"📊 Статус: <b>{status}</b>\n\n"
        f"📝 <b>Инструкция:</b>\n<code>{rule.content}</code>"
    )
    
    builder = InlineKeyboardBuilder()
    toggle_text = "🔴 Выключить" if rule.is_active else "🟢 Включить"
    builder.row(types.InlineKeyboardButton(text=toggle_text, callback_data=f"ai_rule_toggle_{rule.id}"))
    builder.row(types.InlineKeyboardButton(text="✏️ Редактировать текст", callback_data=f"ai_rule_edit_{rule.id}"))
    builder.row(types.InlineKeyboardButton(text="🗑 Удалить", callback_data=f"ai_rule_delete_{rule.id}"))
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data=f"ai_cat_{rule.category}"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("ai_rule_toggle_"))
async def toggle_rule(callback: types.CallbackQuery):
    rule_id = int(callback.data.replace("ai_rule_toggle_", ""))
    
    async with AsyncSessionLocal() as session:
        rule = await session.get(AIRule, rule_id)
        if rule:
            rule.is_active = not rule.is_active
            await session.commit()
            await callback.answer(f"Статус правила изменен на {'Вкл' if rule.is_active else 'Выкл'}")
            # Refresh view
            callback.data = f"ai_rule_view_{rule_id}"
            await view_rule(callback)
        else:
            await callback.answer("Ошибка")

@router.callback_query(F.data.startswith("ai_rule_edit_"))
async def edit_rule_start(callback: types.CallbackQuery, state: FSMContext):
    rule_id = int(callback.data.replace("ai_rule_edit_", ""))
    await state.update_data(edit_rule_id=rule_id)
    await state.set_state(AISettingsState.waiting_for_rule_content)
    
    await callback.message.answer("⌨️ <b>Введите новый текст инструкции для этого правила:</b>\n\n(Используйте четкие и понятные команды для ИИ)", parse_mode="HTML")
    await callback.answer()

@router.message(StateFilter(AISettingsState.waiting_for_rule_content))
async def process_rule_content_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    rule_id = data.get("edit_rule_id")
    
    async with AsyncSessionLocal() as session:
        if rule_id:
            # EDITING EXISTING RULE
            rule = await session.get(AIRule, rule_id)
            if rule:
                rule.content = message.text
                await session.commit()
                await message.answer(f"✅ Текст правила <b>'{rule.title}'</b> успешно обновлен!", parse_mode="HTML")
            else:
                await message.answer("❌ Ошибка: правило не найдено.")
        else:
            # CREATING NEW RULE
            category = data.get("new_rule_cat")
            title = data.get("new_rule_title")
            if not category or not title:
                await message.answer("❌ Ошибка: данные создания правила утеряны.")
                await state.clear()
                return
                
            new_rule = AIRule(category=category, title=title, content=message.text)
            session.add(new_rule)
            await session.commit()
            await message.answer(f"✅ Правило <b>'{title}'</b> создано и активировано!", parse_mode="HTML")
            
    await state.clear()
    # Provide a button to go back
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⚙️ Настройки ИИ", callback_data="ai_settings_home"))
    await message.answer("Вернуться в настройки:", reply_markup=builder.as_markup())

# --- Create Rule Flow ---
@router.callback_query(F.data == "ai_rule_create")
async def create_rule_start(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Турист", callback_data="ai_newcat_tourist"))
    builder.row(types.InlineKeyboardButton(text="Персонал", callback_data="ai_newcat_staff"))
    builder.row(types.InlineKeyboardButton(text="Общее", callback_data="ai_newcat_general"))
    
    await callback.message.edit_text("Выберите категорию для нового правила:", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("ai_newcat_"))
async def create_rule_cat_selected(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("ai_newcat_", "")
    await state.update_data(new_rule_cat=category)
    await state.set_state(AISettingsState.waiting_for_rule_title)
    await callback.message.answer("📎 Напишите краткое <b>Название</b> для этого правила (например: 'Приветствие туристов'):", parse_mode="HTML")
    await callback.answer()

@router.message(StateFilter(AISettingsState.waiting_for_rule_title))
async def process_new_rule_title(message: types.Message, state: FSMContext):
    await state.update_data(new_rule_title=message.text)
    await state.set_state(AISettingsState.waiting_for_rule_content)
    await message.answer("✍️ Теперь напишите саму <b>Инструкцию</b> (текст, который будет добавлен к логике ИИ):", parse_mode="HTML")

@router.callback_query(F.data.startswith("ai_rule_delete_"))
async def delete_rule(callback: types.CallbackQuery):
    rule_id = int(callback.data.replace("ai_rule_delete_", ""))
    async with AsyncSessionLocal() as session:
        rule = await session.get(AIRule, rule_id)
        if rule:
            cat = rule.category
            await session.delete(rule)
            await session.commit()
            await callback.answer("Правило удалено")
            # Go back to category list
            callback.data = f"ai_cat_{cat}"
            await list_rules_in_category(callback)
        else:
            await callback.answer("Ошибка")
