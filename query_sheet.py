import asyncio
import gspread
from google.oauth2.service_account import Credentials

async def main():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(
        "google service account/best-telegram-bots-9df5029c28e8.json", 
        scopes=scopes
    )
    client = gspread.authorize(creds)
    
    # Correct ID from DB logs
    sheet_id = "155LXx2XlMwLBV8as8h3WIgLNO2n7TlUhK1Ki8T43eZI"
    sheet = client.open_by_key(sheet_id)
    
    # Let's get "11.03"
    ws = sheet.worksheet("11.03")
    values = ws.get_all_values()
    
    print(f"Total rows: {len(values)}")
    
    # Search for the "DATE" "AGENT" header row
    for i, r in enumerate(values):
        if r and r[0].upper().strip() == "DATE":
            print(f"--- Header Row {i} ---")
            for col_idx, col_name in enumerate(r):
                print(f"Col {col_idx}: {col_name}")
            
            print(f"\n--- Data Row {i+1} ---")
            print(values[i+1][:20])
            break

if __name__ == '__main__':
    asyncio.run(main())
