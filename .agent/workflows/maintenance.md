---
description: How to maintain and expand the Phuket Guide Bot
---
# Developer Workflow

This bot is built with a modular architecture to ensure transparency for both humans and AI agents.

## Project Structure
- `bot.py`: Entry point and scheduler initialization.
- `config.py`: Environment variables and constants.
- `handlers/`: Role-based message logic.
- `services/`: External integrations (Google Sheets, Scheduler).
- `database/`: Persistence layer (SQLAlchemy + SQLite).

## Adding New Commands
1. Create or update a router in `handlers/`.
2. Register the router in `bot.py` if it's a new file.

## Modifying Spreadsheet Logic
- Update `services/google_sheets.py`.
- Ensure column/row indices match the physical spreadsheet structure.

## Deployment
// turbo
1. Build and start: `docker-compose up -d --build`
2. Check logs: `docker-compose logs -f`
