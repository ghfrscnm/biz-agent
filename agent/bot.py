"""Telegram-бот. Запуск: python -m agent.bot"""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .app import build_agent
from .config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

GREETING = (
    "Привет! Я ИИ-администратор «{name}». Подскажу цены и расписание, "
    "запишу на бесплатную пробную тренировку или позову менеджера. Что интересует?"
)


async def main() -> None:
    if not config.telegram_token:
        raise SystemExit("Нет TELEGRAM_BOT_TOKEN в .env")
    bot = Bot(config.telegram_token)
    dp = Dispatcher()

    async def notify_manager(text: str) -> None:
        if config.manager_chat_id:
            await bot.send_message(config.manager_chat_id, text)
        else:
            log.warning("MANAGER_CHAT_ID не задан, уведомление: %s", text)

    agent, storage = build_agent(notify_manager)
    is_manager = F.chat.id == config.manager_chat_id

    @dp.message(CommandStart())
    async def start(m: Message):
        storage.reset(m.chat.id)
        await m.answer(GREETING.format(name=config.business_name))

    @dp.message(Command("reset"))
    async def reset(m: Message):
        storage.reset(m.chat.id)
        await m.answer("Начнём заново. Чем помочь?")

    @dp.message(Command("id"))
    async def my_id(m: Message):
        await m.answer(f"chat_id: {m.chat.id}")

    @dp.message(Command("leads"), is_manager)
    async def leads(m: Message):
        rows = storage.last_leads(10)
        if not rows:
            return await m.answer("Заявок пока нет.")
        lines = [f"#{r['id']} {datetime.fromtimestamp(r['ts']):%d.%m %H:%M} · {r['name']} · "
                 f"{r['phone']} · {r['interest']} · {r['preferred_time'] or '—'}" for r in rows]
        await m.answer("Последние заявки:\n" + "\n".join(lines))

    @dp.message(Command("trace"), is_manager)
    async def trace(m: Message):
        rows = storage.last_traces(limit=10)
        if not rows:
            return await m.answer("Вызовов инструментов пока не было.")
        lines = [f"{datetime.fromtimestamp(r['ts']):%H:%M:%S} chat {r['chat_id']} → "
                 f"{r['tool']}({r['args']})" for r in reversed(rows)]
        await m.answer("Последние действия агента:\n" + "\n".join(lines))

    @dp.message(F.text)
    async def chat(m: Message):
        await bot.send_chat_action(m.chat.id, ChatAction.TYPING)
        user = {"username": m.from_user.username, "first_name": m.from_user.first_name}
        try:
            answer = await agent.reply(m.chat.id, m.text, user)
        except Exception:
            log.exception("agent failed")
            answer = "Что-то пошло не так. Попробуйте ещё раз через минуту."
        await m.answer(answer)

    @dp.message()
    async def other(m: Message):
        await m.answer("Пока понимаю только текст. Напишите, пожалуйста, словами 🙂")

    log.info("Бот запущен, модель %s", config.model)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
