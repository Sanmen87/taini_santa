# src/bot/schemas.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


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
