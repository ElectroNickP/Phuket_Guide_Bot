import asyncio
import datetime
from services.sea_plan import sea_plan_service

async def search_program(name):
    target_date = datetime.date(2026, 3, 22)
    values = await sea_plan_service._get_worksheet_values(target_date)
    for i, row in enumerate(values):
        if name.lower() in str(row).lower():
            print(f"Row {i}: {' | '.join([str(c) for c in row])}")

if __name__ == '__main__':
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else 'Elephant Beach'
    asyncio.run(search_program(name))
