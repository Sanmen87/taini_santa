# src/bot/google_sheets.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import gspread
from google.oauth2.service_account import Credentials
from requests.adapters import HTTPAdapter
import urllib3
from urllib3.util.retry import Retry

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

        session = getattr(gc, "session", None)
        if session is not None:
            _configure_http_session(session, settings)
            _disable_ssl_verification(session)

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


def _configure_http_session(session, settings) -> None:
    timeout = max(1.0, float(getattr(settings.sheets, "request_timeout", 10.0)))
    max_retries = max(0, int(getattr(settings.sheets, "max_retries", 3)))
    backoff = max(0.0, float(getattr(settings.sheets, "retry_backoff_factor", 0.5)))

    try:
        if max_retries > 0:
            retry = Retry(
                total=max_retries,
                read=max_retries,
                connect=max_retries,
                status=max_retries,
                backoff_factor=backoff,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET", "POST", "PUT", "PATCH", "DELETE"]),
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry)
            session.mount("https://", adapter)
            session.mount("http://", adapter)

        original_request = session.request

        def request_with_timeout(method, url, **kwargs):
            kwargs.setdefault("timeout", timeout)
            return original_request(method, url, **kwargs)

        session.request = request_with_timeout
    except Exception as exc:
        logger.warning("Failed to configure Google Sheets HTTP session: %s", exc)


def _disable_ssl_verification(session) -> None:
    try:
        session.verify = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        logger.warning("SSL verification for Google Sheets is DISABLED (dev mode).")
    except Exception as exc:
        logger.error("Failed to disable SSL verification for Google Sheets: %s", exc)
