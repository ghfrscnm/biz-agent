"""Цикл агента: модель → (инструменты → модель)* → ответ клиенту."""
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI

from .storage import Storage
from .tools import TOOL_SCHEMAS, Tools

log = logging.getLogger("agent")

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
FALLBACK = "Сейчас не могу ответить — передам вопрос менеджеру, он скоро напишет."


class Agent:
    def __init__(self, client: AsyncOpenAI, model: str, tools: Tools, storage: Storage,
                 system_prompt: str, business_name: str, history_limit: int = 20,
                 max_steps: int = 6, tz: str = "Asia/Yekaterinburg"):
        self.client, self.model, self.tools, self.storage = client, model, tools, storage
        self.system_template = system_prompt
        self.business_name = business_name
        self.history_limit, self.max_steps, self.tz = history_limit, max_steps, tz

    def _system(self) -> str:
        now = datetime.now(ZoneInfo(self.tz))
        return (self.system_template
                .replace("{business_name}", self.business_name)
                .replace("{now}", f"{now:%d.%m.%Y %H:%M}, {WEEKDAYS[now.weekday()]}"))

    async def reply(self, chat_id: int, text: str, user: dict | None = None) -> str:
        user = user or {}
        history = self.storage.history(chat_id, self.history_limit)
        messages = [{"role": "system", "content": self._system()}, *history,
                    {"role": "user", "content": text}]
        self.storage.add_message(chat_id, "user", text)

        answer = None
        for step in range(self.max_steps):
            resp = await self.client.chat.completions.create(
                model=self.model, messages=messages, tools=TOOL_SCHEMAS,
                tool_choice="auto", temperature=0.3,
            )
            msg = resp.choices[0].message
            calls = msg.tool_calls or []
            if not calls:
                answer = (msg.content or "").strip()
                break

            messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [{"id": c.id, "type": "function",
                                "function": {"name": c.function.name,
                                             "arguments": c.function.arguments}} for c in calls],
            })
            for c in calls:
                try:
                    args = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                log.info("chat=%s step=%s tool=%s args=%s", chat_id, step, c.function.name, args)
                result = await self.tools.call(chat_id, c.function.name, args, user)
                messages.append({"role": "tool", "tool_call_id": c.id, "content": result})

        if not answer:
            answer = FALLBACK
        self.storage.add_message(chat_id, "assistant", answer)
        return answer
