# src/bot/services/polls_service.py
from __future__ import annotations

import logging
from typing import List, Optional

import gspread

from ..google_sheets import SheetClient, utc_now_iso, get_sheet_client
from ..schemas import (
    POLLS_COLUMNS,
    POLL_RESPONSES_COLUMNS,
    PollQuestion,
    PollResponse,
)

logger = logging.getLogger(__name__)


class PollsService:
    def __init__(self, sheet_client: Optional[SheetClient] = None) -> None:
        self._sheet_client = sheet_client or get_sheet_client()

    @property
    def polls_sheet(self) -> gspread.Worksheet:
        return self._sheet_client.polls_sheet()

    def _ensure_header(self) -> None:
        values = self.polls_sheet.row_values(1)
        if values != POLLS_COLUMNS:
            logger.info("Updating Polls header row")
            self.polls_sheet.update("1:1", [POLLS_COLUMNS])

    def list_all(self) -> List[PollQuestion]:
        self._ensure_header()
        values = self.polls_sheet.get_all_values()
        if not values:
            return []
        return [PollQuestion.from_row(row) for row in values[1:]]

    def get_poll_by_id(self, poll_id: str) -> Optional[PollQuestion]:
        polls = self.list_all()
        for poll in polls:
            if poll.poll_id == poll_id:
                return poll
        return None

    def get_active_poll(self) -> Optional[PollQuestion]:
        polls = self.list_all()
        for poll in polls:
            if poll.status.lower() == "active":
                return poll
        return None


class PollResponsesService:
    def __init__(self, sheet_client: Optional[SheetClient] = None) -> None:
        self._sheet_client = sheet_client or get_sheet_client()

    @property
    def responses_sheet(self) -> gspread.Worksheet:
        return self._sheet_client.poll_responses_sheet()

    def _ensure_header(self) -> None:
        values = self.responses_sheet.row_values(1)
        if values != POLL_RESPONSES_COLUMNS:
            logger.info("Updating PollResponses header row")
            self.responses_sheet.update("1:1", [POLL_RESPONSES_COLUMNS])

    def list_by_poll(self, poll_id: str) -> List[PollResponse]:
        self._ensure_header()
        values = self.responses_sheet.get_all_values()
        if not values:
            return []
        responses = []
        for row in values[1:]:
            resp = PollResponse.from_row(row)
            if resp.poll_id == poll_id:
                responses.append(resp)
        return responses

    def has_response(self, poll_id: str, tg_id: int) -> bool:
        responses = self.list_by_poll(poll_id)
        for resp in responses:
            if resp.tg_id == tg_id:
                return True
        return False

    def add_response(self, response: PollResponse) -> None:
        self._ensure_header()
        response.submitted_at = utc_now_iso()
        self.responses_sheet.append_row(response.to_row())
