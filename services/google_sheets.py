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
import json

DEBUG_LOG_PATH = "/home/nick/Projects/Phuket/Best/Best_sea_job_orders/.cursor/debug.log"

def _debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict):
    # region agent log
    try:
        payload = {
            "id": f"{int(datetime.datetime.now().timestamp() * 1000)}_{hypothesis_id}",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(datetime.datetime.now().timestamp() * 1000),
        }
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion

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
        self._all_values_cache = {} # {sheet_title: (timestamp, values)}
        self._merges_cache = {}     # {sheet_title: merges_list}
        self._worksheets_cache = {} # {spreadsheet_id: (timestamp, list_of_worksheets)}
        self._col_values_cache = {} # {cache_key: (timestamp, list)}

    async def get_spreadsheet_id(self) -> str:
        """Fetches spreadsheet ID from DB or config"""
        async with AsyncSessionLocal() as session:
            query = select(AppSettings).where(AppSettings.key == "spreadsheet_id")
            result = await session.execute(query)
            setting = result.scalars().first()
            return setting.value if setting else config.DEFAULT_SPREADSHEET_ID

    async def get_spreadsheet(self) -> gspread.Spreadsheet:
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
                
                # If it's a permission error, we should probably let the caller know immediately
                # so it doesn't just fail silently with 'None'
                is_permission_error = "403" in str(e) or "permission" in str(e).lower()
                
                if self._spreadsheet and self._current_spreadsheet_id == sheet_id and not is_permission_error:
                    logger.warning("Using stale spreadsheet instance due to connection error.")
                else:
                    # Re-raise so handlers can provide better feedback
                    raise e
        return self._spreadsheet

    async def get_sheet_by_date(self, target_date: datetime.date) -> gspread.Worksheet | None:
        """
        Finds the sheet for a specific month/year.
        """
        spreadsheet = await self.get_spreadsheet()
        if not spreadsheet:
            return None

        month = f"{target_date.month:02d}"
        year_short = str(target_date.year)[2:]
        
        possible_names = [f"{month}.{year_short}", f"{month}/{year_short}"]
        
        # Use cached worksheets
        all_sheets = await self._get_cached_worksheets(spreadsheet)
        for sheet in all_sheets:
            if sheet.title in possible_names:
                return sheet
        
        # Fallback to search by month start
        for sheet in all_sheets:
            if sheet.title.startswith(month):
                return sheet
                
        logger.error(f"Sheet for date {target_date} not found!")
        return None

    async def get_current_month_sheet(self) -> gspread.Worksheet | None:
        """
        Finds the sheet for the current month.
        """
        return await self.get_sheet_by_date(get_phuket_now().date())

    async def parse_guides(self, sheet: gspread.Worksheet) -> tuple[list[dict], list[dict]]:
        """
        Parses Column A to identify staff and freelance guides based on markers:
        - Staff start after "ГИДЫ:"
        - Staff end at "ВЫХОДНЫЕ"
        - Freelance start after "ФРИЛАНС"
        """
        # Use cached column values to avoid API rate limits
        col_a = await self._get_cached_col_values(sheet, 1)

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

            match = re.search(r'@([\w\d_]+)', str(value))
            if match:
                username = match.group(1).strip()
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

    async def _get_cached_worksheets(self, spreadsheet: gspread.Spreadsheet) -> list[gspread.Worksheet]:
        cache_key = spreadsheet.id
        now = get_phuket_now()
        if cache_key in self._worksheets_cache:
            ts, worksheets = self._worksheets_cache[cache_key]
            if (now - ts).total_seconds() < 300: # 5 mins TTL
                return worksheets
        
        logger.info(f"Fetching fresh worksheets list for {cache_key}")
        worksheets = await asyncio.to_thread(spreadsheet.worksheets)
        self._worksheets_cache[cache_key] = (now, worksheets)
        return worksheets

    async def _get_cached_col_values(self, sheet: gspread.Worksheet, col_index: int) -> list[str]:
        cache_key = f"{sheet.spreadsheet.id}_{sheet.title}_col_{col_index}"
        now = get_phuket_now()
        if cache_key in self._col_values_cache:
            ts, values = self._col_values_cache[cache_key]
            if (now - ts).total_seconds() < 300: # 5 mins TTL
                return values
        
        logger.info(f"Fetching fresh column values for {cache_key}")
        values = await asyncio.to_thread(sheet.col_values, col_index)
        self._col_values_cache[cache_key] = (now, values)
        return values

    async def _get_cached_values(self, sheet: gspread.Worksheet) -> list[list[str]]:
        cache_key = f"{sheet.spreadsheet.id}_{sheet.title}"
        now = get_phuket_now()
        if cache_key in self._all_values_cache:
            ts, values = self._all_values_cache[cache_key]
            if (now - ts).total_seconds() < 60:
                return values
        
        values = await asyncio.to_thread(sheet.get_all_values)
        self._all_values_cache[cache_key] = (now, values)
        return values

    async def _get_cached_merges(self, sheet: gspread.Worksheet) -> list[dict]:
        sheet_title = sheet.title
        if sheet_title in self._merges_cache:
            return self._merges_cache[sheet_title]
            
        try:
            metadata = await asyncio.to_thread(sheet.spreadsheet.fetch_sheet_metadata)
            sheet_meta = next((s for s in metadata['sheets'] if s['properties']['title'] == sheet_title), None)
            merges = sheet_meta.get('merges', []) if sheet_meta else []
            self._merges_cache[sheet_title] = merges
            return merges
        except Exception as e:
            logger.error(f"Error fetching merges for {sheet_title}: {e}")
            return []

    async def get_guide_schedule(self, sheet: gspread.Worksheet, guide_row: int, target_date: datetime.date = None) -> str | None:
        if target_date is None:
            target_date = get_phuket_now().date()
        # region agent log
        _debug_log(
            run_id="pre-fix",
            hypothesis_id="H1_H2_H3",
            location="services/google_sheets.py:get_guide_schedule:entry",
            message="Entered get_guide_schedule",
            data={"sheet_title": getattr(sheet, "title", None), "guide_row": guide_row, "target_date": str(target_date)},
        )
        # endregion
        
        day = target_date.day
        all_values = await self._get_cached_values(sheet)
        if not all_values or guide_row > len(all_values):
            # region agent log
            _debug_log(
                run_id="pre-fix",
                hypothesis_id="H3",
                location="services/google_sheets.py:get_guide_schedule:row_guard",
                message="Row guard returned None",
                data={"has_values": bool(all_values), "values_len": len(all_values) if all_values else 0, "guide_row": guide_row},
            )
            # endregion
            return None
            
        header = all_values[0]
        # Find column by searching for the day number
        target_col = -1
        day_str = str(day).strip()
        for i, val in enumerate(header):
            if str(val).strip() == day_str:
                target_col = i
                break
        
        if target_col == -1:
            target_col = 2 + day - 1
            # region agent log
            _debug_log(
                run_id="pre-fix",
                hypothesis_id="H2",
                location="services/google_sheets.py:get_guide_schedule:fallback_col",
                message="Header day not found, using fallback column",
                data={"day": day, "fallback_col": target_col, "header_len": len(header)},
            )
            # endregion
            
        row_values = all_values[guide_row - 1]
        value = row_values[target_col].strip() if target_col < len(row_values) else ""
        
        if value:
            # region agent log
            _debug_log(
                run_id="pre-fix",
                hypothesis_id="H4",
                location="services/google_sheets.py:get_guide_schedule:direct_value",
                message="Returning direct cell value",
                data={"target_col": target_col, "value_preview": value[:80]},
            )
            # endregion
            return value
            
        # Merged Check
        merges = await self._get_cached_merges(sheet)
        r_idx = guide_row - 1
        c_idx = target_col
        
        for m in merges:
            if (m['startRowIndex'] <= r_idx < m['endRowIndex'] and 
                m['startColumnIndex'] <= c_idx < m['endColumnIndex']):
                sr, sc = m['startRowIndex'], m['startColumnIndex']
                if sr < len(all_values) and sc < len(all_values[sr]):
                    merged_val = all_values[sr][sc].strip()
                    # region agent log
                    _debug_log(
                        run_id="pre-fix",
                        hypothesis_id="H1",
                        location="services/google_sheets.py:get_guide_schedule:merge_hit",
                        message="Merge cell source resolved",
                        data={"source_row": sr, "source_col": sc, "merged_preview": merged_val[:80]},
                    )
                    # endregion
        # region agent log
        _debug_log(
            run_id="pre-fix",
            hypothesis_id="H1",
            location="services/google_sheets.py:get_guide_schedule:implicit_none",
            message="Function reached implicit None return path",
            data={"guide_row": guide_row, "target_col": c_idx, "merges_count": len(merges)},
        )
        # endregion
    async def get_guide_4day_data(self, username: str) -> list[dict]:
        """Fetches 4-day schedule data for a specific username (Yesterday to After Tomorrow)"""
        now = get_phuket_now().date()
        date_list = [
            ("⏮ Вчера", now - datetime.timedelta(days=1)),
            ("📅 Сегодня", now),
            ("📅 Завтра", now + datetime.timedelta(days=1)),
            ("⏭ Послезавтра", now + datetime.timedelta(days=2))
        ]
        
        results = []
        sheet_row_cache = {} # {sheet_title: row_idx}
        
        for label, target_date in date_list:
            sheet = await self.get_sheet_by_date(target_date)
            if not sheet:
                results.append({"label": label, "date": target_date, "sched": "❌ Лист не найден"})
                continue
            
            # Find row in this specific sheet
            if sheet.title not in sheet_row_cache:
                s, f = await self.parse_guides(sheet)
                all_g = s + f
                guide = next((g for g in all_g if g['username'].lower() == username.lower()), None)
                sheet_row_cache[sheet.title] = guide['row'] if guide else -1
            
            row_idx = sheet_row_cache[sheet.title]
            if row_idx == -1:
                results.append({"label": label, "date": target_date, "sched": "---"})
                continue
                
            sched = await self.get_guide_schedule(sheet, row_idx, target_date)
            results.append({"label": label, "date": target_date, "sched": sched or "---"})
        
        return results


google_sheets = GoogleSheetsService()
