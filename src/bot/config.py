from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass
class TelegramConfig:
    bot_token: str
    admin_ids: List[int]
    admin_chat_id: Optional[int]  # ID чата/группы для валидации


@dataclass
class SheetsConfig:
    spreadsheet_id: str
    participants_sheet: str
    polls_sheet: str
    poll_responses_sheet: str
    achievements_sheet: str
    service_account_json: str  # путь к файлу


@dataclass
class Settings:
    telegram: TelegramConfig
    sheets: SheetsConfig


def get_settings() -> Settings:
    # ADMIN_IDS=123,456,789
    admin_ids_raw = os.getenv("ADMIN_IDS", "")
    admin_ids = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip()]

    # ADMIN_CHAT_ID=-1001234567890 (ID группы/канала с админами)
    admin_chat_id_raw = os.getenv("ADMIN_CHAT_ID")
    admin_chat_id: Optional[int]
    if admin_chat_id_raw:
        try:
            admin_chat_id = int(admin_chat_id_raw)
        except ValueError:
            admin_chat_id = None
    else:
        admin_chat_id = None

    return Settings(
        telegram=TelegramConfig(
            bot_token=os.environ["BOT_TOKEN"],
            admin_ids=admin_ids,
            admin_chat_id=admin_chat_id,
        ),
        sheets=SheetsConfig(
            spreadsheet_id=os.environ["GSHEET_SPREADSHEET_ID"],
            participants_sheet=os.getenv("GSHEET_PARTICIPANTS_SHEET_NAME", "Participants"),
            polls_sheet=os.getenv("GSHEET_POLLS_SHEET_NAME", "Polls"),
            poll_responses_sheet=os.getenv("GSHEET_POLL_RESPONSES_SHEET_NAME", "PollResponses"),
            achievements_sheet=os.getenv("GSHEET_ACHIEVEMENTS_SHEET_NAME", "Achievements"),
            service_account_json=os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
        ),
    )
