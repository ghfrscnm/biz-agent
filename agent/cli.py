"""Чат с агентом в терминале — для отладки и демо без Telegram.
Запуск: python -m agent.cli   (выход: Ctrl+C, сброс: /reset)
"""
import asyncio

from .app import build_agent

CHAT_ID = 1


async def main() -> None:
    async def notify(text: str) -> None:
        print(f"\n  [→ менеджеру]\n  " + text.replace("\n", "\n  ") + "\n")

    agent, storage = build_agent(notify)
    storage.reset(CHAT_ID)
    print("Агент готов. Пишите (Ctrl+C — выход, /reset — сначала).\n")
    while True:
        try:
            text = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            continue
        if text == "/reset":
            storage.reset(CHAT_ID)
            print("— история очищена —\n")
            continue
        before = len(storage.last_traces(CHAT_ID, 1000))
        answer = await agent.reply(CHAT_ID, text, {"username": "cli_user", "first_name": "Тест"})
        new = storage.last_traces(CHAT_ID, len(storage.last_traces(CHAT_ID, 1000)) - before)
        for t in reversed(new):
            print(f"  · {t['tool']}({t['args']})")
        print(f"Агент: {answer}\n")


if __name__ == "__main__":
    asyncio.run(main())
