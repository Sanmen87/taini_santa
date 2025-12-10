from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router()


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    await message.answer("pong")
