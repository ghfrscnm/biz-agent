"""Инструменты агента. Модель сама решает, какой вызвать и когда.

Чтобы добавить инструмент: опишите схему в TOOL_SCHEMAS и напишите метод
с тем же именем в классе Tools. Больше ничего менять не нужно.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

import httpx

from .kb import KnowledgeBase
from .storage import Storage

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "Поиск по базе знаний бизнеса: цены, абонементы, правила, адрес, "
                "тренеры, что взять на тренировку и т.п. Вызывай перед любым "
                "фактическим ответом. Не выдумывай то, чего нет в результатах."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Поисковый запрос"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule",
            "description": "Расписание групповых тренировок. Можно отфильтровать по дню недели и/или группе.",
            "parameters": {
                "type": "object",
                "properties": {
                    "weekday": {
                        "type": "string",
                        "enum": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
                        "description": "День недели, если клиент спросил про конкретный день",
                    },
                    "group": {
                        "type": "string",
                        "description": "Часть названия группы: 'дети', 'новички', 'взрослые', 'женская' и т.п.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_lead",
            "description": (
                "Записать клиента на пробную тренировку или оставить заявку. Вызывай, "
                "только когда клиент дал имя и телефон и согласился записаться."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "interest": {"type": "string", "description": "Что хочет: пробная, абонемент, персональные и т.п."},
                    "preferred_time": {"type": "string", "description": "Удобный день/время или группа"},
                    "comment": {"type": "string", "description": "Важные детали: возраст ребёнка, опыт, травмы"},
                },
                "required": ["name", "phone", "interest"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_manager",
            "description": (
                "Передать диалог живому менеджеру. Вызывай, если: клиент просит человека; "
                "жалоба, конфликт, возврат денег; травма или медицинский вопрос; "
                "вопрос не решается по базе знаний."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "enum": ["просит человека", "жалоба", "возврат", "здоровье", "нет ответа в базе", "другое"]},
                    "summary": {"type": "string", "description": "Суть вопроса в 1–2 предложениях для менеджера"},
                    "urgency": {"type": "string", "enum": ["low", "normal", "high"]},
                },
                "required": ["reason", "summary", "urgency"],
            },
        },
    },
]

PHONE_RE = re.compile(r"\d")


def normalize_phone(raw: str) -> str | None:
    digits = "".join(PHONE_RE.findall(raw or ""))
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    if 10 <= len(digits) <= 15:
        return "+" + digits
    return None


Notifier = Callable[[str], Awaitable[None]]


@dataclass
class Tools:
    storage: Storage
    kb: KnowledgeBase
    schedule_path: Path
    notify_manager: Notifier | None = None
    sheets_webhook_url: str = ""
    _schedule: list[dict] = field(default_factory=list, init=False)

    def __post_init__(self):
        if self.schedule_path.exists():
            self._schedule = json.loads(self.schedule_path.read_text(encoding="utf-8"))

    async def call(self, chat_id: int, name: str, args: dict, user: dict) -> str:
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_") or name == "call":
            result = json.dumps({"error": f"неизвестный инструмент {name}"}, ensure_ascii=False)
        else:
            try:
                result = await fn(chat_id=chat_id, user=user, **args)
            except TypeError as e:
                result = json.dumps({"error": f"неверные аргументы: {e}"}, ensure_ascii=False)
            except Exception as e:  # инструмент не должен ронять агента
                result = json.dumps({"error": f"ошибка инструмента: {e}"}, ensure_ascii=False)
        self.storage.add_trace(chat_id, name, args, result)
        return result

    # ---------- инструменты ----------

    async def search_knowledge(self, chat_id: int, user: dict, query: str) -> str:
        hits = self.kb.search(query, k=3)
        if not hits:
            return json.dumps({"found": False, "note": "В базе знаний ничего не нашлось."}, ensure_ascii=False)
        return json.dumps(
            {"found": True, "results": [
                {"source": c.source, "section": c.title, "text": c.text} for c, _ in hits
            ]},
            ensure_ascii=False,
        )

    async def get_schedule(self, chat_id: int, user: dict, weekday: str | None = None,
                           group: str | None = None) -> str:
        rows = self._schedule
        if weekday:
            rows = [r for r in rows if r["weekday"] == weekday]
        if group:
            g = group.lower()[:5]
            rows = [r for r in rows if g in r["group"].lower()]
        return json.dumps({"count": len(rows), "classes": rows}, ensure_ascii=False)

    async def create_lead(self, chat_id: int, user: dict, name: str, phone: str, interest: str,
                          preferred_time: str = "", comment: str = "") -> str:
        norm = normalize_phone(phone)
        if not norm:
            return json.dumps({"ok": False, "error": "Телефон похож на неверный — переспроси номер."}, ensure_ascii=False)
        fields = dict(name=name.strip(), phone=norm, interest=interest,
                      preferred_time=preferred_time, comment=comment)
        lead_id = self.storage.add_lead(chat_id, **fields)

        synced = False
        if self.sheets_webhook_url:
            try:
                async with httpx.AsyncClient(timeout=10, follow_redirects=True) as http:
                    r = await http.post(self.sheets_webhook_url, json={
                        "lead_id": lead_id, "telegram": user.get("username") or chat_id, **fields
                    })
                    synced = r.status_code == 200
            except httpx.HTTPError:
                synced = False

        if self.notify_manager:
            who = f"@{user['username']}" if user.get("username") else f"id {chat_id}"
            await self.notify_manager(
                f"🟢 Новая заявка #{lead_id}\n"
                f"Имя: {fields['name']}\nТелефон: {norm}\nTelegram: {who}\n"
                f"Хочет: {interest}\nКогда: {preferred_time or '—'}\nКомментарий: {comment or '—'}"
            )
        return json.dumps({"ok": True, "lead_id": lead_id, "saved_to_sheet": synced}, ensure_ascii=False)

    async def escalate_to_manager(self, chat_id: int, user: dict, reason: str, summary: str,
                                  urgency: str = "normal") -> str:
        hid = self.storage.add_handoff(chat_id, reason, summary, urgency)
        notified = False
        if self.notify_manager:
            icon = {"high": "🔴", "normal": "🟡", "low": "⚪"}.get(urgency, "🟡")
            who = f"@{user['username']}" if user.get("username") else f"id {chat_id}"
            name = user.get("first_name") or ""
            await self.notify_manager(
                f"{icon} Нужен менеджер (#{hid})\nКлиент: {name} {who}\n"
                f"Причина: {reason}\nСуть: {summary}"
            )
            notified = True
        return json.dumps({"ok": True, "handoff_id": hid, "manager_notified": notified}, ensure_ascii=False)
