import asyncio
import datetime
from services.google_sheets import google_sheets

async def check():
    sheet = await google_sheets.get_current_month_sheet()
    if not sheet:
        print("No sheet found")
        return
    
    staff, freelance = google_sheets.parse_guides(sheet)
    all_guides = staff + freelance
    
    # Check for @Nick_0989
    guide = next((g for g in all_guides if g['username'].lower() == 'nick_0989'), None)
    if not guide:
        print("Guide @Nick_0989 not found")
        return
    
    print(f"Found guide at row {guide['row']}")
    
    # Check for tomorrow (March 10)
    day = 10
    program = google_sheets.get_guide_schedule(sheet, guide['row'], day=day)
    print(f"Program for day {day}: {program}")

if __name__ == "__main__":
    asyncio.run(check())
