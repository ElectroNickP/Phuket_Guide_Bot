from utils.time import get_phuket_now, get_phuket_today
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

class GoogleSheetsService:
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
        """Fetches spreadsheet ID from DB or config"""
        async with AsyncSessionLocal() as session:
            query = select(AppSettings).where(AppSettings.key == "spreadsheet_id")
            result = await session.execute(query)
            setting = result.scalar_one_or_none()
            return setting.value if setting else config.DEFAULT_SPREADSHEET_ID

    async def get_spreadsheet(self):
        """Returns the current spreadsheet instance, updating if ID changed"""
        sheet_id = await self.get_spreadsheet_id()
        if not self._spreadsheet or self._current_spreadsheet_id != sheet_id:
            logger.info(f"Opening spreadsheet: {sheet_id}")
            try:
                # Run blocking gspread call in a thread pool
                self._spreadsheet = await asyncio.to_thread(
                    self.client.open_by_key, sheet_id
                )
                self._current_spreadsheet_id = sheet_id
                logger.info(f"Successfully loaded spreadsheet: {self._spreadsheet.title}")
            except Exception as e:
                logger.error(f"Failed to open spreadsheet {sheet_id}: {e}")
                if self._spreadsheet and self._current_spreadsheet_id == sheet_id:
                    logger.warning("Using stale spreadsheet instance due to connection error.")
                else:
                    return None
        return self._spreadsheet

    async def get_current_month_sheet(self):
        """
        Finds the sheet for the current month.
        """
        spreadsheet = await self.get_spreadsheet()
        if not spreadsheet:
            return None

        now = get_phuket_now()
        month = f"{now.month:02d}"
        year_short = str(now.year)[2:]
        
        possible_names = [f"{month}.{year_short}", f"{month}/{year_short}"]
        
        # Run blocking call in thread pool
        all_sheets = await asyncio.to_thread(spreadsheet.worksheets)
        for sheet in all_sheets:
            if sheet.title in possible_names:
                return sheet
        
        # Fallback to search by month start
        for sheet in all_sheets:
            if sheet.title.startswith(month):
                return sheet
                
        logger.error(f"Sheet for month {month} not found!")
        return None

    async def parse_guides(self, sheet):
        """
        Parses Column A to identify staff and freelance guides based on markers:
        - Staff start after "ГИДЫ:"
        - Staff end at "ВЫХОДНЫЕ"
        - Freelance start after "ФРИЛАНС"
        """
        # Run blocking call in thread pool
        col_a = await asyncio.to_thread(sheet.col_values, 1)

        staff_guides = []
        freelance_guides = []
        
        current_section = None  # Can be 'staff' or 'freelance'
        
        for i, value in enumerate(col_a):
            row_idx = i + 1
            clean_value = str(value).strip().upper()
            
            if "ГИДЫ:" in clean_value:
                current_section = 'staff'
                continue
            
            if "ВЫХОДНЫЕ" in clean_value:
                current_section = None
                continue
                
            if "ФРИЛАНС" in clean_value:
                current_section = 'freelance'
                continue

            if not current_section:
                continue

            match = re.search(r'@(\w+)', str(value))
            if match:
                username = match.group(1)
                guide_data = {
                    "raw_name": value,
                    "username": username,
                    "row": row_idx,
                    "type": current_section
                }
                if current_section == 'staff':
                    staff_guides.append(guide_data)
                elif current_section == 'freelance':
                    freelance_guides.append(guide_data)
        
        logger.info(f"Parsed {len(staff_guides)} staff and {len(freelance_guides)} freelance guides")
        return staff_guides, freelance_guides

    async def get_guide_schedule(self, sheet, guide_row, day=None):
        if day is None:
            day = get_phuket_now().day
            
        # Run blocking call in thread pool
        all_values = await asyncio.to_thread(sheet.get_all_values)
        if not all_values or guide_row > len(all_values):
            return None
            
        header = all_values[0]
        row_values = all_values[guide_row - 1]
        
        # 1. Dynamically find the column for the day
        # We look for a cell in the first row that matches the day number (string)
        target_col_idx = -1
        day_str = str(day)
        for i, val in enumerate(header):
            if val.strip() == day_str:
                target_col_idx = i
                break
        
        # Fallback to hardcoded logic if header parsing fails
        if target_col_idx == -1:
            target_col_idx = 1 + day # Column C is Index 2, which is Day 1. So Day N is N+1? No, 2+N-1 = N+1.
            # My previous was 2+day which is N+2. Let's be careful.
            # C is Col 3 (Index 2). Day 1. 2 + 1 = 3 (Index 2). Correct.
            target_col_idx = 2 + day - 1 # Index 2 for Day 1.
        
        if len(row_values) <= target_col_idx:
            return None
            
        value = row_values[target_col_idx].strip()
        
        # --- Multi-day / Merged Cells Support ---
        if not value:
            day_off_markers = ["ВЫХ", "OFF", "VACATION", "RESERVE", "РЕЗЕРВ"]
            
            # Look back up to 5 days (some programs are long)
            # Stay within the schedule bounds (start looking from target_col_idx - 1)
            # Column C (Index 2) is the start of the schedule
            for back_idx in range(target_col_idx - 1, 1, -1):
                if back_idx >= len(row_values):
                    continue
                
                prev_val = row_values[back_idx].strip()
                if prev_val:
                    # We return the value even if it's a day off, because if it's merged, 
                    # it means the day off continues.
                    return prev_val
                    
        return value

google_sheets = GoogleSheetsService()
