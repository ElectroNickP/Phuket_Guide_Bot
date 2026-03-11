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

        now = datetime.datetime.now()
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
            day = datetime.datetime.now().day
            
        col_idx = 2 + day
        # Run blocking call in thread pool
        row_values = await asyncio.to_thread(sheet.row_values, guide_row)
        if len(row_values) < col_idx:
            return None
            
        return row_values[col_idx - 1]

google_sheets = GoogleSheetsService()
