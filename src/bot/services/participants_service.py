# src/bot/services/participants_service.py
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import gspread

from ..google_sheets import SheetClient, utc_now_iso, get_sheet_client
from ..schemas import Participant, PARTICIPANTS_COLUMNS

logger = logging.getLogger(__name__)


class ParticipantsService:
    def __init__(self, sheet_client: Optional[SheetClient] = None) -> None:
        """
        Если sheet_client не передан явно, используем один общий экземпляр
        (singleton), чтобы не переинициализировать Google Sheets клиент
        на каждый запрос.
        """
        if sheet_client is not None:
            self._sheet_client = sheet_client
        else:
            self._sheet_client = get_sheet_client()

    @property
    def sheet(self) -> gspread.Worksheet:
        return self._sheet_client.participants_sheet()

    # ---------- Вспомогательные методы ----------

    def _ensure_header(self) -> None:
        """
        Гарантирует, что первая строка содержит правильные заголовки.
        Не трогает существующие данные ниже.
        """
        values = self.sheet.row_values(1)
        if values != PARTICIPANTS_COLUMNS:
            logger.info("Updating Participants header row")
            self.sheet.update(
                "1:1",
                [PARTICIPANTS_COLUMNS],
            )

    def _find_row_index_by_tg_id(self, tg_id: int) -> Optional[int]:
        """
        Ищем строку по Telegram ID.
        Возвращает индекс строки (1-based) или None.
        """
        # колонка 2 — "Telegram ID"
        try:
            cell = self.sheet.find(str(tg_id), in_column=2)
        except Exception as e:
            # В некоторых версиях gspread может выбрасываться разный тип исключений
            logger.debug("Telegram ID %s not found (exception): %s", tg_id, e)
            return None

        if cell is None:
            logger.debug("Telegram ID %s not found (cell is None)", tg_id)
            return None

        return cell.row


    # ---------- Публичные методы ----------

    def get_by_tg_id(self, tg_id: int) -> Optional[Participant]:
        self._ensure_header()
        row_idx = self._find_row_index_by_tg_id(tg_id)
        if row_idx is None:
            return None
        row = self.sheet.row_values(row_idx)
        return Participant.from_row(row)

    def upsert_participant(
        self,
        participant: Participant,
    ) -> Tuple[Participant, int]:
        """
        Создаёт или обновляет участника.
        Возвращает (participant, row_index).
        """
        self._ensure_header()
        row_idx = self._find_row_index_by_tg_id(participant.tg_id)

        participant.updated_at = utc_now_iso()
        row_values = participant.to_row()

        if row_idx is None:
            # добавляем новую строку
            logger.info("Creating new participant tg_id=%s", participant.tg_id)
            self.sheet.append_row(row_values)
            # заново ищем индекс (append_row не возвращает его напрямую)
            row_idx = self._find_row_index_by_tg_id(participant.tg_id)
            if row_idx is None:
                raise RuntimeError("Failed to locate row just appended")
        else:
            # обновляем существующую строку
            logger.info("Updating participant tg_id=%s row=%s", participant.tg_id, row_idx)
            self.sheet.update(f"{row_idx}:{row_idx}", [row_values])

        return participant, row_idx

    def set_active(self, tg_id: int, active: bool) -> Optional[Participant]:
        """
        Пометить участника как активного/неактивного (команда /leave и т.п.).
        """
        participant = self.get_by_tg_id(tg_id)
        if not participant:
            return None
        participant.active = active
        updated, _ = self.upsert_participant(participant)
        return updated

    def list_all(self) -> List[Participant]:
        """
        Простой список всех участников (для будущего /list).
        """
        self._ensure_header()
        values = self.sheet.get_all_values()
        if not values:
            return []
        # пропускаем header
        return [Participant.from_row(row) for row in values[1:]]
