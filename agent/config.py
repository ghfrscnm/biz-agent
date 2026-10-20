"""Настройки из .env. Всё, что меняется между бизнесами, — здесь и в папке kb/."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    llm_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    model: str = os.getenv("MODEL", "openai/gpt-4o-mini")

    business_name: str = os.getenv("BUSINESS_NAME", "Клуб кикбоксинга «Удар»")
    manager_chat_id: int = int(os.getenv("MANAGER_CHAT_ID", "0") or 0)
    sheets_webhook_url: str = os.getenv("SHEETS_WEBHOOK_URL", "")

    kb_dir: Path = ROOT / os.getenv("KB_DIR", "kb")
    db_path: Path = ROOT / os.getenv("DB_PATH", "data/agent.db")
    prompt_path: Path = ROOT / "prompts" / "system.md"

    history_limit: int = int(os.getenv("HISTORY_LIMIT", "20"))
    max_agent_steps: int = int(os.getenv("MAX_AGENT_STEPS", "6"))


config = Config()
