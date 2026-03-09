# Phuket Guide Schedule Bot 🏝🚤

Professional Telegram bot for managing guide schedules from Google Sheets.

## Features ✨

- 📅 **Interactive Schedule**: View schedule for today and tomorrow with inline buttons.
- 👤 **Role Management**: Support for Staff and Freelance guides.
- ⚠️ **Dynamic Notifications**: Instant alerts when the schedule changes in Google Sheets.
- 🛠 **Advanced Admin Panel**:
  - 📊 **Detailed Statistics**: Track user activity, last contact, and engagement levels.
  - ⏱ **Custom Polling**: Set spreadsheet update frequency (1 min to 1 hour) directly from the bot.
  - 👁 **Guide Monitoring**: Check any guide's schedule by username.
  - 🔗 **Sheet Management**: Change the target Google Sheet ID on the fly.
  - 📋 **Log Access**: View latest system logs via Telegram.
- 📝 **Feedback System**: direct communication line from guides to administrator.
- 🐳 **Docker Ready**: Easy deployment using Docker Compose.

## Tech Stack 🛠

- **Framework**: [Aiogram 3.x](https://github.com/aiogram/aiogram) (Asynchronous Telegram Bot API)
- **Database**: SQLite with [SQLAlchemy](https://www.sqlalchemy.org/) & [AioSqlite](https://github.com/omnilib/aiosqlite)
- **Sheet Integration**: [GSpread](https://github.com/burnash/gspread) with Service Account
- **Scheduling**: [APScheduler](https://github.com/agronholm/apscheduler)
- **Logging**: [Loguru](https://github.com/Delgan/loguru)

## Setup and Installation 🚀

1. **Clone the repository**:
   ```bash
   git clone <your-repo-url>
   cd <repo-name>
   ```

2. **Configure Environment**:
   Create a `.env` file and fill in the following:
   ```env
   BOT_TOKEN=your_telegram_bot_token
   ADMIN_ID=your_telegram_id
   DEFAULT_SPREADSHEET_ID=your_google_sheet_id
   SERVICE_ACCOUNT_FILE=/app/google service account/your-key.json
   DB_URL=sqlite+aiosqlite:///data/bot_database.db
   POLLING_INTERVAL=600
   ```

3. **Google Service Account**:
   Place your JSON key in the `google service account/` directory.

4. **Run with Docker**:
   ```bash
   docker-compose up -d --build
   ```

## Development 💻

To run locally without Docker:
1. Install dependencies: `pip install -r requirements.txt`
2. Run the bot: `python bot.py`

## License 📄
Private Project.
