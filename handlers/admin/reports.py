import datetime
import html
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import AsyncSessionLocal
from database.models import User, AppSettings, ReportSubmission
from config import config
from sqlalchemy import select, func, desc

from services.scheduler import get_phuket_now, get_phuket_today
from utils.permissions import RoleFilter
from .base import ADMIN_ALL, ADMIN_MANAGEMENT, IsAdminFilter

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

class AdminReportStates(StatesGroup):
    waiting_for_username = State()
    waiting_for_report_type = State()

@router.message(F.text == "📝 Отчет за гида", RoleFilter(ADMIN_MANAGEMENT))
async def cmd_admin_report_proxy(message: types.Message, state: FSMContext):
    await message.answer("👥 Введите <b>@username</b> гида, за которого нужно сдать отчет:", parse_mode="HTML")
    await state.set_state(AdminReportStates.waiting_for_username)

@router.message(AdminReportStates.waiting_for_username)
async def process_admin_report_username(message: types.Message, state: FSMContext):
    username = message.text.strip().replace("@", "")
    await state.update_data(proxy_username=username)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Начать программу", callback_data="admin_report_type_start")
    builder.button(text="🏁 Завершить программу", callback_data="admin_report_type_finish")
    builder.adjust(1)
    
    await message.answer(
        f"👤 Вы сдаете отчет за <b>@{username}</b>.\nВыберите тип отчета:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await state.set_state(AdminReportStates.waiting_for_report_type)

@router.callback_query(F.data.startswith("admin_report_type_"), AdminReportStates.waiting_for_report_type)
async def process_admin_report_type_select(callback: types.CallbackQuery, state: FSMContext, **data):
    rtype = callback.data.replace("admin_report_type_", "")
    is_end = (rtype == "finish")
    await state.update_data(is_end_report=is_end)
    
    await callback.message.edit_reply_markup(reply_markup=None)
    
    from handlers.guide import _initiate_report_filling, get_phuket_now
    target_date = get_phuket_now().date()
    
    await callback.message.answer(f"📝 Выбран тип: {'Завершение' if is_end else 'Начало'} программы.")
    await _initiate_report_filling(callback.message, state, target_date, **data)
    await callback.answer()

@router.message(F.text == "📊 Статистика", RoleFilter(ADMIN_ALL))
async def cmd_stats_kb(message: types.Message):
    async with AsyncSessionLocal() as session:
        query_total = select(func.count(User.id))
        res_total = await session.execute(query_total)
        total_users = res_total.scalar()
        
        day_ago = get_phuket_now() - datetime.timedelta(days=1)
        query_active = select(func.count(User.id)).where(User.last_contact >= day_ago)
        res_active = await session.execute(query_active)
        active_24h = res_active.scalar()
        
        today_start = datetime.datetime.combine(get_phuket_today(), datetime.time.min)
        query_reports = select(ReportSubmission.report_type, func.count(ReportSubmission.id))\
            .where(ReportSubmission.date >= today_start)\
            .group_by(ReportSubmission.report_type)
        res_reports = await session.execute(query_reports)
        reports_summary = {r[0]: r[1] for r in res_reports.all()}
        
        starts = reports_summary.get("start", 0)
        finishes = reports_summary.get("finish", 0)
        
        query_users = select(User).order_by(desc(User.last_contact)).limit(15)
        result_users = await session.execute(query_users)
        users = result_users.scalars().all()
        
        query_int = select(AppSettings).where(AppSettings.key == "polling_interval")
        res_int = await session.execute(query_int)
        setting_int = res_int.scalar_one_or_none()
        current_interval = int(setting_int.value) if setting_int else config.POLLING_INTERVAL
        
        user_list_str = ""
        for u in users:
            last_contact_str = u.last_contact.strftime("%d.%m %H:%M") if u.last_contact else "---"
            last_act = u.last_action or "---"
            if len(last_act) > 30: last_act = last_act[:27] + "..."
            
            phuket_now_naive = get_phuket_now().replace(tzinfo=None)
            status_icon = "🟢" if u.last_contact and u.last_contact >= (phuket_now_naive - datetime.timedelta(minutes=30)) else "⚪️"
            
            user_list_str += (
                f"{status_icon} <b>@{u.username or u.telegram_id}</b>\n"
                f"  🕒 {last_contact_str} | ⚙️ <code>{html.escape(last_act)}</code>\n"
                f"  📈 Reps: 🚀{u.count_start or 0} | 🏁{u.count_finish or 0} | 👤{u.count_status or 0}\n\n"
            )

    response = (
        f"📊 <b>СИСТЕМНАЯ СТАТИСТИКА</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"🔥 Активны (24ч): <b>{active_24h}</b>\n"
        f"⏱ Опрос таблицы: <b>{current_interval // 60} мин.</b>\n\n"
        f"📅 <b>ОТЧЕТЫ СЕГОДНЯ:</b>\n"
        f"🚀 Начали: <b>{starts}</b>\n"
        f"🏁 Завершили: <b>{finishes}</b>\n\n"
        f"🕒 <b>ПОСЛЕДНЯЯ АКТИВНОСТЬ (TOP 15):</b>\n\n"
        f"{user_list_str if user_list_str else 'Данных нет.'}"
    )
    
    await message.answer(response, parse_mode="HTML")
