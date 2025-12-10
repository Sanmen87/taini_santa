# src/bot/handlers/admin.py
from __future__ import annotations

import logging
import random
from typing import Tuple, List, Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from ..config import get_settings
from ..google_sheets import utc_now_iso
from ..services.participants_service import ParticipantsService
from ..keyboards import admin_main_kb
from ..schemas import Participant

from requests.exceptions import RequestException, ConnectionError as RequestsConnectionError
try:
    from gspread.exceptions import APIError as GSpreadAPIError
except Exception:
    GSpreadAPIError = Exception

logger = logging.getLogger(__name__)
router = Router()


class AdminBroadcastStates(StatesGroup):
    waiting_broadcast = State()


def _is_admin(user_id: int) -> bool:
    settings = get_settings()
    admin_ids = settings.telegram.admin_ids
    try:
        return int(user_id) in admin_ids
    except Exception:
        return False


# ---------- Вспомогательная функция для безопасного чтения участников ----------


async def _load_participants_or_error(message: Message) -> Optional[List[Participant]]:
    """
    Получаем список участников из Google Sheets.
    В случае ошибки показываем администратору понятное сообщение и возвращаем None.
    """
    ps = ParticipantsService()
    try:
        participants = ps.list_all()
        return participants
    except (RequestsConnectionError, RequestException, GSpreadAPIError) as e:
        logger.error("Failed to load participants from Google Sheets: %s", e)
        await message.answer(
            "❌ Не удалось получить список участников из Google Sheets.\n"
            "Похоже, временная проблема с подключением к Google API.\n"
            "Попробуйте повторить попытку чуть позже."
        )
        return None
    except Exception as e:
        logger.exception("Unexpected error while loading participants: %s", e)
        await message.answer(
            "❌ Произошла непредвиденная ошибка при чтении таблицы участников.\n"
            "Детали смотрите в логах сервера."
        )
        return None


# ---------- Меню администратора ----------


@router.message(Command("admin"))
@router.message(Command("admin_ping"))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    await message.answer(
        "Меню администратора:\n"
        "• 🎲 Провести жеребьёвку — команда /draw или кнопка «Провести жеребьёвку».\n"
        "• 📨 Разослать результаты — команда /notify или кнопка «Разослать результаты» (напоминание).\n"
        "• 👥 Участники — показать всех активных.\n"
        "• ✅ Подтверждённые — только прошедшие валидацию.\n"
        "• 📢 Общая рассылка — отправить/переслать любое сообщение всем пользователям из таблицы.",
        reply_markup=admin_main_kb(),
    )


# ---------- Кнопки меню (reply-клавиатура) ----------


