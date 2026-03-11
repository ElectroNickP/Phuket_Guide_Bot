import asyncio
import gspread
from google.oauth2.service_account import Credentials

async def main():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("google service account/best-telegram-bots-9df5029c28e8.json", scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("155LXx2XlMwLBV8as8h3WIgLNO2n7TlUhK1Ki8T43eZI")
    ws = sheet.worksheet("11.03")
    values = ws.get_all_values()
    
    # Let's find where the Sea Plan section starts and where the Guest section is
    for i, r in enumerate(values):
        if len(r) > 15 and r[15] and r[15].upper() == 'BOAT':
            print(f"Sea Plan Header found at row {i}: {r}")
        if len(r) > 13 and r[13] and 'PROGRAM' in r[13].upper():
            print(f"Guest List Header found at row {i}: {r[:16]}")

if __name__ == '__main__':
    asyncio.run(main())
