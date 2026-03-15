import asyncio
import gspread
from google.oauth2.service_account import Credentials
from loguru import logger
from config import config
from database.db import AsyncSessionLocal
from database.models import AppSettings
from sqlalchemy import select
import datetime
import re
import time
from typing import List, Dict, Tuple
from database.dto import GuestDTO, GuideDTO, LandPlanDTO, SeaPlanDTO, ProgramDTO

class SeaPlanService:
    def __init__(self):
        self.scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        self.credentials = Credentials.from_service_account_file(
            config.SERVICE_ACCOUNT_FILE, 
            scopes=self.scopes
        )
        self.client = gspread.authorize(self.credentials)
        self._spreadsheet = None
        self._current_spreadsheet_id = None
        self._sheet_cache: Dict[Tuple[str, str], Tuple[float, List[List[str]]]] = {} # (sheet_id, worksheet_name) -> (timestamp, data)
        self._cache_ttl = 300 # 5 minutes

    async def get_spreadsheet_id(self):
        """Fetches Sea Plan spreadsheet ID from DB or config"""
        async with AsyncSessionLocal() as session:
            query = select(AppSettings).where(AppSettings.key == "sea_spreadsheet_id")
            result = await session.execute(query)
            setting = result.scalar_one_or_none()
            return setting.value if setting else config.DEFAULT_SEA_SPREADSHEET_ID

    async def get_spreadsheet(self):
        """Returns the current spreadsheet instance, updating if ID changed"""
        sheet_id = await self.get_spreadsheet_id()
        if not self._spreadsheet or self._current_spreadsheet_id != sheet_id:
            logger.info(f"Opening Sea Plan spreadsheet: {sheet_id}")
            try:
                # Run blocking gspread call in a thread pool
                self._spreadsheet = await asyncio.to_thread(
                    self.client.open_by_key, sheet_id
                )
                self._current_spreadsheet_id = sheet_id
                logger.info(f"Successfully loaded Sea Plan: {self._spreadsheet.title}")
            except Exception as e:
                logger.error(f"Failed to open Sea Plan spreadsheet {sheet_id}: {e}")
                if self._spreadsheet and self._current_spreadsheet_id == sheet_id:
                     logger.warning("Using stale Sea Plan instance due to connection error.")
                else:
                    return None
        return self._spreadsheet

    async def get_date_worksheet(self, target_date: datetime.date):
        """Finds worksheet matching the date (e.g. '10.03')"""
        spreadsheet = await self.get_spreadsheet()
        if not spreadsheet:
            return None
        date_str = target_date.strftime("%d.%m")
        try:
            return await asyncio.to_thread(spreadsheet.worksheet, date_str)
        except gspread.WorksheetNotFound:
            logger.warning(f"Worksheet {date_str} not found in Sea Plan.")
            return None

    async def _get_worksheet_values(self, target_date: datetime.date) -> List[List[str]]:
        """Returns values from a worksheet, utilizing an in-memory cache to prevent 429 errors."""
        sheet_id = await self.get_spreadsheet_id()
        date_str = target_date.strftime("%d.%m")
        cache_key = (sheet_id, date_str)
        
        now = time.time()
        if cache_key in self._sheet_cache:
            ts, data = self._sheet_cache[cache_key]
            if now - ts < self._cache_ttl:
                return data

        # If not in cache or expired, fetch from Google
        worksheet = await self.get_date_worksheet(target_date)
        if not worksheet:
            return []
            
        logger.info(f"Fetching fresh data for worksheet {date_str} (Cache miss/expired)")
        try:
            data = await asyncio.to_thread(worksheet.get_all_values)
            self._sheet_cache[cache_key] = (now, data)
            return data
        except Exception as e:
            logger.error(f"Error fetching worksheet values for {date_str}: {e}")
            # If we have stale data, returns it as a fallback instead of failing
            if cache_key in self._sheet_cache:
                logger.warning(f"Returning stale data for {date_str} due to API error.")
                return self._sheet_cache[cache_key][1]
            return []

    def _validate_sheet_columns(self, header_row: list):
        """
        Defensive check: warns if expected column positions appear empty.
        Expected (0-indexed): 4=program, 5=pax, 7=guide, 13=pier, 15=boat
        """
        expected = {4: "program", 5: "pax", 7: "guide", 13: "pier", 15: "boat"}
        if not header_row:
            logger.warning("Sea Plan sheet header row is empty — cannot validate columns.")
            return
        for idx, name in expected.items():
            if idx >= len(header_row):
                logger.warning(
                    f"Sea Plan column {idx} (expected: '{name}') is out of range. "
                    "Columns may have shifted — verify sheet structure!"
                )

    async def get_guide_sea_plan(self, username: str, target_date: datetime.date) -> List[SeaPlanDTO]:
        """
        Parses the Sea Plan for a specific guide, grouping all data by boat.
        """
        sheet = await self.get_date_worksheet(target_date)
        if not sheet:
            return []
            
        all_values = await self._get_worksheet_values(target_date)
        
        if all_values:
            self._validate_sheet_columns(all_values[0])

        boats_data = {}
        current_boat = None
        current_pier = None
        current_thai_guide = None
        
        for i, row in enumerate(all_values):
            if i > 250 and len(row) > 4:
                row_prog_raw = row[4].strip()
                if row_prog_raw == "TOTAL" or row_prog_raw.startswith("JOB ORDER"):
                    break

            if len(row) < 16: continue
            
            row_boat = row[15].strip()
            row_pier = row[13].strip()
            row_thai = row[1].strip()
            row_date = row[0].strip() or target_date.strftime("%d.%m")

            if "COMEBACK BOATS" in row[4].strip().upper():
                continue

            if row_boat:
                current_boat = row_boat
                current_pier = row_pier
                current_thai_guide = row_thai
            
            if not current_boat:
                continue
                
            guide_str = row[7].strip()
            prog_name = row[4].strip()
            pax_str = row[5].strip()

            if not prog_name and not guide_str:
                continue

            boat_key = f"{current_pier}_{current_boat}"
            if boat_key not in boats_data:
                boats_data[boat_key] = SeaPlanDTO(
                    boat=current_boat,
                    pier=current_pier,
                    date=row_date,
                    thai_guide=current_thai_guide,
                    programs=[],
                    guides=[],
                    total_pax=0,
                    is_assigned=False
                )
            
            dto = boats_data[boat_key]
            
            if prog_name:
                pax_val = 0
                a, c, i = 0, 0, 0
                try:
                    if '/' in pax_str:
                        parts = pax_str.replace(" ", "").split('/')
                        a = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
                        c = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                        i = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                        pax_val = a + c + i
                    elif '+' in pax_str:
                        parts = pax_str.replace(" ", "").split('+')
                        a = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
                        c = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                        pax_val = a + c
                    else:
                        pax_val = int(pax_str)
                        a = pax_val
                except ValueError:
                    pass
                
                short_guide = guide_str
                match_uname = re.search(r'(@\w+)', guide_str)
                if match_uname:
                    short_guide = match_uname.group(1)

                dto.programs.append(ProgramDTO(
                    name=prog_name,
                    pax=pax_str,
                    guide=guide_str,
                    short_guide=short_guide
                ))
                dto.total_pax += pax_val
                
                # Update pax_string
                curr_a, curr_c, curr_i = 0, 0, 0
                if dto.pax_string and dto.pax_string != "0/0/0":
                    curr_parts = dto.pax_string.split('/')
                    curr_a = int(curr_parts[0]) if len(curr_parts) > 0 else 0
                    curr_c = int(curr_parts[1]) if len(curr_parts) > 1 else 0
                    curr_i = int(curr_parts[2]) if len(curr_parts) > 2 else 0
                
                dto.pax_string = f"{curr_a + a}/{curr_c + c}/{curr_i + i}"
            if guide_str:
                matches = re.findall(r'@(\w+)', guide_str)
                is_me = False
                for uname in matches:
                    if uname.lower() == username.lower():
                        is_me = True
                        dto.is_assigned = True
                
                # Check if guide already in list
                if not any(g.full_info == guide_str for g in dto.guides):
                    dto.guides.append(GuideDTO(full_info=guide_str, is_me=is_me))

        return [dto for dto in boats_data.values() if dto.is_assigned]

    async def get_active_sea_guides(self, target_dates: list[datetime.date]) -> list[str]:
        """
        Returns a sorted list of unique @usernames active in sea plans for the given dates.
        """
        all_usernames = set()
        
        for t_date in target_dates:
            sheet = await self.get_date_worksheet(t_date)
            if not sheet:
                continue
            
            all_values = await self._get_worksheet_values(t_date)
            for row in all_values:
                if len(row) < 8:
                    continue
                guide_str = row[7].strip()
                if not guide_str or '@' not in guide_str:
                    continue
                matches = re.findall(r'@(\w+)', guide_str)
                for uname in matches:
                    all_usernames.add(uname.lower())
                    
        return sorted(list(all_usernames))

    async def get_active_land_guides(self, target_dates: list[datetime.date]) -> list[str]:
        """
        Returns a sorted list of unique @usernames active in land plans for the given dates.
        """
        all_usernames = set()
        
        for t_date in target_dates:
            sheet = await self.get_date_worksheet(t_date)
            if not sheet:
                continue
            
            all_values = await self._get_worksheet_values(t_date)
            
            # Land sections include: LAND JOINED TOURS and PRIVATE LAND TOURS
            # Exclusion sections: PRIVATE AVIA TOURS
            is_land_section = False
            for row in all_values:
                row_str = " ".join([str(v) for v in row if v]).upper()
                
                if 'JOB ORDER' in row_str:
                    if 'PRIVATE LAND' in row_str or 'LAND JOINED' in row_str:
                        is_land_section = True
                    else:
                        is_land_section = False
                    continue
                
                if not is_land_section:
                    continue

                if len(row) < 2:
                    continue
                col1 = row[1].strip()
                if '@' in col1:
                    matches = re.findall(r'@(\w+)', col1)
                    for uname in matches:
                        all_usernames.add(uname.lower())
                    
        return sorted(list(all_usernames))
        
    async def get_guide_land_plan(self, username: str, target_date: datetime.date) -> List[LandPlanDTO]:
        """
        Parses the Land Joined Tours section for a specific guide.
        """
        sheet = await self.get_date_worksheet(target_date)
        if not sheet:
            return []
            
        all_values = await self._get_worksheet_values(target_date)
        
        blocks = []
        current_block = None
        username_lower = username.lower()
        
        # 1. Collect all guide identifiers across all land sections
        all_guide_identifiers = set()
        is_land_section = False
        for row in all_values:
            row_str = " ".join([str(v) for v in row if v]).upper()
            if 'JOB ORDER' in row_str:
                if 'PRIVATE LAND' in row_str or 'LAND JOINED' in row_str:
                    is_land_section = True
                else:
                    is_land_section = False
                continue
            
            if not is_land_section:
                continue

            if len(row) < 8: continue
            col1 = row[1].strip()
            col7 = row[7].strip()
            if '@' in col1:
                if col7: all_guide_identifiers.add(col7.lower())
                uname_match = re.search(r'@(\w+)', col1)
                if uname_match: all_guide_identifiers.add(uname_match.group(1).lower())

        # 2. Parse land sections into blocks
        is_land_section = False
        for row in all_values:
            row_str = " ".join([str(v) for v in row if v]).upper()
            
            if 'JOB ORDER' in row_str:
                if current_block:
                    blocks.append(current_block)
                    current_block = None
                if 'PRIVATE LAND' in row_str or 'LAND JOINED' in row_str:
                    is_land_section = True
                else:
                    is_land_section = False
                continue
            
            if not is_land_section:
                continue

            if len(row) < 16: continue
            
            col1 = row[1].strip()
            col2 = row[2].strip()
            col3 = row[3].strip()
            col4 = row[4].strip()
            col7 = row[7].strip()
            
            # Check for header based on date in Col A or specific formatting
            is_header = False
            if row[4].strip() and not row[1].strip() and not row[7].strip() and not ('@' in row[1]):
                is_header = True
            elif row[3].strip() and not row[1].strip() and not row[7].strip() and (' b' in row[3].lower() or 'bus' in row[3].lower()):
                 is_header = True

            if is_header:
                if current_block:
                    blocks.append(current_block)
                current_block = LandPlanDTO(
                    program=row[4].strip() or row[3].strip(),
                    date=target_date.strftime("%d.%m"),
                    guides=[],
                    guests=[],
                    is_assigned=False
                )
                continue
            
            # If no current block and we see a guide, start one (handles missing headers)
            if not current_block and '@' in col1:
                current_block = LandPlanDTO(
                    program="Unknown/Joined",
                    date=target_date.strftime("%d.%m"),
                    guides=[],
                    guests=[],
                    is_assigned=False
                )
                continue
            
            if not current_block:
                continue

            if '@' in col1:
                is_me = False
                uname_match = re.search(r'@(\w+)', col1)
                if uname_match and uname_match.group(1).lower() == username_lower:
                    is_me = True
                    current_block.is_assigned = True
                
                pu_time = col3
                if ' ' in pu_time: pu_time = pu_time.split(' ')[0]
                
                pax_a_g, pax_c_g, pax_i_g = 0, 0, 0
                try:
                    pax_a_g = int(row[9]) if row[9].isdigit() else 0
                    pax_c_g = int(row[10]) if row[10].isdigit() else 0
                    pax_i_g = int(row[11]) if row[11].isdigit() else 0
                except: pass

                current_block.guides.append(GuideDTO(
                    full_info=col1,
                    short_name=col7,
                    pickup_time=pu_time,
                    pickup_location=col4,
                    pax=f"{pax_a_g}/{pax_c_g}/{pax_i_g}",
                    is_me=is_me
                ))
                continue

            if 'Bus' in col3 or (col2 and 'Bus' in col2):
                if current_block:
                    current_block.bus = col3 if 'Bus' in col3 else col2
                    current_block.driver = col7
                    current_block.is_assigned = any(g.is_me for g in current_block.guides)
                    blocks.append(current_block)
                    current_block = None
                continue

            if col7 and col7.lower() not in all_guide_identifiers:
                try:
                    pax_a = int(row[9]) if row[9].isdigit() else 0
                    pax_c = int(row[10]) if row[10].isdigit() else 0
                    pax_i = int(row[11]) if row[11].isdigit() else 0
                    
                    pax_str = f"{pax_a}/{pax_c}/{pax_i}"
                    total_pax = pax_a + pax_c + pax_i
                    if total_pax == 0: continue
                except: continue

                current_block.guests.append(GuestDTO(
                    voucher=col2 or "N/A",
                    pickup=col3,
                    hotel=col4,
                    area=row[5].strip() if len(row) > 5 else "-",
                    room=row[6].strip() or "-",
                    name=col7,
                    phone=row[8].strip() or "-",
                    pax=pax_str,
                    cot=row[14].strip() if len(row) > 14 else "0",
                    remarks=row[15].strip() if len(row) > 15 else "-"
                ))

        if current_block:
            blocks.append(current_block)

        # Calculate accumulated pax_string for each assigned block
        assigned = [b for b in blocks if b.is_assigned]
        for b in assigned:
            a, c, i = 0, 0, 0
            for g in b.guides:
                parts = g.pax.split('/')
                a += int(parts[0]); c += int(parts[1]); i += int(parts[2])
            for gst in b.guests:
                parts = gst.pax.split('/')
                a += int(parts[0]); c += int(parts[1]); i += int(parts[2])
            b.pax_string = f"{a}/{c}/{i}"

        return assigned

    async def get_guest_list(self, target_date: datetime.date, program_names: list[str]) -> List[GuestDTO]:
        """
        Retrieves a detailed guest list from the top section of the sheet
        based on exact matches with the given program names.
        Handles "Comeback" programs by looking back at the previous day.
        """
        sheet = await self.get_date_worksheet(target_date)
        if not sheet:
            return []

        # Categorize programs into current-day and previous-day (comebacks)
        comeback_markers = ["COMEBACK", "ВЫВОЗ", "RETURN"]
        
        standard_progs_lower = set()
        comeback_mapping_lower = {} # cleaned_name_lower -> original_name
        
        for p in program_names:
            is_comeback = False
            for marker in comeback_markers:
                if marker.upper() in p.upper():
                    # Clean the name: "COMEBACK 5 Pearls" -> "5 Pearls"
                    cleaned = re.sub(rf'(?i)\b({marker})\b', '', p, flags=re.IGNORECASE).strip()
                    cleaned = re.sub(r'^[\s\-\:]+', '', cleaned).strip()
                    comeback_mapping_lower[cleaned.lower()] = p
                    is_comeback = True
                    break
            
            if not is_comeback:
                standard_progs_lower.add(p.lower())

        all_guests = []
        
        # 1. Fetch Guest List for standard programs (Current Day)
        if standard_progs_lower:
            current_values = await self._get_worksheet_values(target_date)
            for r in current_values:
                if len(r) < 14: continue
                program_str = r[13].strip()
                if program_str and program_str.lower() in standard_progs_lower:
                    all_guests.append(self._parse_guest_row(r))

        # 2. Fetch Guest List for comeback programs (Previous Day)
        if comeback_mapping_lower:
            prev_date = target_date - datetime.timedelta(days=1)
            prev_values = await self._get_worksheet_values(prev_date)
            if prev_values:
                for r in prev_values:
                    if len(r) < 14: continue
                    program_str = r[13].strip()
                    prog_lower = program_str.lower()
                    
                    # We also want to match if the plan has "5 Pearls" and the guest list has "5 Pearls b2"
                    # or if the plan has "5 Pearls comfort" and guest list has "5 Pearls comfort"
                    matched_orig = None
                    for cleaned_lower, orig in comeback_mapping_lower.items():
                        if prog_lower == cleaned_lower or prog_lower.startswith(cleaned_lower + " "):
                            matched_orig = orig
                            break
                    
                    if matched_orig:
                        guest = self._parse_guest_row(r)
                        guest.program = matched_orig
                        all_guests.append(guest)
                
        return all_guests

    def _parse_guest_row(self, r: list) -> GuestDTO:
        return GuestDTO(
            program=r[13].strip(),
            agent=r[1].strip(),
            voucher=r[2].strip(),
            pickup=r[3].strip(),
            hotel=r[4].strip(),
            room=r[6].strip(),
            name=r[7].strip(),
            phone=r[8].strip(),
            pax=f"{r[9].strip() or '0'}/{r[10].strip() or '0'}/{r[11].strip() or '0'}",
            cot=r[14].strip() if len(r) > 14 else "0",
            remarks=r[15].strip(),
        )

sea_plan_service = SeaPlanService()
