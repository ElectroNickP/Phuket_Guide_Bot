import asyncio
from services.google_sheets import GoogleSheetsService
GoogleSheetsService.get_spreadsheet_id = lambda self: "1wtSeYmTnwcC5d-AxNt3zLaMZhe5-mRXfYJ-gm4nJQ7E"

async def main():
    service = GoogleSheetsService()
    try:
        sheet = await asyncio.to_thread(service.client.open_by_key, "1wtSeYmTnwcC5d-AxNt3zLaMZhe5-mRXfYJ-gm4nJQ7E")
        sheets = await asyncio.to_thread(sheet.worksheets)
        print("Available sheets:", [s.title for s in sheets])
        ws = sheets[0] # Grab the first sheet
        values = await asyncio.to_thread(ws.get_all_values)
        print(f"\nROWS for {ws.title}:")
        for i, row in enumerate(values[:5]):
            print(f"[{i}] {row}")
    except Exception as e:
        print("ERR:", e)

if __name__ == '__main__':
    asyncio.run(main())
