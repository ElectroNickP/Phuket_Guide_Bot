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
                match = re.search(r'@(\w+)', guide_str)
                if match:
                    uname = match.group(1).lower()
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
        
        return result_plans if result_plans else None

sea_plan_service = SeaPlanService()
