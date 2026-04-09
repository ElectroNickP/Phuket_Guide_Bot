import asyncio
import datetime
from services.sea_plan import sea_plan_service

async def dump_all_mentions():
    target_date = datetime.date(2026, 3, 22)
    values = await sea_plan_service._get_worksheet_values(target_date)
    for i, row in enumerate(values):
        row_str = " | ".join([str(c) for c in row])
        if '@' in row_str:
            print(f"Row {i}: {row_str}")

if __name__ == '__main__':
    asyncio.run(dump_all_mentions())
