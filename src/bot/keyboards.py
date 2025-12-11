# src/bot/keyboards.py
from __future__ import annotations

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from .schemas import PollQuestion

# ---------- Пользовательские клавиатуры ----------


def start_new_user_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎄 Принять участие",
                    callback_data="register_start",
                )
            ]
        ]
    )


def existing_profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Изменить данные",
                    callback_data="profile_edit",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🚪 Выйти из игры",
                    callback_data="leave_game",
                )
            ],
        ]
    )


def user_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🧾 Мой профиль"),
                KeyboardButton(text="✏️ Изменить данные"),
            ],
            [
                KeyboardButton(text="🚪 Выйти из игры"),
                KeyboardButton(text="ℹ️ Правила"),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def quiz_options_kb(poll: PollQuestion) -> InlineKeyboardMarkup:
    """
    Клавиатура для вариантов викторины.
    """
    buttons = []
    for idx, option in enumerate(poll.options):
        buttons.append([
            InlineKeyboardButton(
                text=f"{idx + 1}. {option}",
                callback_data=f"quiz_answer:{poll.poll_id}:{idx}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ---------- Админские клавиатуры ----------


def admin_main_kb() -> ReplyKeyboardMarkup:
    """
    Меню администратора.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👥 Участники"),
                KeyboardButton(text="✅ Подтверждённые"),
            ],
            [
                KeyboardButton(text="🎲 Провести жеребьёвку"),
                KeyboardButton(text="📨 Разослать результаты"),
            ],
            [
                KeyboardButton(text="📢 Общая рассылка"),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def admin_participant_actions_kb(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"adm_approve:{tg_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"adm_reject:{tg_id}",
                ),
            ]
        ]
    )
