import asyncio
import datetime
from services.sea_plan import sea_plan_service

async def dump_range(start, end):
    target_date = datetime.date(2026, 3, 22)
    values = await sea_plan_service._get_worksheet_values(target_date)
    for i in range(start, min(end, len(values))):
        row = values[i]
        print(f"Row {i}: {' | '.join([str(c) for c in row])}")

if __name__ == '__main__':
    import sys
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    asyncio.run(dump_range(start, end))
