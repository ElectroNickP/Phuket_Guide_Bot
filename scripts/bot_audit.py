import asyncio
import datetime
import sys
import os
import re
import gspread
from loguru import logger
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import config
from database.db import init_db
from database.dto import SeaPlanDTO, LandPlanDTO, GuestDTO, GuideDTO, ProgramDTO

# ─── Configuration for Audit ──────────────────────────────────────────────────
REPORT_SPREADSHEET_ID = "1KgXnPnwV4gkh8f0cdr4-Aqu6yPNDaehTl836MZwT_8I" 

class BotSimulator:
    """Simulates bot responses based on pre-fetched and cached data"""
    
    @staticmethod
    def format_schedule(guide_name: str, username: str, date_str: str, schedule_val: str):
        display_val = schedule_val if schedule_val else "Свободен"
        return (
            f"📅 <b>Расписание: @{username}</b>\n\n"
            f"Дата: <b>{date_str}</b>\n"
            f"Занятость: <b>{display_val}</b>"
        )

    @staticmethod
    def format_sea_plan(plans: List[SeaPlanDTO], username: str, date_str: str):
        if not plans:
            return f"❌ План на море на {date_str} для @{username} не найден."

        response = f"🌊 <b>План на море ({date_str})</b>\n\n"
        for plan in plans:
            response += f"🚢 <b>Лодка:</b> {plan.boat}\n"
            response += f"⚓️ <b>Пирс:</b> {plan.pier or '---'}\n"
            response += f"👤 <b>Thai Guide:</b> {plan.thai_guide or '---'}\n"
            response += f"👥 <b>Гид(ы):</b> {', '.join([g.full_info for g in plan.guides])}\n"
            response += f"📝 <b>Программы:</b>\n"
            for prog in plan.programs:
                prog_text = f"{prog.name} ({prog.pax} pax)"
                if len(plan.guides) > 1 and prog.guide:
                    response += f"  • {prog_text} - {prog.short_guide}\n"
                else:
                    response += f"  • {prog_text}\n"
            response += f"📊 <b>Total Pax:</b> {plan.total_pax}\n\n"
        return response

    @staticmethod
    def format_land_plan(plans: List[LandPlanDTO], username: str, date_str: str):
        if not plans:
            return f"🚐 <b>План на суше ({date_str})</b>\n\nНа этот день ваших заказов не найдено."

        full_response = ""
        for plan in plans:
            response = f"🚐 <b>Job Order: {plan.program}</b>\n"
            response += f"📅 <b>Date:</b> {plan.date}\n\n"
            if plan.guides:
                response += "👤 <b>Guide(s):</b>\n"
                for g in plan.guides:
                    me_tag = " (ВЫ)" if g.is_me else ""
                    response += f"  • {g.full_info}{me_tag} (P/U: {g.pickup_time} @ {g.pickup_location})\n"
                response += "\n"
            if plan.bus:
                response += f"🚌 <b>Bus:</b> <code>{plan.bus}</code>\n"
            if plan.driver:
                response += f"👨‍✈️ <b>Driver:</b> {plan.driver}\n"
            if plan.guests:
                response += "\n👥 <b>Guest List:</b>\n\n"
                for g in plan.guests:
                    response += f"  • <b>V/C:</b> <code>{g.voucher}</code> | <b>Pax:</b> {g.pax}\n"
                    response += f"    <b>Pickup:</b> {g.pickup}\n"
                    response += f"    <b>Hotel:</b> {g.hotel} ({g.area}) (RM: {g.room})\n"
                    response += f"    <b>Name:</b> <code>{g.name}</code>\n"
                    if g.phone and g.phone != "-":
                        response += f"    <b>Phone:</b> <code>{g.phone}</code>\n"
                    if g.remarks and g.remarks != "-":
                        response += f"    <b>Remarks:</b> {g.remarks}\n"
                    response += f"    💰 <b>COT:</b> <code>{g.cot}</code>\n"
                    response += "\n"
            full_response += response + "\n" + "="*30 + "\n\n"
        return full_response

    @staticmethod
    def format_guest_list(guest_list: List[GuestDTO], date_str: str):
        if not guest_list:
            return f"📋 Список гостей пуст или не найден."

        response = f"📋 <b>Список гостей ({date_str})</b>:\n\n"
        grouped_guests = {}
        for g in guest_list:
            if g.program not in grouped_guests:
                grouped_guests[g.program] = []
            grouped_guests[g.program].append(g)

        for pname, guests in grouped_guests.items():
            response += f"🔹 <b>Program: {pname}</b>\n"
            for g in guests:
                response += f"  • <b>V/C:</b> <code>{g.voucher}</code> | <b>Pax:</b> {g.pax}\n"
                if g.pickup:
                    response += f"    <b>Pickup:</b> {g.pickup}\n"
                response += f"    <b>Hotel:</b> {g.hotel} (RM: {g.room})\n"
                response += f"    <b>Name:</b> <code>{g.name}</code>\n"
                if g.phone and g.phone != "-":
                    response += f"    <b>Phone:</b> <code>{g.phone}</code>\n"
                if g.remarks and g.remarks != "-":
                    response += f"    <b>Remarks:</b> {g.remarks}\n"
                response += f"    💰 <b>COT:</b> <code>{g.cot}</code>\n"
                response += "\n"
        return response

