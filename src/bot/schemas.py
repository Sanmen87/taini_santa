# src/bot/schemas.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# Колонки листа Participants
PARTICIPANTS_COLUMNS: List[str] = [
    "Время обновления",
    "Telegram ID",
    "Username",
    "ФИО",
    "Отдел",
    "Телефон",
    "Участвует",
    "Подтверждён",
    "Валидатор",
    "Время валидации",
    "Telegram ID получателя",
    "ФИО получателя",
    "Инфо о получателе",
    "Уведомлён",
    "Комментарий администратора",
]


# Колонки листа Polls
POLLS_COLUMNS: List[str] = [
    "ID",
    "Вопрос",
    "Варианты",
    "Правильный индекс",
    "Очки",
    "Статус",
]


# Колонки листа PollResponses
POLL_RESPONSES_COLUMNS: List[str] = [
    "Poll ID",
    "Telegram ID",
    "Ответ",
    "Правильный",
    "Время ответа",
]


@dataclass
class Participant:
    tg_id: int
    username: Optional[str]
    full_name: str
    department: str
    phone: str
    active: bool = True
    validated: bool = False
    validator_tg_id: Optional[int] = None
    validation_ts: Optional[str] = None
    recipient_tg_id: Optional[int] = None
    recipient_name: Optional[str] = None
    recipient_info: Optional[str] = None
    notified: bool = False
    admin_comment: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: List[str]) -> "Participant":
        """
        Преобразование строки из таблицы в объект Participant.
        Ожидается, что row идёт строго в порядке PARTICIPANTS_COLUMNS.
        """
        data: Dict[str, Any] = {}
        # безопасно берём по индексу, если колонок меньше — подставляем ""
        def _get(i: int) -> str:
            return row[i] if i < len(row) else ""

        updated_at = _get(0) or None
        tg_id_raw = _get(1)
        username = _get(2) or None
        full_name = _get(3) or ""
        department = _get(4) or ""
        phone = _get(5) or ""
        active_raw = _get(6)
        validated_raw = _get(7)
        validator_raw = _get(8)
        validation_ts = _get(9) or None
        recipient_tg_raw = _get(10)
        recipient_name = _get(11) or None
        recipient_info = _get(12) or None
        notified_raw = _get(13)
        admin_comment = _get(14) or None

        return cls(
            tg_id=int(tg_id_raw) if tg_id_raw else 0,
            username=username,
            full_name=full_name,
            department=department,
            phone=phone,
            active=active_raw.upper() == "TRUE",
            validated=validated_raw.upper() == "TRUE",
            validator_tg_id=int(validator_raw) if validator_raw else None,
            validation_ts=validation_ts,
            recipient_tg_id=int(recipient_tg_raw) if recipient_tg_raw else None,
            recipient_name=recipient_name,
            recipient_info=recipient_info,
            notified=notified_raw.upper() == "TRUE",
            admin_comment=admin_comment,
            updated_at=updated_at,
        )

    def to_row(self) -> List[str]:
        """
        Преобразование объекта Participant в список строк для записи в таблицу.
        Порядок строго соответствует PARTICIPANTS_COLUMNS.
        """
        def _bool(v: bool) -> str:
            return "TRUE" if v else "FALSE"

        return [
            self.updated_at or "",
            str(self.tg_id),
            self.username or "",
            self.full_name,
            self.department,
            self.phone,
            _bool(self.active),
            _bool(self.validated),
            str(self.validator_tg_id) if self.validator_tg_id is not None else "",
            self.validation_ts or "",
            str(self.recipient_tg_id) if self.recipient_tg_id is not None else "",
            self.recipient_name or "",
            self.recipient_info or "",
            _bool(self.notified),
            self.admin_comment or "",
        ]


@dataclass
class PollQuestion:
    poll_id: str
    question: str
    options: List[str]
    correct_index: Optional[int]
    points: int
    status: str  # e.g. active, draft, closed

    @classmethod
    def from_row(cls, row: List[str]) -> "PollQuestion":
        def _get(i: int) -> str:
            return row[i] if i < len(row) else ""

        poll_id = _get(0) or ""
        question = _get(1) or ""
        options_raw = _get(2) or ""
        options = [opt.strip() for opt in options_raw.split("|") if opt.strip()]
        correct_raw = _get(3)
        correct_index = int(correct_raw) if correct_raw.isdigit() else None
        points_raw = _get(4)
        points = int(points_raw) if points_raw.isdigit() else 0
        status = _get(5) or "draft"
        return cls(
            poll_id=poll_id,
            question=question,
            options=options,
            correct_index=correct_index,
            points=points,
            status=status,
        )

    def to_row(self) -> List[str]:
        return [
            self.poll_id,
            self.question,
            "|".join(self.options),
            str(self.correct_index) if self.correct_index is not None else "",
            str(self.points),
            self.status,
        ]


@dataclass
class PollResponse:
    poll_id: str
    tg_id: int
    answer_index: int
    is_correct: bool
    submitted_at: str

    @classmethod
    def from_row(cls, row: List[str]) -> "PollResponse":
        def _get(i: int) -> str:
            return row[i] if i < len(row) else ""

        poll_id = _get(0) or ""
        tg_raw = _get(1)
        answer_raw = _get(2)
        correct_raw = _get(3)
        submitted = _get(4) or ""
        return cls(
            poll_id=poll_id,
            tg_id=int(tg_raw) if tg_raw else 0,
            answer_index=int(answer_raw) if answer_raw.isdigit() else -1,
            is_correct=correct_raw.upper() == "TRUE",
            submitted_at=submitted,
        )

    def to_row(self) -> List[str]:
        def _bool(v: bool) -> str:
            return "TRUE" if v else "FALSE"

        return [
            self.poll_id,
            str(self.tg_id),
            str(self.answer_index),
            _bool(self.is_correct),
            self.submitted_at,
        ]
