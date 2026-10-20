"""Сборка агента из конфига — общая для Telegram-бота и консоли."""
from openai import AsyncOpenAI

from .config import config
from .core import Agent
from .kb import KnowledgeBase
from .storage import Storage
from .tools import Notifier, Tools


def build_agent(notify_manager: Notifier | None = None) -> tuple[Agent, Storage]:
    if not config.llm_api_key:
        raise SystemExit("Нет OPENROUTER_API_KEY в .env")
    storage = Storage(config.db_path)
    kb = KnowledgeBase(config.kb_dir)
    tools = Tools(
        storage=storage, kb=kb, schedule_path=config.kb_dir / "schedule.json",
        notify_manager=notify_manager, sheets_webhook_url=config.sheets_webhook_url,
    )
    client = AsyncOpenAI(api_key=config.llm_api_key, base_url=config.llm_base_url)
    agent = Agent(
        client=client, model=config.model, tools=tools, storage=storage,
        system_prompt=config.prompt_path.read_text(encoding="utf-8"),
        business_name=config.business_name, history_limit=config.history_limit,
        max_steps=config.max_agent_steps,
    )
    return agent, storage
