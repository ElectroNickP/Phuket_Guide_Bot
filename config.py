import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class Settings(BaseSettings):
    BOT_TOKEN: SecretStr
    ADMIN_ID: int
    ADMIN_IDS: str = ""  # Optional: additional admins, comma-separated (e.g. "123456,789012")
    DEFAULT_SPREADSHEET_ID: str = "1VzzL9hKRSwqga1nsjJ9Df2AlkSBVw_6zRorXDy_MURs"
    DEFAULT_SEA_SPREADSHEET_ID: str = "1wtSeYmTnwcC5d-AxNt3zLaMZhe5-mRXfYJ-gm4nJQ7E"
    SERVICE_ACCOUNT_FILE: str = "google service account/best-telegram-bots-9df5029c28e8.json"
    
    # Database settings
    DB_URL: str = "sqlite+aiosqlite:///data/bot_database.db"
    
    # Intervals
    POLLING_INTERVAL: int = 600  # 10 minutes in seconds

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def admin_id_list(self) -> List[int]:
        """Returns a list of all admin Telegram IDs (primary + additional)."""
        ids = [self.ADMIN_ID] if self.ADMIN_ID else []
        if self.ADMIN_IDS:
            for id_str in self.ADMIN_IDS.split(","):
                try:
                    val = int(id_str.strip())
                    if val not in ids:
                        ids.append(val)
                except ValueError:
                    pass
        return ids

config = Settings()
