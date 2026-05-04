import asyncio
from services.sea_plan import sea_plan_service
from utils.time import get_phuket_now
from loguru import logger

async def debug_sheet():
    target_date = get_phuket_now().date()
    print(f"Target date: {target_date}")
    all_values = await sea_plan_service._get_worksheet_values(target_date)
    
    print("Found total rows:", len(all_values))
    print("Column Map:", sea_plan_service.col)
    
    for i, row in enumerate(all_values):
        row_str = " ".join([str(v) for v in row if v]).upper()
        if 'YAMU' in row_str:
            print(f"ROW {i}: {row}")
            print(f"Length: {len(row)}")
            # Try parsing logic manually
            C_PROG = sea_plan_service.col["program"]
            C_PIER = sea_plan_service.col["pier"]
            C_BOAT = sea_plan_service.col["boat"]
            prog = row[C_PROG] if len(row) > C_PROG else None
            pier = row[C_PIER] if len(row) > C_PIER else None
            boat = row[C_BOAT] if len(row) > C_BOAT else None
            print(f"-> PROG={prog}, PIER={pier}, BOAT={boat}")

if __name__ == "__main__":
    asyncio.run(debug_sheet())