@router.message(F.text.contains("Провести жереб"))
async def btn_draw(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await _handle_draw(message)


@router.message(F.text.contains("Разослать результат"))
async def btn_notify(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await _handle_notify(message)


@router.message(F.text.contains("Участник"))
async def btn_list_all(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await _send_participants_list(message, only_validated=False)


@router.message(F.text.contains("Подтвержд"))
async def btn_list_validated(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await _send_participants_list(message, only_validated=True)


@router.message(F.text.contains("Общая рассылка"))
async def btn_broadcast(message: Message, state: FSMContext) -> None:
    """
    Запуск общей рассылки с кнопки.
    """
    if not _is_admin(message.from_user.id):
        return
    await _start_broadcast(message, state)


# ---------- Общая рассылка (любые сообщения) ----------


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    """
    Запуск общей рассылки через команду.
    """
    if not _is_admin(message.from_user.id):
        return
    await _start_broadcast(message, state)


async def _start_broadcast(message: Message, state: FSMContext) -> None:
    """
    Общее начало сценария рассылки.
    """
    await state.set_state(AdminBroadcastStates.waiting_broadcast)
    await message.answer(
        "📢 Режим общей рассылки.\n\n"
        "Отправьте сообщение, которое нужно разослать всем пользователям из таблицы.\n"
        "Можно переслать сообщение из другого чата, с медиа, кнопками и т.д.\n\n"
        "Для отмены напишите «Отмена» или используйте команду /cancel_broadcast."
    )


@router.message(AdminBroadcastStates.waiting_broadcast, F.text.casefold() == "отмена")
@router.message(AdminBroadcastStates.waiting_broadcast, Command("cancel_broadcast"))
async def broadcast_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Режим общей рассылки отменён.")


@router.message(AdminBroadcastStates.waiting_broadcast)
async def broadcast_do(message: Message, state: FSMContext) -> None:
    """
    Берём ЛЮБОЕ сообщение админа в этом состоянии и копируем его всем пользователям из таблицы.
    """
    if not _is_admin(message.from_user.id):
        await state.clear()
        return

    participants = await _load_participants_or_error(message)
    if participants is None:
        await state.clear()
        return

    # По вашей формулировке — «всем кто есть в таблице».
    # Поэтому не фильтруем по active/validated, а шлём всем, у кого есть tg_id.
    targets: List[Participant] = [
        p for p in participants
        if p.tg_id
    ]

    if not targets:
        await message.answer("В таблице нет ни одного участника с Telegram ID.")
        await state.clear()
        return

    await message.answer(
        f"Начинаю рассылку сообщения всем пользователям из таблицы.\n"
        f"Получателей: {len(targets)}."
    )

    sent = 0
    failed = 0

    for p in targets:
        try:
            # Копируем сообщение как есть (текст/медиа/кнопки и т.д.)
            await message.bot.copy_message(
                chat_id=p.tg_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning("Failed to broadcast message to %s: %s", p.tg_id, e)

    await state.clear()

    await message.answer(
        "Общая рассылка завершена.\n"
        f"Сообщений успешно отправлено: {sent}\n"
        f"Ошибок отправки: {failed}"
    )


# ---------- Список участников ----------


def _format_participant_line(p: Participant) -> str:
    status = "✅" if p.validated else "⏳"
    active = "🟢" if p.active else "⚪️"
    return (
        f"{status}{active} <b>{p.full_name}</b> — {p.department} "
        f"({p.phone}) [<code>{p.tg_id}</code>]"
    )


async def _send_participants_list(message: Message, only_validated: bool) -> None:
    participants = await _load_participants_or_error(message)
    if participants is None:
        return

    filtered: List[Participant] = []
    for p in participants:
        if not p.active:
            continue
        if only_validated and not p.validated:
            continue
        filtered.append(p)

    if not filtered:
        if only_validated:
            await message.answer("Подтверждённых активных участников нет.")
        else:
            await message.answer("Активных участников нет.")
        return

    title = "✅ Подтверждённые участники:" if only_validated else "👥 Активные участники:"
    await message.answer(
        f"{title}\nВсего: <b>{len(filtered)}</b>."
    )

    chunk: List[str] = []
    for p in filtered:
        chunk.append(_format_participant_line(p))
        if len(chunk) >= 30:
            await message.answer("\n".join(chunk))
            chunk = []
    if chunk:
        await message.answer("\n".join(chunk))


# ---------- Жеребьёвка и рассылка (получатели) ----------


@router.message(Command("draw"))
async def cmd_draw(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await _handle_draw(message)


@router.message(Command("notify"))
async def cmd_notify(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await _handle_notify(message)


async def _handle_draw(message: Message) -> None:
    """
    /draw или кнопка «Провести жеребьёвку»:
    формируем пары и отправляем ПЕРВОЕ уведомление участникам.
    """
    participants = await _load_participants_or_error(message)
    if participants is None:
        return

    eligible: list[Participant] = [
        p for p in participants
        if p.active and p.validated
    ]

    if len(eligible) < 2:
        await message.answer(
            "Жеребьёвка невозможна: подтверждённых участников меньше двух."
        )
        return

    if any(p.recipient_tg_id for p in eligible):
        await message.answer(
            "Похоже, жеребьёвка уже проводилась (у некоторых участников уже есть получатель).\n"
            "Во избежание конфликтов повторный запуск /draw заблокирован."
        )
        return

    random.shuffle(eligible)

    n = len(eligible)
    ps = ParticipantsService()
    for i, santa in enumerate(eligible):
        receiver = eligible[(i + 1) % n]

        santa.recipient_tg_id = receiver.tg_id
        santa.recipient_name = receiver.full_name
        santa.recipient_info = (
            f"Отдел: {receiver.department}\n"
            f"Телефон: {receiver.phone}"
        )
        santa.notified = False

        ps.upsert_participant(santa)

    await message.answer(
        f"Жеребьёвка завершена.\n"
        f"Участников в игре: {n}.\n"
        f"Начинаю рассылку результатов…"
    )

    sent, failed = await _notify_participants(
        message,
        only_notified_false=True,
        reminder=False,
    )

    await message.answer(
        "Рассылка завершена.\n"
        f"Всего участников: {n}\n"
        f"Уведомлено: {sent}\n"
        f"Ошибок отправки: {failed}"
    )


async def _handle_notify(message: Message) -> None:
    """
    /notify или кнопка «Разослать результаты»:
    напоминание всем участникам, у кого уже есть получатель.
    """
    sent, failed = await _notify_participants(
        message,
        only_notified_false=False,
        reminder=True,
    )

    await message.answer(
        "Напоминание отправлено.\n"
        f"Сообщений отправлено: {sent}\n"
        f"Ошибок отправки: {failed}"
    )


async def _notify_participants(
    message: Message,
    *,
    only_notified_false: bool,
    reminder: bool,
) -> Tuple[int, int]:
    """
    Рассылка уведомлений участникам о их получателях.
    """
    participants = await _load_participants_or_error(message)
    if participants is None:
        return 0, 0

    sent = 0
    failed = 0
    ps = ParticipantsService()

    for p in participants:
        if not p.active or not p.validated:
            continue
        if not p.recipient_tg_id or not p.recipient_name:
            continue
        if only_notified_false and p.notified:
            continue

        if reminder:
            text = (
                "🔔 Напоминаем: вы участвуете в игре «Тайный Санта»!\n\n"
                "Ваш получатель:\n"
                f"ФИО: <b>{p.recipient_name}</b>\n"
                f"{(p.recipient_info or '')}\n\n"
                "Пожалуйста, не забудьте подготовить и вручить подарок вовремя. "
                "Сохраняйте интригу и не раскрывайте свою личность раньше времени 🙂"
            )
        else:
            text = (
                "🎁 Ваш получатель в игре «Тайный Санта»:\n\n"
                f"ФИО: <b>{p.recipient_name}</b>\n"
                f"{(p.recipient_info or '')}\n\n"
                "Помните про лимит бюджета и дату обмена подарками!"
            )

        try:
            await message.bot.send_message(
                chat_id=p.tg_id,
                text=text,
            )
            if not p.notified:
                p.notified = True
                ps.upsert_participant(p)
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning("Failed to notify participant %s: %s", p.tg_id, e)

    return sent, failed


# ---------- Валидация через инлайн-кнопки ----------


@router.callback_query(F.data.startswith("adm_"))
async def admin_validation_callback(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    if not _is_admin(user_id):
        await callback.answer("Недостаточно прав для этого действия.", show_alert=True)
        return

    data = callback.data or ""
    try:
        action, tg_id_str = data.split(":", 1)
        target_tg_id = int(tg_id_str)
    except Exception:
        await callback.answer("Некорректные данные кнопки.", show_alert=True)
        return

    ps = ParticipantsService()
    participant = ps.get_by_tg_id(target_tg_id)

    if participant is None:
        await callback.answer("Участник не найден.", show_alert=True)
        return

    if action == "adm_approve":
        participant.validated = True
        participant.active = True
        participant.validator_tg_id = user_id
        participant.validation_ts = utc_now_iso()

        ps.upsert_participant(participant)

        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        await callback.answer("Анкета подтверждена ✅", show_alert=False)

        try:
            await callback.bot.send_message(
                chat_id=target_tg_id,
                text=(
                    "✅ Ваша анкета в игре «Тайный Санта» подтверждена.\n"
                    "Скоро вы получите информацию о получателе подарка."
                ),
            )
        except Exception as e:
            logger.warning("Failed to notify participant %s about approval: %s", target_tg_id, e)

    elif action == "adm_reject":
        participant.validated = False
        participant.active = False
        participant.validator_tg_id = user_id
        participant.validation_ts = utc_now_iso()

        ps.upsert_participant(participant)

        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        await callback.answer("Анкета отклонена ❌", show_alert=False)

        try:
            await callback.bot.send_message(
                chat_id=target_tg_id,
                text=(
                    "❌ Ваша анкета в игре «Тайный Санта» отклонена.\n"
                    "Свяжитесь, пожалуйста, с организатором для уточнения причин."
                ),
            )
        except Exception as e:
            logger.warning("Failed to notify participant %s about rejection: %s", target_tg_id, e)

    else:
        await callback.answer("Неизвестное действие.", show_alert=True)
