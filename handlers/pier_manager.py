from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, KeyboardButton
from database.models import UserRole
from utils.permissions import RoleFilter
from services.sea_plan import sea_plan_service
from utils.time import get_phuket_now
from loguru import logger
import datetime

router = Router()

# Define roles allowed to access this dashboard
ALLOWED_ROLES = [UserRole.PIER_MANAGER, UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE]

class PierManagerStates(StatesGroup):
    waiting_for_pier = State()
    dashboard = State()

@router.message(F.text == "⚓️ Панель Пирс-Менеджера", RoleFilter(ALLOWED_ROLES))
async def cmd_pier_manager_dashboard(message: types.Message, state: FSMContext):
    logger.info(f"Pier Manager dashboard accessed by {message.from_user.id}")
    
    builder = ReplyKeyboardBuilder()
    piers = ["RPM", "Yamu", "Sarasin", "Chalong"]
    for pier in piers:
        builder.button(text=pier)
    builder.row(KeyboardButton(text="🔙 Главное меню"))
    builder.adjust(2)
    
    await state.set_state(PierManagerStates.waiting_for_pier)
    await message.answer(
        "⚓️ <b>Панель Пирс-Менеджера</b>\n\nПожалуйста, выберите пирс для работы:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@router.message(PierManagerStates.waiting_for_pier, F.text.in_(["RPM", "Yamu", "Sarasin", "Chalong"]))
async def process_pier_selection(message: types.Message, state: FSMContext):
    pier = message.text
    await state.update_data(selected_pier=pier)
    await state.set_state(PierManagerStates.dashboard)
    await show_pier_dashboard(message, pier)

async def show_pier_dashboard(message: types.Message, pier: str):
    builder = ReplyKeyboardBuilder()
    builder.button(text="⛴ Лодки сегодня")
    builder.button(text="⛴ Лодки завтра")
    builder.button(text="👤 Гиды сегодня")
    builder.button(text="👤 Гиды завтра")
    builder.button(text="🔄 Сменить пирс")
    builder.button(text="🔙 Главное меню")
    builder.adjust(2)
    
    await message.answer(
        f"⚓️ <b>Пирс: {pier}</b>\n\nВыберите нужное действие для просмотра информации из Sea Plan:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@router.message(PierManagerStates.dashboard, F.text.regexp(r"(⛴ Лодки|👤 Гиды) (сегодня|завтра)"))
async def process_pier_action(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier")
    if not pier:
        await cmd_pier_manager_dashboard(message, state)
        return

    text = message.text
    is_boats = "Лодки" in text
    is_today = "сегодня" in text
    
    target_date = get_phuket_now().date()
    if not is_today:
        target_date += datetime.timedelta(days=1)
    
    date_str = target_date.strftime("%d.%m.%Y")
    await message.answer(f"⏳ Загружаю данные из Google Таблицы на {date_str}...")
    
    plans = await sea_plan_service.get_pier_detailed_plan(pier, target_date)
    
    if not plans:
        await message.answer(f"❌ Данных для пирса <b>{pier}</b> на <b>{date_str}</b> не найдено.", parse_mode="HTML")
        return

    if is_boats:
        report = f"⛴ <b>Лодки на пирсе {pier} ({date_str}):</b>\n\n"
        for p in sorted(plans, key=lambda x: x.boat):
            progs = ", ".join([prog.name for prog in p.programs])
            pax = p.pax_string
            guides = ", ".join([g.full_info for g in p.guides])
            report += f"🚢 <b>{p.boat}</b>\n"
            report += f"📝 Программы: {progs}\n"
            report += f"👥 PAX: <code>{pax}</code>\n"
            report += f"👤 Гиды: {guides}\n"
            if p.thai_guide:
                report += f"🇹🇭 Тай. гид: {p.thai_guide}\n"
            report += "──────────────────\n"
    else:
        report = f"👤 <b>Гиды на пирсе {pier} ({date_str}):</b>\n\n"
        unique_guides = {}
        for p in plans:
            for g in p.guides:
                if g.full_info not in unique_guides:
                    unique_guides[g.full_info] = []
                unique_guides[g.full_info].append(p.boat)
        
        if not unique_guides:
            report += "Гиды не найдены."
        else:
            for guide, boats in sorted(unique_guides.items()):
                boats_str = ", ".join(boats)
                report += f"👤 {guide}\n🚢 Лодки: {boats_str}\n\n"

    # Split report if too long
    if len(report) > 4000:
        for x in range(0, len(report), 4000):
            await message.answer(report[x:x+4000], parse_mode="HTML")
    else:
        await message.answer(report, parse_mode="HTML")

@router.message(PierManagerStates.dashboard, F.text == "🔄 Сменить пирс")
async def cmd_change_pier(message: types.Message, state: FSMContext):
    await cmd_pier_manager_dashboard(message, state)

@router.message(F.text == "🔙 Главное меню", RoleFilter(ALLOWED_ROLES))
async def back_to_main_menu_pier(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.common import cmd_start
    await cmd_start(message)

# Fallback for Back button if text is just "🔙 Назад"
@router.message(F.text == "🔙 Назад", RoleFilter(ALLOWED_ROLES))
async def back_to_main_fallback(message: types.Message, state: FSMContext):
    await back_to_main_menu_pier(message, state)