class FastPlanParser:
    """Highly optimized parser that works on in-memory data to avoid 429 errors"""
    
    def __init__(self, raw_data: List[List[str]]):
        self.data = raw_data

    def get_sea_plan(self, username: str, date_str: str) -> List[SeaPlanDTO]:
        boats_data = {}
        current_boat = None
        current_pier = None
        current_thai_guide = None
        
        for i, row in enumerate(self.data):
            if i > 250 and len(row) > 4:
                row_prog_raw = row[4].strip()
                if row_prog_raw == "TOTAL" or row_prog_raw.startswith("JOB ORDER"):
                    break

            if len(row) < 16: continue
            
            row_boat = row[15].strip()
            row_pier = row[13].strip()
            row_thai = row[1].strip()
            row_date = row[0].strip() or date_str

            if "COMEBACK BOATS" in row[4].strip().upper(): continue

            if row_boat:
                current_boat = row_boat
                current_pier = row_pier
                current_thai_guide = row_thai
            
            if not current_boat: continue
                
            guide_str = row[7].strip()
            prog_name = row[4].strip()
            pax_str = row[5].strip()

            if not prog_name and not guide_str: continue

            boat_key = f"{current_pier}_{current_boat}"
            if boat_key not in boats_data:
                boats_data[boat_key] = SeaPlanDTO(
                    boat=current_boat, pier=current_pier, date=row_date,
                    thai_guide=current_thai_guide, programs=[], guides=[],
                    total_pax=0, is_assigned=False
                )
            
            dto = boats_data[boat_key]
            if prog_name:
                pax_val = 0
                try: pax_val = int(pax_str)
                except: pass
                
                short_guide = guide_str
                match_uname = re.search(r'(@\w+)', guide_str)
                if match_uname: short_guide = match_uname.group(1)

                dto.programs.append(ProgramDTO(name=prog_name, pax=pax_str, guide=guide_str, short_guide=short_guide))
                dto.total_pax += pax_val

            if guide_str:
                matches = re.findall(r'@(\w+)', guide_str)
                is_me = any(uname.lower() == username.lower() for uname in matches)
                if is_me: dto.is_assigned = True
                if not any(g.full_info == guide_str for g in dto.guides):
                    dto.guides.append(GuideDTO(full_info=guide_str, is_me=is_me))

        return [dto for dto in boats_data.values() if dto.is_assigned]

    def get_land_plan(self, username: str, date_str: str) -> List[LandPlanDTO]:
        land_start = -1
        for i, row in enumerate(self.data):
            row_str = " ".join([str(v) for v in row if v])
            if 'JOB ORDER - LAND JOINED TOURS' in row_str:
                land_start = i
                break
        
        if land_start == -1: return []

        blocks = []
        current_block = None
        username_lower = username.lower()
        
        for i in range(land_start + 1, len(self.data)):
            row = self.data[i]
            if row and row[0] and date_str not in row[0]:
                if i > land_start + 50: break

            row_str = " ".join([str(v) for v in row if v]).upper()
            if i > land_start + 5 and ('TOTAL' in row_str or 'JOB ORDER - PRIVATE' in row_str): break

            if len(row) < 16: continue
            
            col1, col2, col3, col4, col7 = row[1].strip(), row[2].strip(), row[3].strip(), row[4].strip(), row[7].strip()
            
            is_header = False
            if col4 and (re.search(r' b\d+', col4, re.IGNORECASE) or re.search(r'Bus \d+', col4, re.IGNORECASE)): is_header = True
            elif col3 and (re.search(r' b\d+', col3, re.IGNORECASE) or re.search(r'Bus \d+', col3, re.IGNORECASE)) and not col7: is_header = True
                
            if is_header and not ('@' in col1):
                if current_block: blocks.append(current_block)
                current_block = LandPlanDTO(program=col4, date=date_str, guides=[], guests=[], is_assigned=False)
                continue
            
            if not current_block: continue

            if '@' in col1:
                is_me = False
                uname_match = re.search(r'@(\w+)', col1)
                if uname_match and uname_match.group(1).lower() == username_lower:
                    is_me = True
                    current_block.is_assigned = True
                
                pu_time = col3.split(' ')[0] if ' ' in col3 else col3
                current_block.guides.append(GuideDTO(full_info=col1, short_name=col7, pickup_time=pu_time, pickup_location=col4, is_me=is_me))
                continue

            if 'Bus' in col3 or (col2 and 'Bus' in col2):
                current_block.bus = col3 if 'Bus' in col3 else col2
                current_block.driver = col7
                continue

            if col7: # Guest entry
                try:
                    pax_a = int(row[9]) if row[9].isdigit() else 0
                    pax_c = int(row[10]) if row[10].isdigit() else 0
                    pax_i = int(row[11]) if row[11].isdigit() else 0
                    if (pax_a + pax_c + pax_i) == 0: continue
                except: continue

                current_block.guests.append(GuestDTO(
                    voucher=col2 or "N/A", pickup=col3, hotel=col4, 
                    area=row[5].strip() if len(row) > 5 else "-",
                    room=row[6].strip() or "-", name=col7, phone=row[8].strip() or "-",
                    pax=f"{pax_a}/{pax_c}/{pax_i}", cot=row[14].strip() if len(row) > 14 else "0",
                    remarks=row[15].strip() if len(row) > 15 else "-"
                ))

        if current_block: blocks.append(current_block)
        return [b for b in blocks if b.is_assigned]

    def get_guest_list(self, program_names: list[str], yesterday_data: List[List[str]] = None) -> List[GuestDTO]:
        guests = []
        comeback_markers = ["COMEBACK", "ВЫВОЗ", "RETURN"]
        
        standard_progs_lower = set()
        comeback_mapping_lower = {} # cleaned_lower -> original

        for p in program_names:
            is_comeback = False
            for marker in comeback_markers:
                if marker.upper() in p.upper():
                    cleaned = re.sub(rf'(?i)\b({marker})\b', '', p, flags=re.IGNORECASE).strip()
                    cleaned = re.sub(r'^[\s\-\:]+', '', cleaned).strip()
                    comeback_mapping_lower[cleaned.lower()] = p
                    is_comeback = True
                    break
            if not is_comeback:
                standard_progs_lower.add(p.lower())

        # 1. Standard (Today)
        for r in self.data:
            if len(r) < 14: continue
            program_str = r[13].strip()
            if program_str and program_str.lower() in standard_progs_lower:
                guests.append(self._parse_guest_row(r))

        # 2. Comeback (Yesterday)
        if comeback_mapping_lower and yesterday_data:
            for r in yesterday_data:
                if len(r) < 14: continue
                program_str = r[13].strip()
                prog_lower = program_str.lower()
                
                matched_orig = None
                for cleaned_lower, orig in comeback_mapping_lower.items():
                    if prog_lower == cleaned_lower or prog_lower.startswith(cleaned_lower + " "):
                        matched_orig = orig
                        break
                
                if matched_orig:
                    g = self._parse_guest_row(r)
                    g.program = matched_orig
                    guests.append(g)
        return guests

    def _parse_guest_row(self, r: list) -> GuestDTO:
        return GuestDTO(
            program=r[13].strip(), agent=r[1].strip(), voucher=r[2].strip(),
            pickup=r[3].strip(), hotel=r[4].strip(), room=r[6].strip(),
            name=r[7].strip(), phone=r[8].strip(),
            pax=f"{r[9].strip() or '0'}/{r[10].strip() or '0'}/{r[11].strip() or '0'}",
            cot=r[14].strip() if len(r) > 14 else "0", remarks=r[15].strip(),
        )

