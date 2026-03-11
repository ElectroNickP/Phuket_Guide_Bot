import asyncio
import csv
from services.google_sheets import GoogleSheetsService
GoogleSheetsService.get_spreadsheet_id = lambda self: "1wtSeYmTnwcC5d-AxNt3zLaMZhe5-mRXfYJ-gm4nJQ7E"

async def main():
    service = GoogleSheetsService()
    try:
        sheet = await asyncio.to_thread(service.client.open_by_key, "1wtSeYmTnwcC5d-AxNt3zLaMZhe5-mRXfYJ-gm4nJQ7E")
        ws = sheet.worksheet('11.03')
        values = await asyncio.to_thread(ws.get_all_values)
        with open('sea_plan_dump.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(values[:150])
        print("Done")
    except Exception as e:
        print("ERR:", e)

if __name__ == '__main__':
    asyncio.run(main())
