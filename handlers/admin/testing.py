import datetime
import asyncio
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import Bot

from services.scheduler import get_phuket_now, get_phuket_today, get_wakeup_message_data
from services.sea_plan import sea_plan_service
from database.db import AsyncSessionLocal
from database.models import WakeUpConfirmation
from sqlalchemy import select
from loguru import logger
from utils.permissions import RoleFilter
from .base import ADMIN_ALL, ADMIN_MANAGEMENT, IsAdminFilter, IsTesterFilter
from database.models import UserRole
from services.google_sheets import google_sheets
from aiogram.filters import Command

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

@router.message(F.text == "🔍 Тест-Аудит", RoleFilter(ADMIN_MANAGEMENT))
async def cmd_run_audit(message: types.Message):
    await message.answer("🧪 <b>Запускаю полное тестирование...</b>\n\nЯ прогню симуляцию ответов для всех гидов на сегодня и завтра.\n\n⏳ Пожалуйста, подожди...", parse_mode="HTML")
    try:
        from scripts.bot_audit import run_audit
        report_link = await run_audit()
        if report_link:
            await message.answer(f"✅ <b>Тестирование завершено!</b>\n\n📊 Отчет доступен по ссылке:\n{report_link}", parse_mode="HTML")
        else:
            await message.answer("❌ Произошла ошибка при создании отчета. Проверь логи.")
    except Exception as e:
        logger.exception(f"Error running audit from bot: {e}")
        await message.answer(f"❌ Критическая ошибка при выполнении аудита: {e}")

@router.message(F.text == "🔍 Тест Пробуждения", RoleFilter(ADMIN_ALL))
async def cmd_wakeup_test(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Сегодня", callback_data="wutest_date_today")
    builder.button(text="📅 Завтра", callback_data="wutest_date_tomorrow")
    builder.adjust(2)
    await message.answer("⏰ <b>Тест Системы Пробуждения</b>\n\nВыберите дату для проверки:", parse_mode="HTML", reply_markup=builder.as_markup())
    await state.clear()

@router.callback_query(F.data.startswith("wutest_date_"))
async def process_wakeup_test_date(callback: types.CallbackQuery, state: FSMContext):
    is_today = "today" in callback.data
    target_date = get_phuket_today() if is_today else get_phuket_today() + datetime.timedelta(days=1)
    date_str = target_date.strftime("%d.%m")
    
    await callback.answer(f"Ищу гидов на {date_str}...")
    active_guides = await sea_plan_service.get_active_land_guides([target_date])
    
    if active_guides:
        builder = InlineKeyboardBuilder()
        for uname in active_guides:
            builder.button(text=f"👤 @{uname}", callback_data=f"wutest_user_{date_str}_{uname}")
        builder.adjust(2)
        await callback.message.edit_text(f"⏰ <b>Гиды на суше ({date_str}):</b>\nВыберите гида для теста пробуждения:", parse_mode="HTML", reply_markup=builder.as_markup())
    else:
        await callback.message.edit_text(f"⏰ На {date_str} гидов на суше не найдено.")

@router.callback_query(F.data.startswith("wutest_user_"))
async def process_wakeup_test_user(callback: types.CallbackQuery):
    parts = callback.data.split("_", 3)
    date_str = parts[2]
    username = parts[3]
    target_date = datetime.datetime.strptime(f"{date_str}.{get_phuket_today().year}", "%d.%m.%Y").date()
    
    await callback.answer(f"Расчет для @{username}...")
    
    plans = await sea_plan_service.get_guide_land_plan(username, target_date)
    if not plans:
        await callback.message.answer(f"❌ План для @{username} на {date_str} не найден.")
        return
    plan = plans[0]
    guide_info = next((g for g in plan.guides if g.is_me), None)
    if not guide_info or not guide_info.pickup_time:
        await callback.message.answer(f"❌ Время пикапа для @{username} не найдено в плане.")
        return

    p_time_str = guide_info.pickup_time.strip()
    try:
        h, m = map(int, p_time_str.split(':'))
        pickup_dt = datetime.datetime.combine(target_date, datetime.time(h, m))
        wake_up_dt = pickup_dt - datetime.timedelta(hours=1)
    except Exception as e:
        await callback.message.answer(f"❌ Некорректный формат времени в плане: {p_time_str} ({e})")
        return

    status_text = "N/A (Будущая дата)"
    if target_date == get_phuket_today():
        date_norm = datetime.datetime.combine(target_date, datetime.time.min)
        async with AsyncSessionLocal() as session:
            q = select(WakeUpConfirmation).where(
                WakeUpConfirmation.guide_username == username,
                WakeUpConfirmation.date == date_norm,
                WakeUpConfirmation.pickup_time == p_time_str
            )
            res = await session.execute(q)
            conf = res.scalars().first()
            if conf:
                status_text = f"<b>{conf.status.upper()}</b> (отправлено в {conf.sent_at.strftime('%H:%M')})"
            else:
                status_text = "Ожидает отправки"

    info = (
        f"⏰ <b>Детали Пробуждения: @{username}</b>\n"
        f"📅 Дата: {date_str}\n"
        f"🏝 Программа: {plan.program}\n\n"
        f"🚐 Пикап: <b>{p_time_str}</b>\n"
        f"🔔 Подъем: <b>{wake_up_dt.strftime('%H:%M')}</b>\n"
        f"📊 Статус: {status_text}"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="👁 Предпросмотр текста", callback_data=f"wutest_action_preview_{date_str}_{username}")
    builder.button(text="📲 Тестовое мне", callback_data=f"wutest_action_send_{date_str}_{username}")
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"wutest_date_{'today' if target_date == get_phuket_today() else 'tomorrow'}"))
    builder.adjust(1)

    await callback.message.answer(info, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("wutest_action_"))
