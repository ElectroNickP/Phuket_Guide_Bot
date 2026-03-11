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
            # Run blocking call in thread pool
            return await asyncio.to_thread(spreadsheet.worksheet, date_str)
        except gspread.WorksheetNotFound:
            logger.warning(f"Worksheet {date_str} not found in Sea Plan.")
            return None

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

    async def get_guide_sea_plan(self, username: str, target_date: datetime.date):
        """
        Parses the Sea Plan for a specific guide, grouping all data by boat.
        """
        sheet = await self.get_date_worksheet(target_date)
        if not sheet:
            return None
            
        # Run blocking call in thread pool
        all_values = await asyncio.to_thread(sheet.get_all_values)
        
        # Defensive column validation on the first non-empty row
        if all_values:
            self._validate_sheet_columns(all_values[0])
            for idx, r in enumerate(all_values[:25]):
                logger.debug(f"ROW {idx}: {r}")

        # boat_id (pier+boat name) -> aggregated_info
        boats_data = {}
        
        current_boat = None
        current_pier = None
        current_thai_guide = None
        
        # Columns (0-indexed):
        # 0: Date, 1: Thai Guide/Note, 4: Program, 5: Pax, 6: Grand Total, 7: Guide, 13: Pier, 15: Boat
        for i, row in enumerate(all_values):
            if len(row) < 16: continue
            
            # Identify row type: is it a header row for a boat?
            row_boat = row[15].strip()
            row_pier = row[13].strip()
            row_thai = row[1].strip()
            row_date = row[0].strip()
            row_program = row[4].strip()

            # STOP CONDITION: break if we hit the summary or private tour sections
            # WE ONLY APPLY THIS IF WE HAVE ALREADY FOUND A BOAT (to avoid breaking on headers)
            stop_keywords = ["BOOKED", "FREE", "TOTAL", "ENHANCED", "STANDARD", "SUPERIOR", "JOB ORDER"]
            if current_boat and (any(k in row_thai.upper() for k in stop_keywords) or \
                               any(k in row_program.upper() for k in stop_keywords)):
                logger.debug(f"Stop condition met at row {i}: {row_thai} | {row_program}")
                break

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
                boats_data[boat_key] = {
                    "date": row_date or target_date.strftime("%d.%m"),
                    "boat": current_boat,
                    "pier": current_pier,
                    "thai_guide": current_thai_guide,
                    "total_pax": 0,
                    "programs": [],
                    "guides": set(),
                    "assigned_usernames": set()
                }
            
            # Aggregate program
            if prog_name:
                pax_val = 0
                try:
                    pax_val = int(pax_str)
                except (ValueError, TypeError):
                    pass
                
                short_guide = guide_str
                # Attempt to extract just the @username
                match_uname = re.search(r'(@\w+)', guide_str)
                if match_uname:
                    short_guide = match_uname.group(1)
                
                boats_data[boat_key]["programs"].append({
                    "name": prog_name,
                    "pax": pax_str,
                    "guide": guide_str,
                    "short_guide": short_guide
                })
                boats_data[boat_key]["total_pax"] += pax_val

            # Aggregate guide
            if guide_str:
                matches = re.findall(r'@(\w+)', guide_str)
                for uname_raw in matches:
                    uname = uname_raw.lower()
                    boats_data[boat_key]["assigned_usernames"].add(uname)
                    boats_data[boat_key]["guides"].add(guide_str)

        # Filter boats where the requested guide is assigned
        username_lower = username.lower()
        result_plans = []
        
        for boat_key, data in boats_data.items():
            if username_lower in data["assigned_usernames"]:
                formatted_plan = {
                    "date": data["date"],
                    "boat": data["boat"],
                    "pier": data["pier"],
                    "thai_guide": data["thai_guide"],
                    "total_pax": data["total_pax"],
                    "guides_list": sorted(list(data["guides"])),
                    "programs": data["programs"]  # Raw list for conditional formatting in handlers
                }
                result_plans.append(formatted_plan)
        
        return result_plans

    async def get_active_sea_guides(self, target_dates: list[datetime.date]) -> list[str]:
        """
        Returns a sorted list of unique @usernames active in sea plans for the given dates.
        """
        all_usernames = set()
        
        for t_date in target_dates:
            sheet = await self.get_date_worksheet(t_date)
            if not sheet:
                continue
            
            all_values = await asyncio.to_thread(sheet.get_all_values)
            for i, row in enumerate(all_values):
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
            
            all_values = await asyncio.to_thread(sheet.get_all_values)
            
            # Find land section start
            land_start = -1
            for i, row in enumerate(all_values):
                row_str = " ".join([str(v) for v in row if v])
                if 'JOB ORDER - LAND JOINED TOURS' in row_str:
                    land_start = i
                    break
            
            if land_start == -1:
                continue

            for i in range(land_start + 1, len(all_values)):
                row = all_values[i]
                if len(row) < 2:
                    continue
                col1 = row[1].strip()
                if '@' in col1:
                    matches = re.findall(r'@(\w+)', col1)
                    for uname in matches:
                        all_usernames.add(uname.lower())
                    
        return sorted(list(all_usernames))
        
    async def get_guide_land_plan(self, username: str, target_date: datetime.date):
        """
        Parses the Land Joined Tours section for a specific guide.
        """
        sheet = await self.get_date_worksheet(target_date)
        if not sheet:
            return None
            
        all_values = await asyncio.to_thread(sheet.get_all_values)
        
        land_start = -1
        for i, row in enumerate(all_values):
            row_str = " ".join([str(v) for v in row if v])
            if 'JOB ORDER - LAND JOINED TOURS' in row_str:
                land_start = i
                break
        
        if land_start == -1:
            return None

        # Blocks will store data for each "Bus"
        blocks = []
        current_block = None
        
        username_lower = username.lower()
        
        # We need to scan for all guide identifiers to strictly filter them out from guest lists
        all_guide_identifiers = set()
        for i in range(land_start + 1, len(all_values)):
            row = all_values[i]
            if len(row) < 8: continue
            col1 = row[1].strip()
            col7 = row[7].strip()
            if '@' in col1:
                if col7: all_guide_identifiers.add(col7.lower())
                uname_match = re.search(r'@(\w+)', col1)
                if uname_match: all_guide_identifiers.add(uname_match.group(1).lower())

        for i in range(land_start + 1, len(all_values)):
            row = all_values[i]
            if len(row) < 16: continue
            
            col1 = row[1].strip() # Agent / Guide Handle
            col2 = row[2].strip() # Voucher
            col3 = row[3].strip() # P/U Time / Bus No
            col4 = row[4].strip() # Hotel / Program
            col7 = row[7].strip() # Guest Name / Guide Short Name
            
            # 1. Detect Program/Bus Header (e.g. "Krabi b1", "Khao lak b2")
            # Logic: Col 4 contains " b" followed by digits, and Col 1 is NOT a guide row
            if col4 and re.search(r' b\d+', col4) and not ('@' in col1):
                if current_block:
                    blocks.append(current_block)
                current_block = {
                    "program": col4,
                    "date": target_date.strftime("%d.%m"),
                    "guides": [],
                    "bus": None,
                    "driver": None,
                    "guests": [],
                    "is_assigned": False
                }
                continue
            
            if not current_block:
                continue

            # 2. Identify Guide Row
            if '@' in col1:
                is_me = False
                uname_match = re.search(r'@(\w+)', col1)
                if uname_match and uname_match.group(1).lower() == username_lower:
                    is_me = True
                    current_block["is_assigned"] = True
                
                # Extract Pickup Time from Col 3
                pu_time = col3
                if ' ' in pu_time: pu_time = pu_time.split(' ')[0]
                
                current_block["guides"].append({
                    "full_info": col1,
                    "short_name": col7,
                    "pickup_time": pu_time,
                    "pickup_location": col4,
                    "is_me": is_me
                })
                continue

            # 3. Identify Bus/Driver Row
            if 'Bus' in col3 or (col2 and 'Bus' in col2):
                current_block["bus"] = col3 if 'Bus' in col3 else col2
                current_block["driver"] = col7
                continue

            # 4. Identify Guest Row
            # Logic: Col 7 is not empty and not in the guide identifier set
            if col7 and col7.lower() not in all_guide_identifiers:
                # Calculate Pax (Cols 9, 10, 11)
                try:
                    pax_a = int(row[9]) if row[9].isdigit() else 0
                    pax_c = int(row[10]) if row[10].isdigit() else 0
                    pax_i = int(row[11]) if row[11].isdigit() else 0
                    # For land tours, we often show it as A/C/I
                    pax_str = f"{pax_a}/{pax_c}/{pax_i}"
                    total_pax = pax_a + pax_c + pax_i
                    if total_pax == 0: continue # Skip zero pax rows
                except (ValueError, IndexError):
                    continue

                current_block["guests"].append({
                    "voucher": col2 or "N/A",
                    "pickup": col3,
                    "hotel": col4,
                    "area": row[5].strip() if len(row) > 5 else "-",
                    "room": row[6].strip() or "-",
                    "name": col7,
                    "phone": row[8].strip() or "-",
                    "pax": pax_str,
                    "cot": row[14].strip() if len(row) > 14 else "0",
                    "remarks": row[15].strip() if len(row) > 15 else "-"
                })

        if current_block:
            blocks.append(current_block)

        # Filter blocks where the guide is assigned
        my_blocks = [b for b in blocks if b["is_assigned"]]
        return my_blocks if my_blocks else None

    async def get_guest_list(self, target_date: datetime.date, program_names: list[str]) -> list[dict]:
        """
        Retrieves a detailed guest list from the top section of the sheet
        based on exact matches with the given program names.
        """
        sheet = await self.get_date_worksheet(target_date)
        if not sheet:
            return []

        all_values = await asyncio.to_thread(sheet.get_all_values)
        
        # We'll return a list of guests
        guests = []
        
        # Scan through rows.
        for r in all_values:
            # Skip empty or short rows
            if len(r) < 16:
                continue
                
            program_str = r[13].strip()
            # If the row has a program that is in our target list
            if program_str and program_str in program_names:
                guests.append({
                    "program": program_str,
                    "agent": r[1].strip(),
                    "voucher": r[2].strip(),
                    "pickup": r[3].strip(),
                    "hotel": r[4].strip(),
                    "room": r[6].strip(),
                    "name": r[7].strip(),
                    "phone": r[8].strip(),
                    "pax": f"{r[9].strip() or '0'}/{r[10].strip() or '0'}/{r[11].strip() or '0'}",
                    "cot": r[14].strip() if len(r) > 14 else "0",
                    "remarks": r[15].strip(),
                })
                
        # Return grouped by program
        grouped_guests = {}
        for p in program_names:
            grouped_guests[p] = []
            
        for g in guests:
            if g["program"] in grouped_guests:
                grouped_guests[g["program"]].append(g)
                
        # Only return non-empty programs
        return [{"program_name": k, "guests": v} for k, v in grouped_guests.items() if v]

sea_plan_service = SeaPlanService()
