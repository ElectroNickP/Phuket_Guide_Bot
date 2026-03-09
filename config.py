import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class Settings(BaseSettings):
    BOT_TOKEN: SecretStr
    ADMIN_ID: int
    DEFAULT_SPREADSHEET_ID: str = "1VzzL9hKRSwqga1nsjJ9Df2AlkSBVw_6zRorXDy_MURs"
    SERVICE_ACCOUNT_FILE: str = "/app/google service account/best-telegram-bots-9df5029c28e8.json"
    
    # Database settings
    DB_URL: str = "sqlite+aiosqlite:///data/bot_database.db"
    
    # Intervals
    POLLING_INTERVAL: int = 600  # 10 minutes in seconds

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

config = Settings()
