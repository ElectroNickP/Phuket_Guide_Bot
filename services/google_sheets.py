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
                self._spreadsheet = self.client.open_by_key(sheet_id)
                self._current_spreadsheet_id = sheet_id
                logger.info(f"Successfully loaded spreadsheet: {self._spreadsheet.title}")
            except Exception as e:
                logger.error(f"Failed to open spreadsheet {sheet_id}: {e}")
                raise e
        return self._spreadsheet

    async def get_current_month_sheet(self):
        """
        Finds the sheet for the current month.
        """
        spreadsheet = await self.get_spreadsheet()
        now = datetime.datetime.now()
        month = f"{now.month:02d}"
        year_short = str(now.year)[2:]
        
        possible_names = [f"{month}.{year_short}", f"{month}/{year_short}"]
        
        all_sheets = spreadsheet.worksheets()
        for sheet in all_sheets:
            if sheet.title in possible_names:
                return sheet
        
        # Fallback to search by month start
        for sheet in all_sheets:
            if sheet.title.startswith(month):
                return sheet
                
        logger.error(f"Sheet for month {month} not found!")
        return None

    def parse_guides(self, sheet):
        """
        Parses Column A to identify staff and freelance guides.
        """
        col_a = sheet.col_values(1)
        staff_guides = []
        freelance_guides = []
        
        is_freelance_section = False
        
        for i, value in enumerate(col_a):
            row_idx = i + 1
            if row_idx < 8:
                continue
            
            clean_value = str(value).strip().upper()
            
            if "ФРИЛАНС" in clean_value:
                is_freelance_section = True
                continue
            
            if "ВЫХОДНЫЕ" in clean_value:
                continue

            match = re.search(r'@(\w+)', str(value))
            if match:
                username = match.group(1)
                guide_data = {
                    "raw_name": value,
                    "username": username,
                    "row": row_idx,
                    "type": "freelance" if is_freelance_section else "staff"
                }
                if is_freelance_section:
                    freelance_guides.append(guide_data)
                else:
                    staff_guides.append(guide_data)
        
        return staff_guides, freelance_guides

    def get_guide_schedule(self, sheet, guide_row, day=None):
        if day is None:
            day = datetime.datetime.now().day
            
        col_idx = 2 + day
        row_values = sheet.row_values(guide_row)
        if len(row_values) < col_idx:
            return None
            
        return row_values[col_idx - 1]

google_sheets = GoogleSheetsService()
