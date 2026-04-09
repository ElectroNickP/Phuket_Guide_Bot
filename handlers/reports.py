from aiogram import Router, types, F
from aiogram.filters import Command
from datetime import datetime, date
from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import ReportSubmission, UserRole
from services.sea_plan import sea_plan_service
from config import config
from utils.time import get_phuket_now
from loguru import logger

router = Router()

@router.message(Command("reports"))
async def cmd_check_reports(message: types.Message):
    # Check if message is in the report group and topic
    if message.chat.id != config.REPORT_GROUP_ID:
        return # Silent ignore if not in group
        
    if message.message_thread_id not in [config.REPORT_START_TOPIC_ID, config.REPORT_FINISH_TOPIC_ID]:
        # Optional: could respond, but user specifically asked for "in this topic"
        return

    today = get_phuket_now().date()
    
    try:
        # 1. Get expected reports
        expected = await sea_plan_service.get_expected_reports(today)
        if not expected:
            await message.answer(f"📭 На сегодня ({today.strftime('%d.%m')}) программ не найдено.")
            return

        # 2. Get submitted reports from DB
        # We look for submissions today (timestamp >= start of day)
        from utils.time import PHUKET_TZ
        start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=PHUKET_TZ)
        
        async with AsyncSessionLocal() as session:
            query = select(ReportSubmission).where(
                ReportSubmission.timestamp >= start_of_day
            )
            result = await session.execute(query)
            submissions = result.scalars().all()
            
        submitted_data = {} # (username, program_name_lower) -> {"start": status, "finish": status}
        for s in submissions:
            uname = s.guide_username.lower()
            prog_lower = s.program_name.lower()
            rtype = s.report_type or "start" # Handle legacy
            
            if (uname, prog_lower) not in submitted_data:
                submitted_data[(uname, prog_lower)] = {}
            submitted_data[(uname, prog_lower)][rtype] = s.status

        # 3. Correlate and Group
        sea_lines = []
        land_lines = []
        
        unique_expected = set(expected)
        sorted_expected = sorted(list(unique_expected), key=lambda x: x[0])
        
        for uname, prog, category in sorted_expected:
            prog_lower = prog.lower()
            key = (uname, prog_lower)
            
            start_icon = "❌"
            finish_icon = "❌"
            
            if key in submitted_data:
                statuses = submitted_data[key]
                if "start" in statuses:
                    start_icon = "🚀✅" if statuses["start"] == "ok" else "🚀⚠️"
                if "finish" in statuses:
                    finish_icon = "🏁✅" if statuses["finish"] == "ok" else "🏁⚠️"
            
            line = f"{start_icon}{finish_icon} @{uname} — <i>{prog}</i>"
            if category == "SEA":
                sea_lines.append(line)
            else:
                land_lines.append(line)

        response = f"📊 <b>Статус отчетов на {today.strftime('%d.%m')}</b>\n"
        response += "🚀=Старт, 🏁=Финиш\n"
        
        if sea_lines:
            response += f"\n🌊 <b>МОРЕ:</b>\n" + "\n".join(sea_lines) + "\n"
            
        if land_lines:
            response += f"\n🚐 <b>СУША:</b>\n" + "\n".join(land_lines) + "\n"

        # Count unique start/finish pairs vs expected
        total_starts = sum(1 for v in submitted_data.values() if "start" in v)
        total_finishes = sum(1 for v in submitted_data.values() if "finish" in v)
        
        response += f"\nОтправлено: С:{total_starts} Ф:{total_finishes} из {len(unique_expected)}"
        
        await message.answer(response, parse_mode="HTML")

    except Exception as e:
        logger.exception(f"Error checking reports: {e}")
        await message.answer(f"❌ Ошибка при проверке отчетов: {e}")
