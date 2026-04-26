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
import re

router = Router()

# Define roles allowed to access this dashboard
ALLOWED_ROLES = [UserRole.PIER_MANAGER, UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.HEAD_OF_GUIDE]

PIERS = ["RPM", "Yamu", "Sarasin", "Chalong"]

# Maps lowercased program-name substrings → list of NP codes
# Order matters: more specific first
NP_PROGRAM_MAP: list[tuple[str, list[str]]] = [
    ("pp bamboo",         ["PP"]),
    ("pp ovn",            ["PP"]),
    ("pp sunrise",        ["PP"]),
    ("11 island",         ["PP", "JB", "HG"]),
    ("11 остров",         ["PP", "JB", "HG"]),
    ("4 pearl",           ["PP", "JB"]),
    ("4 жемчуж",          ["PP", "JB"]),
    ("5 pearl",           ["PP", "JB", "HG"]),
    ("5 жемчуж",          ["PP", "JB", "HG"]),
    ("krabi tropical",    ["HG"]),
    ("phi phi",           ["PP"]),
    ("james bond",        ["JB"]),
    ("phang nga",         ["JB"]),
    ("hong island",       ["HG"]),
    ("hong",              ["HG"]),
    ("4 island",          ["PP"]),
]

# NP fees
NP_FEES = {
    "PP": {"emoji": "🏝", "name": "Phi Phi (PP)",  "adult": 350, "child": 200, "parking": 100, "note": "400 для приватных"},
    "JB": {"emoji": "🗿", "name": "James Bond (JB)","adult": 300, "child": 150, "parking": 100, "note": None},
    "HG": {"emoji": "🌊", "name": "Hong Island (HG)","adult": 300, "child": 150, "parking": None, "note": "Без парковки"},
}

class PierManagerStates(StatesGroup):
    waiting_for_pier = State()
    dashboard = State()
    pier_ops = State()

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

