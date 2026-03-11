from utils.time import get_phuket_now, get_phuket_today
import asyncio
from services.sea_plan import sea_plan_service
import datetime

async def main():
    sheet = await sea_plan_service.get_date_worksheet(get_phuket_today())
    if not sheet:
        print("No sheet found")
        return
    values = await asyncio.to_thread(sheet.get_all_values)
    print("Total rows:", len(values))
    for i, row in enumerate(values[:25]): # print first 25
        print(f"Row {i:02d} [{len(row)}]: {row}")

if __name__ == "__main__":
    asyncio.run(main())
