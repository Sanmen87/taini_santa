import asyncio
import logging
import ssl

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from .config import get_settings
from .logging_config import setup_logging
from .handlers import common, user, admin


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    settings = get_settings()

    # ⚠ ОТКЛЮЧАЕМ проверку сертификатов — только для временного теста!
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    session = AiohttpSession()
    session._connector_init["ssl"] = ssl_context

    bot = Bot(
        token=settings.telegram.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(common.router)
    dp.include_router(user.router)
    dp.include_router(admin.router)

    logger.info("Starting bot")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