class FastScheduleParser:
    """Optimized parser for guide schedules"""
    def __init__(self, raw_data: List[List[str]]):
        self.data = raw_data

    def get_schedule(self, guide_row: int, day: int) -> str:
        if not self.data or guide_row > len(self.data): return ""
        header = self.data[0]
        row = self.data[guide_row - 1]
        
        # Determine target column index by looking at the header
        target_col_idx = -1
        day_str = str(day)
        for i, val in enumerate(header):
            if val.strip() == day_str:
                target_col_idx = i
                break
        
        if target_col_idx == -1:
            # Fallback
            target_col_idx = 1 + day
            
        if len(row) <= target_col_idx: return ""
        
        value = row[target_col_idx].strip()
        
        # Multi-day support for merged cells
        if not value:
            # Look back up to index 2 (Day 1)
            for back_idx in range(target_col_idx - 1, 1, -1):
                if back_idx >= len(row): continue
                prev_val = row[back_idx].strip()
                if prev_val:
                    return prev_val
        return value

async def run_audit():
    """Main audit function, can be called from command line OR bot handler"""
    await init_db()
    
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(config.SERVICE_ACCOUNT_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    
    # 1. Access Report Spreadsheet
    try:
        ss = client.open_by_key(REPORT_SPREADSHEET_ID)
        sheet_name = f"Audit_{datetime.datetime.now().strftime('%d.%m_%H.%M.%S')}"
        worksheet = ss.add_worksheet(title=sheet_name, rows="2000", cols="7")
    except Exception as e:
        logger.error(f"Failed to access report spreadsheet: {e}")
        return None

    headers = ["Guide", "Username", "Date", "Type", "Scenario", "Bot Response", "Status"]
    worksheet.update(values=[headers], range_name='A1:G1')
    worksheet.format('A1:G1', {'textFormat': {'bold': True}, 'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}})
    worksheet.freeze(rows=1)

    # 2. Pre-fetch ALL Data
    today_dt = datetime.date.today()
    tomorrow_dt = today_dt + datetime.timedelta(days=1)
    yesterday_dt = today_dt - datetime.timedelta(days=1)
    
    # Pre-fetch list includes Yesterday for comeback guest lists
    dates_to_show = [today_dt, tomorrow_dt]
    all_needed_dates = [yesterday_dt, today_dt, tomorrow_dt]
    
    from services.google_sheets import google_sheets
    from services.sea_plan import sea_plan_service
    
    schedule_sheet = await google_sheets.get_current_month_sheet()
    if not schedule_sheet:
        logger.error("Could not find monthly schedule sheet!")
        return None
        
    logger.info("Pre-fetching monthly schedule...")
    schedule_values = await asyncio.to_thread(schedule_sheet.get_all_values)
    sched_parser = FastScheduleParser(schedule_values)
    
    staff, freelance = await google_sheets.parse_guides(schedule_sheet)
    all_guides_list = staff + freelance
    
    sheet_data = {}
    for d in all_needed_dates:
        logger.info(f"Pre-fetching data for {d.strftime('%d.%m')}...")
        try:
            ws = await sea_plan_service.get_date_worksheet(d)
            if ws:
                sheet_data[d.strftime('%d.%m')] = await asyncio.to_thread(ws.get_all_values)
            else:
                sheet_data[d.strftime('%d.%m')] = []
        except Exception as e:
            logger.error(f"Failed to fetch data for {d}: {e}")
            sheet_data[d.strftime('%d.%m')] = []

    # 3. Process simulations locally
    rows_to_insert = []
    simulator = BotSimulator()
    
    for d_obj in dates_to_show:
        date_str = d_obj.strftime('%d.%m')
        day_num = d_obj.day
        raw_values = sheet_data.get(date_str, [])
        parser = FastPlanParser(raw_values)
        
        # Determine previous day's data for comeback programs
        prev_date_str = (d_obj - datetime.timedelta(days=1)).strftime('%d.%m')
        yesterday_raw = sheet_data.get(prev_date_str, [])
        
        for guide in all_guides_list:
            uname = guide['username']
            guide_name = guide['raw_name']
            guide_row = guide['row']
            
            # --- 1. Schedule simulation ---
            sched_val = sched_parser.get_schedule(guide_row, day_num)
            sched_response = simulator.format_schedule(guide_name, uname, date_str, sched_val)
            rows_to_insert.append([guide_name, uname, date_str, "SCHED", "Schedule", sched_response, "✅" if sched_val else "ℹ️"])
            
            # --- 2. Sea Plan simulation ---
            sea_plans = parser.get_sea_plan(uname, date_str)
            sea_response = simulator.format_sea_plan(sea_plans, uname, date_str)
            rows_to_insert.append([guide_name, uname, date_str, "SEA", "Sea Plan", sea_response, "✅" if sea_plans else "ℹ️"])
            
            if sea_plans:
                prog_names = list(set(prog.name for p in sea_plans for prog in p.programs))
                guests = parser.get_guest_list(prog_names, yesterday_data=yesterday_raw)
                rows_to_insert.append([guide_name, uname, date_str, "SEA", "Guest List", simulator.format_guest_list(guests, date_str), "✅" if guests else "⚠️"])
            
            # --- 3. Land Plan simulation ---
            land_plans = parser.get_land_plan(uname, date_str)
            land_response = simulator.format_land_plan(land_plans, uname, date_str)
            rows_to_insert.append([guide_name, uname, date_str, "LAND", "Land Plan", land_response, "✅" if land_plans else "ℹ️"])

    # 4. Batch Upload
    if rows_to_insert:
        # Split into chunks to avoid too large payload
        chunk_size = 500
        for i in range(0, len(rows_to_insert), chunk_size):
            chunk = rows_to_insert[i:i+chunk_size]
            worksheet.update(values=chunk, range_name=f'A{i+2}:G{i+len(chunk)+1}')
            
        try: worksheet.format('F2:F2000', {'wrapStrategy': 'WRAP'})
        except: pass
        logger.info(f"Audit completed: {len(rows_to_insert)} rows uploaded.")
    
    return f"https://docs.google.com/spreadsheets/d/{REPORT_SPREADSHEET_ID}/edit#gid={worksheet.id}"

if __name__ == "__main__":
    link = asyncio.run(run_audit())
    if link: print(f"\n📊 REPORT: {link}\n")
