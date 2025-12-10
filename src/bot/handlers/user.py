# src/bot/handlers/user.py
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from ..config import get_settings

from ..keyboards import (
    start_new_user_kb,
    existing_profile_kb,
    cancel_kb,
    user_main_kb,
    admin_participant_actions_kb,
)

from ..services.participants_service import ParticipantsService
from ..schemas import Participant
from ..texts import (
    START_NEW_USER,
    PROFILE_TEMPLATE,
    REG_FIO_ASK,
    REG_DEPARTMENT_ASK,
    REG_PHONE_ASK,
    REG_CANCELLED,
    REG_FINISHED,
    LEAVE_CONFIRM,
    PROFILE_NOT_FOUND,
)

logger = logging.getLogger(__name__)
router = Router()

# Только кириллица, пробелы и дефисы, разумная длина
FIO_RE = re.compile(r"^[А-Яа-яЁё\s\-]{5,100}$")


class RegistrationStates(StatesGroup):
    fio = State()
    department = State()
    phone = State()


@dataclass
class RegistrationData:
    fio: str
    department: str
    phone: str


def _format_bool(v: bool) -> str:
    return "Да" if v else "Нет"


def _normalize_russian_phone(text: str) -> str | None:
    """
    Приводим номер к виду +7XXXXXXXXXX.
    Допускаем ввод в формате:
    - +7XXXXXXXXXX
    - 8XXXXXXXXXX
    - с пробелами, скобками, дефисами.
    Возвращает нормализованный номер либо None, если номер некорректен.
    """
    digits = re.sub(r"\D", "", text or "")
    # Ожидаем 11 цифр, первый символ 7 или 8
    if len(digits) != 11 or digits[0] not in ("7", "8"):
        return None

    # Если начали с 8 — приводим к 7
    if digits[0] == "8":
        digits = "7" + digits[1:]

    return "+7" + digits[1:]


def _looks_like_phone(text: str) -> bool:
    """
    Очень грубая эвристика: если в строке 10+ цифр — это, скорее всего, номер телефона.
    Используем, чтобы не записать номер в поле «Отдел».
    """
    digits = re.sub(r"\D", "", text or "")
    return len(digits) >= 10


# ---------- Команды участника ----------

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """
    Старт: проверяем, есть ли участник в таблице.
    """
    await state.clear()
    ps = ParticipantsService()
    user_id = message.from_user.id
    participant = ps.get_by_tg_id(user_id)

    if participant is None:
        # Новый пользователь
        await message.answer(START_NEW_USER, reply_markup=start_new_user_kb())
    else:
        # Уже зарегистрирован
        text = PROFILE_TEMPLATE.format(
            full_name=participant.full_name,
            department=participant.department,
            phone=participant.phone,
            active=_format_bool(participant.active),
            validated=_format_bool(participant.validated),
        )
        await message.answer(text, reply_markup=existing_profile_kb())


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    ps = ParticipantsService()
    user_id = message.from_user.id
    participant = ps.get_by_tg_id(user_id)

    if participant is None:
        await message.answer(PROFILE_NOT_FOUND)
        return

    text = PROFILE_TEMPLATE.format(
        full_name=participant.full_name,
        department=participant.department,
        phone=participant.phone,
        active=_format_bool(participant.active),
        validated=_format_bool(participant.validated),
    )
    await message.answer(text, reply_markup=existing_profile_kb())


@router.message(Command("leave"))
async def cmd_leave(message: Message) -> None:
    ps = ParticipantsService()
    user_id = message.from_user.id
    updated = ps.set_active(user_id, False)
    if updated is None:
        await message.answer(PROFILE_NOT_FOUND)
        return

    await message.answer(LEAVE_CONFIRM)


# ---------- Callback-и с кнопок ----------

@router.callback_query(F.data == "register_start")
async def cq_register_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RegistrationStates.fio)
    await callback.message.answer(REG_FIO_ASK, reply_markup=cancel_kb())
    await callback.answer()