@router.message(F.text == "⚓️ Панель Пирс-Менеджера", RoleFilter(ALLOWED_ROLES))
async def cmd_pier_manager_dashboard(message: types.Message, state: FSMContext):
    logger.info(f"Pier Manager dashboard accessed by {message.from_user.id}")

    builder = ReplyKeyboardBuilder()
    for pier in PIERS:
        builder.button(text=pier)
    builder.row(KeyboardButton(text="🔙 Главное меню"))
    builder.adjust(2)

    await state.set_state(PierManagerStates.waiting_for_pier)
    await message.answer(
        "⚓️ <b>Панель Пирс-Менеджера</b>\n\nПожалуйста, выберите пирс для работы:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# ─────────────────────────────────────────────────────────────────────────────
# PIER SELECTION → MAIN PIER DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.waiting_for_pier, F.text.in_(PIERS))
async def process_pier_selection(message: types.Message, state: FSMContext):
    pier = message.text
    await state.update_data(selected_pier=pier)
    await state.set_state(PierManagerStates.dashboard)
    await show_pier_dashboard(message, pier)


async def show_pier_dashboard(message: types.Message, pier: str):
    """Main dashboard for a selected pier — info + open pier button."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=f"🚪 Открыть пирс {pier}")
    builder.button(text="⛴ Лодки сегодня")
    builder.button(text="⛴ Лодки завтра")
    builder.button(text="👤 Гиды сегодня")
    builder.button(text="👤 Гиды завтра")
    builder.button(text="🔄 Сменить пирс")
    builder.button(text="🔙 Главное меню")
    builder.adjust(1, 2, 2, 2)

    await message.answer(
        f"⚓️ <b>Пирс: {pier}</b>\n\nВыберите нужное действие:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# ─────────────────────────────────────────────────────────────────────────────
# BOATS / GUIDES INFO (existing logic)
# ─────────────────────────────────────────────────────────────────────────────

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

    for x in range(0, len(report), 4000):
        await message.answer(report[x:x+4000], parse_mode="HTML")

# ─────────────────────────────────────────────────────────────────────────────
# OPEN PIER → OPERATIONS PANEL
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.dashboard, F.text.regexp(r"^🚪 Открыть пирс (.+)$"))
async def open_pier_ops(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier")
    if not pier:
        await cmd_pier_manager_dashboard(message, state)
        return

    await state.set_state(PierManagerStates.pier_ops)
    await show_pier_ops_menu(message, pier)


async def show_pier_ops_menu(message: types.Message, pier: str):
    builder = ReplyKeyboardBuilder()
    builder.button(text="💰 Открыть кассу")
    builder.button(text="🏞 Нац. парки")
    builder.button(text="📊 Итоги дня")
    builder.button(text="⛴ Лодки сегодня")
    builder.button(text="👤 Гиды сегодня")
    builder.button(text="🔙 К выбору пирса")
    builder.adjust(2, 1, 2, 1)

    now = get_phuket_now()
    await message.answer(
        f"🚪 <b>Пирс {pier} открыт</b>\n"
        f"📅 {now.strftime('%d.%m.%Y')}  🕐 {now.strftime('%H:%M')}\n\n"
        f"Выберите действие:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# ─────────────────────────────────────────────────────────────────────────────
# OPS: 💰 Открыть кассу
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.pier_ops, F.text == "💰 Открыть кассу")
async def ops_open_cash(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier", "—")
    now = get_phuket_now()
    manager_name = message.from_user.full_name or message.from_user.username or "Неизвестно"

    text = (
        f"💰 <b>Касса открыта</b>\n"
        f"──────────────────\n"
        f"⚓️ Пирс: <b>{pier}</b>\n"
        f"📅 Дата: <b>{now.strftime('%d.%m.%Y')}</b>\n"
        f"🕐 Время открытия: <b>{now.strftime('%H:%M')}</b>\n"
        f"👤 Менеджер: <b>{manager_name}</b>\n"
        f"──────────────────\n"
        f"✅ Зафиксировано. Хорошей смены!"
    )

    logger.info(f"Pier {pier} cash opened by {message.from_user.id} ({manager_name}) at {now.strftime('%H:%M')}")
    await message.answer(text, parse_mode="HTML")

# ─────────────────────────────────────────────────────────────────────────────
# OPS: 🏞 Нац. парки
# ─────────────────────────────────────────────────────────────────────────────

def _detect_nps(program_name: str) -> list[str]:
    """Returns list of NP codes for the given program name (may be multiple)."""
    lower = program_name.lower()
    for keyword, codes in NP_PROGRAM_MAP:
        if keyword in lower:
            return codes
    return []


def _np_fee_line(code: str) -> str:
    f = NP_FEES[code]
    parts = [f"{f['emoji']} {f['name']}: взр. {f['adult']}฿ / реб. {f['child']}฿"]
    if f["parking"]:
        parts.append(f"парковка {f['parking']}฿")
    if f["note"]:
        parts.append(f"({f['note']})")
    return "  " + " · ".join(parts)


@router.message(PierManagerStates.pier_ops, F.text == "🏞 Нац. парки")
async def ops_nat_parks(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier", "—")
    target_date = get_phuket_now().date()
    date_str = target_date.strftime("%d.%m.%Y")

    await message.answer(f"⏳ Проверяю нац. парки для пирса <b>{pier}</b> на {date_str}...", parse_mode="HTML")

    plans = await sea_plan_service.get_pier_detailed_plan(pier, target_date)

    if not plans:
        await message.answer(f"❌ Данных для пирса <b>{pier}</b> на <b>{date_str}</b> не найдено.", parse_mode="HTML")
        return

    # Collect: np_code → list of program entries
    # Each program can have multiple NP codes
    np_entries: dict[str, list] = {"PP": [], "JB": [], "HG": []}

    for plan in plans:
        for prog in plan.programs:
            codes = _detect_nps(prog.name)
            for code in codes:
                if code in np_entries:
                    np_entries[code].append({
                        "boat": plan.boat,
                        "program": prog.name,
                        "pax": prog.pax,
                        "guide": prog.guide,
                    })

    has_any = any(np_entries[k] for k in np_entries)
    if not has_any:
        await message.answer(
            f"🏞 <b>Нац. парки — {pier} ({date_str})</b>\n\n"
            "Программ с нац. парками не обнаружено.",
            parse_mode="HTML"
        )
        return

    report = f"🏞 <b>Нац. парки — {pier} ({date_str})</b>\n\n"
    total_np_pax = 0

    for code in ["PP", "JB", "HG"]:
        entries = np_entries[code]
        if not entries:
            continue
        f = NP_FEES[code]
        report += f"<b>{f['emoji']} {f['name']}</b>\n"
        report += f"{_np_fee_line(code)}\n"
        for e in entries:
            pax_total = _sum_pax(e['pax'])
            total_np_pax += pax_total
            report += f"  🚢 {e['boat']} — {e['program']}\n"
            report += f"     👥 PAX: <code>{e['pax']}</code> ({pax_total} чел.)\n"
            if e['guide']:
                report += f"     👤 Гид: {e['guide']}\n"
        report += "\n"

    report += "──────────────────\n"
    report += f"🎫 Итого туристов с нац. парками: <b>{total_np_pax}</b>"

    await message.answer(report, parse_mode="HTML")

# ─────────────────────────────────────────────────────────────────────────────
# OPS: 📊 Итоги дня
# ─────────────────────────────────────────────────────────────────────────────

def _sum_pax(pax_str: str) -> int:
    """Sums A/C/I pax string. Returns 0 on error."""
    try:
        if "/" in pax_str:
            parts = pax_str.split("/")
            return sum(int(p.strip()) for p in parts if p.strip().isdigit())
        elif pax_str.strip().isdigit():
            return int(pax_str.strip())
    except Exception:
        pass
    return 0


@router.message(PierManagerStates.pier_ops, F.text == "📊 Итоги дня")
async def ops_daily_summary(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier", "—")
    target_date = get_phuket_now().date()
    date_str = target_date.strftime("%d.%m.%Y")

    await message.answer(f"⏳ Собираю итоги для пирса <b>{pier}</b>...", parse_mode="HTML")

    plans = await sea_plan_service.get_pier_detailed_plan(pier, target_date)

    if not plans:
        await message.answer(f"❌ Данных для пирса <b>{pier}</b> на <b>{date_str}</b> не найдено.", parse_mode="HTML")
        return

    total_a, total_c, total_i = 0, 0, 0
    total_boats = len(plans)
    boats_lines = []

    for plan in sorted(plans, key=lambda x: x.boat):
        pa, pc, pi = 0, 0, 0
        try:
            parts = plan.pax_string.split("/")
            pa = int(parts[0]) if parts[0].isdigit() else 0
            pc = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            pi = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        except Exception:
            pass
        total_a += pa
        total_c += pc
        total_i += pi
        boat_total = pa + pc + pi
        boats_lines.append(f"  🚢 {plan.boat}: <code>{plan.pax_string}</code> ({boat_total} чел.)")

    grand_total = total_a + total_c + total_i

    report = (
        f"📊 <b>Итоги дня — {pier} ({date_str})</b>\n"
        f"──────────────────\n"
    )
    report += "\n".join(boats_lines) + "\n"
    report += (
        f"──────────────────\n"
        f"🚢 Лодок: <b>{total_boats}</b>\n"
        f"👥 PAX:  A=<b>{total_a}</b>  C=<b>{total_c}</b>  I=<b>{total_i}</b>\n"
        f"🎯 Всего туристов: <b>{grand_total}</b>"
    )

    await message.answer(report, parse_mode="HTML")

# ─────────────────────────────────────────────────────────────────────────────
# OPS: ⛴ Лодки / 👤 Гиды сегодня (inside pier_ops state)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.pier_ops, F.text.in_(["⛴ Лодки сегодня", "👤 Гиды сегодня"]))
async def ops_boats_or_guides(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier", "—")
    target_date = get_phuket_now().date()
    date_str = target_date.strftime("%d.%m.%Y")
    is_boats = "Лодки" in message.text

    await message.answer(f"⏳ Загружаю данные из Google Таблицы на {date_str}...")

    plans = await sea_plan_service.get_pier_detailed_plan(pier, target_date)

    if not plans:
        await message.answer(f"❌ Данных для пирса <b>{pier}</b> на <b>{date_str}</b> не найдено.", parse_mode="HTML")
        return

    if is_boats:
        report = f"⛴ <b>Лодки на пирсе {pier} ({date_str}):</b>\n\n"
        for p in sorted(plans, key=lambda x: x.boat):
            progs = ", ".join([prog.name for prog in p.programs])
            guides = ", ".join([g.full_info for g in p.guides])
            report += f"🚢 <b>{p.boat}</b>\n"
            report += f"📝 Программы: {progs}\n"
            report += f"👥 PAX: <code>{p.pax_string}</code>\n"
            report += f"👤 Гиды: {guides}\n"
            if p.thai_guide:
                report += f"🇹🇭 Тай. гид: {p.thai_guide}\n"
            report += "──────────────────\n"
    else:
        report = f"👤 <b>Гиды на пирсе {pier} ({date_str}):</b>\n\n"
        unique_guides: dict[str, list] = {}
        for p in plans:
            for g in p.guides:
                if g.full_info not in unique_guides:
                    unique_guides[g.full_info] = []
                unique_guides[g.full_info].append(p.boat)
        if not unique_guides:
            report += "Гиды не найдены."
        else:
            for guide, boats in sorted(unique_guides.items()):
                report += f"👤 {guide}\n🚢 Лодки: {', '.join(boats)}\n\n"

    for x in range(0, len(report), 4000):
        await message.answer(report[x:x+4000], parse_mode="HTML")

# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────

@router.message(PierManagerStates.dashboard, F.text == "🔄 Сменить пирс")
async def cmd_change_pier(message: types.Message, state: FSMContext):
    await cmd_pier_manager_dashboard(message, state)


@router.message(PierManagerStates.pier_ops, F.text == "🔙 К выбору пирса")
async def ops_back_to_pier_select(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pier = data.get("selected_pier", "—")
    await state.set_state(PierManagerStates.dashboard)
    await show_pier_dashboard(message, pier)


@router.message(F.text == "🔙 Главное меню", RoleFilter(ALLOWED_ROLES))
async def back_to_main_menu_pier(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.common import cmd_start
    await cmd_start(message)
