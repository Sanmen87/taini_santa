# src/bot/google_sheets.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import gspread
from google.oauth2.service_account import Credentials
import urllib3

from .config import get_settings

logger = logging.getLogger(__name__)

SCOPES: List[str] = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@dataclass
class SheetClient:
    gc: gspread.Client
    spreadsheet: gspread.Spreadsheet

    @classmethod
    def from_settings(cls) -> "SheetClient":
        """
        Создаёт клиента Google Sheets, используя настройки и сервисный аккаунт.
        """
        settings = get_settings()

        # Учетные данные сервисного аккаунта
        creds = Credentials.from_service_account_file(
            settings.sheets.service_account_json,
            scopes=SCOPES,
        )

        # Инициализируем gspread-клиент
        gc = gspread.authorize(creds)

        # ⚠ ОТКЛЮЧАЕМ проверку сертификата ТОЛЬКО для Google Sheets в dev-среде.
        if hasattr(gc, "session"):
            try:
                gc.session.verify = False
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                logger.warning("SSL verification for Google Sheets is DISABLED (dev mode).")
            except Exception as e:
                logger.error("Failed to disable SSL verification for Google Sheets: %s", e)

        spreadsheet = gc.open_by_key(settings.sheets.spreadsheet_id)

        logger.info("Google Sheets client initialized")
        return cls(gc=gc, spreadsheet=spreadsheet)

    def participants_sheet(self) -> gspread.Worksheet:
        """
        Возвращает лист с участниками.
        """
        from .config import get_settings as _get_settings  # локальный импорт, чтобы не было циклов

        settings = _get_settings()
        return self.spreadsheet.worksheet(settings.sheets.participants_sheet)

    def polls_sheet(self) -> gspread.Worksheet:
        settings = get_settings()
        return self.spreadsheet.worksheet(settings.sheets.polls_sheet)

    def poll_responses_sheet(self) -> gspread.Worksheet:
        settings = get_settings()
        return self.spreadsheet.worksheet(settings.sheets.poll_responses_sheet)

    def achievements_sheet(self) -> gspread.Worksheet:
        settings = get_settings()
        return self.spreadsheet.worksheet(settings.sheets.achievements_sheet)


def utc_now_iso() -> str:
    """
    Время в ISO-формате (UTC) для поля 'Время обновления'.
    """
    return datetime.now(timezone.utc).isoformat()
# --- КЭШ ОДНОГО ЭКЗЕМПЛЯРА SheetClient ---

_sheet_client_singleton: Optional[SheetClient] = None


def get_sheet_client() -> SheetClient:
    """
    Возвращает один и тот же экземпляр SheetClient
    на протяжении жизни процесса.
    """
    global _sheet_client_singleton
    if _sheet_client_singleton is None:
        _sheet_client_singleton = SheetClient.from_settings()
    return _sheet_client_singleton