@router.callback_query(F.data == "profile_edit")
async def cq_profile_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Повторно проходим форму регистрации, при этом участник остаётся (active = TRUE).
    """
    await state.set_state(RegistrationStates.fio)
    await callback.message.answer(REG_FIO_ASK, reply_markup=cancel_kb())
    await callback.answer()


@router.callback_query(F.data == "leave_game")
async def cq_leave_game(callback: CallbackQuery) -> None:
    ps = ParticipantsService()
    user_id = callback.from_user.id
    updated = ps.set_active(user_id, False)
    if updated is None:
        await callback.message.answer(PROFILE_NOT_FOUND)
    else:
        await callback.message.answer(LEAVE_CONFIRM)
    await callback.answer()


# ---------- Шаги регистрации (FSM) ----------

@router.message(RegistrationStates.fio, F.text.casefold() == "отмена")
@router.message(RegistrationStates.department, F.text.casefold() == "отмена")
@router.message(RegistrationStates.phone, F.text.casefold() == "отмена")
async def reg_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(REG_CANCELLED, reply_markup=None)


@router.message(RegistrationStates.fio)
async def reg_fio(message: Message, state: FSMContext) -> None:
    fio = (message.text or "").strip()
    if not fio:
        await message.answer("Пожалуйста, введите ФИО одним сообщением или нажмите «Отмена».")
        return

    if not FIO_RE.match(fio):
        await message.answer(
            "ФИО должно содержать только буквы кириллицы, пробелы и дефисы.\n"
            "Пример: <b>Иванов Иван Иванович</b>."
        )
        return

    await state.update_data(fio=fio)
    await state.set_state(RegistrationStates.department)
    await message.answer(REG_DEPARTMENT_ASK)


@router.message(RegistrationStates.department)
async def reg_department(message: Message, state: FSMContext) -> None:
    department = (message.text or "").strip()
    if not department:
        await message.answer("Пожалуйста, укажите отдел или нажмите «Отмена».")
        return

    if _looks_like_phone(department):
        await message.answer(
            "Похоже, вы указали номер телефона.\n"
            "Здесь нужно написать название отдела, например: <b>Отдел разработки</b>."
        )
        return

    if len(department) < 3:
        await message.answer(
            "Название отдела слишком короткое. Уточните, пожалуйста, например: "
            "<b>Отдел маркетинга</b> или <b>Отдел продаж</b>."
        )
        return

    await state.update_data(department=department)
    await state.set_state(RegistrationStates.phone)
    await message.answer(REG_PHONE_ASK)


@router.message(RegistrationStates.phone)
async def reg_phone(message: Message, state: FSMContext) -> None:
    raw_phone = (message.text or "").strip()
    normalized_phone = _normalize_russian_phone(raw_phone)

    if not normalized_phone:
        await message.answer(
            "Номер не похож на российский номер телефона.\n"
            "Укажите, пожалуйста, номер в формате <b>+7XXXXXXXXXX</b> или <b>8XXXXXXXXXX</b>."
        )
        return

    await state.update_data(phone=normalized_phone)
    data = await state.get_data()
    await state.clear()

    # Сохраняем/обновляем участника
    ps = ParticipantsService()
    user = message.from_user

    participant = ps.get_by_tg_id(user.id)
    if participant is None:
        # Новый участник
        participant = Participant(
            tg_id=user.id,
            username=user.username,
            full_name=data["fio"],
            department=data["department"],
            phone=data["phone"],
            active=True,
            validated=False,
        )
    else:
        # Обновление существующего профиля
        participant.full_name = data["fio"]
        participant.department = data["department"]
        participant.phone = data["phone"]
        participant.active = True  # повторная регистрация → активируем

    # ВАЖНО: сохраняем и для новых, и для существующих
    ps.upsert_participant(participant)

    await message.answer(REG_FINISHED, reply_markup=None)

    # -------- Уведомление админ-чата о новой/обновлённой анкете --------
    settings = get_settings()
    admin_chat_id = settings.telegram.admin_chat_id
    logger.info("admin_chat_id from settings: %r", admin_chat_id)

    if admin_chat_id:
        text = (
            "🆕 Новая анкета участника Тайного Санты\n\n"
            f"ФИО: <b>{participant.full_name}</b>\n"
            f"Отдел: <b>{participant.department}</b>\n"
            f"Телефон: <b>{participant.phone}</b>\n"
            f"Username: @{participant.username or '—'}\n"
            f"Telegram ID: <code>{participant.tg_id}</code>\n\n"
            "Выберите действие:"
        )

        kb = admin_participant_actions_kb(participant.tg_id)

        try:
            await message.bot.send_message(
                chat_id=admin_chat_id,
                text=text,
                reply_markup=kb,
            )
            logger.info(
                "Sent participant %s to admin chat %s",
                participant.tg_id,
                admin_chat_id,
            )
        except Exception as e:
            logger.warning(
                "Failed to send participant %s to admin chat %s: %s",
                participant.tg_id,
                admin_chat_id,
                e,
            )
    else:
        logger.warning("admin_chat_id is not set; skip sending participant to admin chat")