async def process_wakeup_test_action(callback: types.CallbackQuery, bot: Bot):
    parts = callback.data.split("_", 4)
    action_type = parts[2]
    date_str = parts[3]
    username = parts[4]
    
    target_date = datetime.datetime.strptime(f"{date_str}.{get_phuket_today().year}", "%d.%m.%Y").date()
    plans = await sea_plan_service.get_guide_land_plan(username, target_date)
    if not plans:
        await callback.answer("❌ План не найден.")
        return
    plan = plans[0]
    guide_info = next((g for g in plan.guides if g.is_me), None)
    if not guide_info or not guide_info.pickup_time:
        await callback.answer("❌ Информация не найдена.")
        return

    p_time_str = guide_info.pickup_time.strip()
    text, reply_markup = get_wakeup_message_data(username, p_time_str, plan.program, guide_info.pickup_location)

    if action_type == "preview":
        preview_text = f"📝 <b>ПРЕДПРОСМОТР СООБЩЕНИЯ:</b>\n\n{text}"
        await callback.message.answer(preview_text, parse_mode="HTML")
        await callback.answer("Предпросмотр показан")
    elif action_type == "send":
        async with AsyncSessionLocal() as session:
            today_norm = datetime.datetime.combine(get_phuket_now().date(), datetime.time.min)
            q = select(WakeUpConfirmation).where(
                WakeUpConfirmation.guide_username == username,
                WakeUpConfirmation.date == today_norm,
                WakeUpConfirmation.pickup_time == p_time_str
            )
            res = await session.execute(q)
            conf = res.scalars().first()
            
            if not conf:
                conf = WakeUpConfirmation(
                    guide_username=username,
                    date=today_norm,
                    pickup_time=p_time_str,
                    program_name=plan.program,
                    status="pending",
                    sent_at=get_phuket_now()
                )
                session.add(conf)
            else:
                conf.program_name = plan.program
                conf.sent_at = get_phuket_now()
                conf.status = "pending"
            await session.commit()

        await callback.message.answer("📲 <b>Отправляю тестовое сообщение тебе...</b>", parse_mode="HTML")
        await bot.send_message(
            callback.from_user.id,
            f"🧪 <b>TEST Wake-up for @{username}</b>\n\n{text}",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        await callback.answer("Сообщение отправлено")

@router.message(F.text == "🆘 Тест SOS", RoleFilter(ADMIN_ALL))
async def cmd_sos_test(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Сегодня", callback_data="sostest_date_today")
    builder.button(text="📅 Завтра", callback_data="sostest_date_tomorrow")
    builder.adjust(2)
    
    await message.answer("🆘 <b>Тест Системы SOS</b>\n\nВыберите дату для проверки:", parse_mode="HTML", reply_markup=builder.as_markup())
    await state.clear()

@router.callback_query(F.data.startswith("sostest_date_"))
async def process_sos_test_date(callback: types.CallbackQuery, state: FSMContext):
    is_today = "today" in callback.data
    target_date = get_phuket_today() if is_today else get_phuket_today() + datetime.timedelta(days=1)
    date_str = target_date.strftime("%d.%m")
    
    await callback.answer(f"Ищу всех активных гидов на {date_str}...")
    sea_guides = await sea_plan_service.get_active_sea_guides([target_date])
    land_guides = await sea_plan_service.get_active_land_guides([target_date])
    active_guides = sorted(list(set(sea_guides + land_guides)))
    
    if active_guides:
        builder = InlineKeyboardBuilder()
        for uname in active_guides:
            builder.button(text=f"👤 @{uname}", callback_data=f"sostest_user_{date_str}_{uname}")
        builder.adjust(2)
        await callback.message.edit_text(
            f"🆘 <b>Активные гиды ({date_str}):</b>\nВыберите гида для имитации SOS-запроса:",
            parse_mode="HTML", reply_markup=builder.as_markup()
        )
    else:
        await callback.message.edit_text(f"🆘 На {date_str} активных гидов не найдено.")

@router.callback_query(F.data.startswith("sostest_user_"))
async def process_sos_test_user(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 3)
    username = parts[3]
    await callback.answer(f"Запуск теста от лица @{username}...")
    await state.update_data(proxy_username=username, is_test=True)
    from handlers.help import cmd_help
    await cmd_help(callback.message, state)

# ─── Impersonation (Tester Mode) ───────────────────────────────────────────

@router.message(Command("become_user"), IsTesterFilter())
async def cmd_become_user(message: types.Message):
    """Tester: Choose a user to impersonate"""
    sheet = await google_sheets.get_current_month_sheet()
    if not sheet:
        await message.answer("❌ Не удалось загрузить расписание.")
        return

    staff, freelance = await google_sheets.parse_guides(sheet)
    all_guides = staff + freelance
    
    # Sort and remove duplicates from sheet
    unique_guide_names = sorted(list(set([g['username'].lower() for g in all_guides if g['username']])))
    
    builder = InlineKeyboardBuilder()
    
    # Add common roles for testing
    builder.row(types.InlineKeyboardButton(text="--- SYSTEM ROLES ---", callback_data="none"))
    builder.row(
        types.InlineKeyboardButton(text="👤 Admin", callback_data="imp_role_admin"),
        types.InlineKeyboardButton(text="👤 Super Admin", callback_data="imp_role_super_admin")
    )
    builder.row(
        types.InlineKeyboardButton(text="👤 Head of Guide", callback_data="imp_role_head_guide"),
        types.InlineKeyboardButton(text="👤 Hot Line", callback_data="imp_role_hotline")
    )
    
    builder.row(types.InlineKeyboardButton(text="--- GUIDES FROM SHEET ---", callback_data="none"))
    for uname in unique_guide_names:
        builder.button(text=f"👤 @{uname}", callback_data=f"imp_user_{uname}")
        
    builder.adjust(1, 2, 2, 1, 3)
    
    await message.answer(
        "🎭 <b>Режим имитации (Tester Mode)</b>\n\n"
        "Выберите пользователя или роль, которую хотите примерить.\n"
        "После выбора бот будет считать вас этим пользователем для ВСЕХ функций.",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.message(Command("exit_impersonation"))
async def cmd_exit_impersonation(message: types.Message, state: FSMContext):
    """Restore original identity"""
    redis = state.storage.redis if hasattr(state, "storage") and hasattr(state.storage, "redis") else None
    if redis:
        await redis.delete(f"impersonation:{message.from_user.id}")
        await message.answer("✅ <b>Режим имитации выключен.</b>\nВаша личность восстановлена. /start для обновления меню.", parse_mode="HTML")
    else:
        await message.answer("❌ Ошибка: Redis не доступен.")

@router.callback_query(F.data.startswith("imp_user_"), IsTesterFilter())
async def process_impersonate_user(callback: types.CallbackQuery, state: FSMContext):
    target_username = callback.data.replace("imp_user_", "")
    
    # Logic: Default to GUIDE role for impersonated guides unless specified
    imp_data = {
        "username": target_username,
        "role": UserRole.GUIDE,
        "id": 0 # Fake ID
    }
    
    redis = state.storage.redis if hasattr(state, "storage") and hasattr(state.storage, "redis") else None
    if redis:
        import json
        await redis.set(f"impersonation:{callback.from_user.id}", json.dumps(imp_data), ex=3600) # 1 hour expiry
        await callback.message.edit_text(f"✅ Теперь вы имитируете @{target_username}.\nИспользуйте /start для обновления интерфейса.")
    else:
        await callback.answer("Ошибка: Redis недоступен", show_alert=True)

@router.callback_query(F.data.startswith("imp_role_"), IsTesterFilter())
async def process_impersonate_role(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.replace("imp_role_", "")
    
    imp_data = {
        "username": f"TEST_{role.upper()}",
        "role": role,
        "id": 0
    }
    
    redis = state.storage.redis if hasattr(state, "storage") and hasattr(state.storage, "redis") else None
    if redis:
        import json
        await redis.set(f"impersonation:{callback.from_user.id}", json.dumps(imp_data), ex=3600)
        await callback.message.edit_text(f"✅ Теперь вы имитируете РОЛЬ: {role}.\nИспользуйте /start для обновления интерфейса.")
    else:
        await callback.answer("Ошибка: Redis недоступен", show_alert=True)

