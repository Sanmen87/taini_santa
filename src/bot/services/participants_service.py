# src/bot/services/participants_service.py
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from typing import Dict, Iterable, List, Optional, Tuple

import gspread

from ..config import get_settings
from ..google_sheets import SheetClient, utc_now_iso, get_sheet_client
from ..schemas import Participant, PARTICIPANTS_COLUMNS

logger = logging.getLogger(__name__)


@dataclass
class _ParticipantsCacheEntry:
    expires_at: float
    participants: List[Participant]
    by_tg_id: Dict[int, Participant]


_participants_cache: Optional[_ParticipantsCacheEntry] = None


def _chunked(seq: List[Dict[str, List[List[str]]]], size: int) -> Iterable[List[Dict[str, List[List[str]]]]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _clone_participant(participant: Participant) -> Participant:
    return replace(participant)


def _set_participants_cache(participants: List[Participant], ttl: float) -> None:
    global _participants_cache
    if ttl <= 0:
        _participants_cache = None
        return
    clones = [_clone_participant(p) for p in participants]
    _participants_cache = _ParticipantsCacheEntry(
        expires_at=time.monotonic() + ttl,
        participants=clones,
        by_tg_id={p.tg_id: p for p in clones if p.tg_id},
    )


def _get_cached_list() -> Optional[List[Participant]]:
    if _participants_cache is None:
        return None
    if time.monotonic() > _participants_cache.expires_at:
        return None
    return [_clone_participant(p) for p in _participants_cache.participants]


def _get_cached_participant(tg_id: int) -> Optional[Participant]:
    if _participants_cache is None:
        return None
    if time.monotonic() > _participants_cache.expires_at:
        return None
    cached = _participants_cache.by_tg_id.get(tg_id)
    if cached is None:
        return None
    return _clone_participant(cached)


def _invalidate_cache() -> None:
    global _participants_cache
    _participants_cache = None


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
        sheets_settings = get_settings().sheets
        self._cache_ttl = max(0.0, float(getattr(sheets_settings, "participants_cache_ttl", 10.0)))
        self._batch_chunk_size = max(1, int(getattr(sheets_settings, "participants_batch_chunk", 40)))

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

    def get_by_tg_id(self, tg_id: int, *, use_cache: bool = True) -> Optional[Participant]:
        self._ensure_header()
        if use_cache and self._cache_ttl > 0:
            cached = _get_cached_participant(tg_id)
            if cached is not None:
                return cached
        row_idx = self._find_row_index_by_tg_id(tg_id)
        if row_idx is None:
            return None
        row = self.sheet.row_values(row_idx)
        participant = Participant.from_row(row)
        participant.row_index = row_idx
        return participant

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

        participant.row_index = row_idx
        _invalidate_cache()
        return participant, row_idx

    def bulk_upsert_participants(self, participants: List[Participant]) -> None:
        """
        Обновляет несколько строк одним или несколькими batch-запросами,
        чтобы не упираться в лимиты Google Sheets API.
        """
        if not participants:
            return
        self._ensure_header()
        prepared: List[Dict[str, List[List[str]]]] = []
        for participant in participants:
            if not participant.row_index:
                raise ValueError("Participant must have row_index for bulk update")
            participant.updated_at = utc_now_iso()
            prepared.append(
                {
                    "range": f"{participant.row_index}:{participant.row_index}",
                    "values": [participant.to_row()],
                }
            )
        for chunk in _chunked(prepared, self._batch_chunk_size):
            self.sheet.batch_update(chunk)
        _invalidate_cache()

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

    def list_all(self, *, use_cache: bool = True) -> List[Participant]:
        """
        Простой список всех участников (для будущего /list).
        """
        self._ensure_header()
        if use_cache and self._cache_ttl > 0:
            cached = _get_cached_list()
            if cached is not None:
                return cached
        values = self.sheet.get_all_values()
        if not values:
            if self._cache_ttl > 0:
                _set_participants_cache([], self._cache_ttl)
            return []
        # пропускаем header
        participants: List[Participant] = []
        for row_idx, row in enumerate(values[1:], start=2):
            participant = Participant.from_row(row)
            participant.row_index = row_idx
            participants.append(participant)
        if self._cache_ttl > 0:
            _set_participants_cache(participants, self._cache_ttl)
        return participants
