"""Офлайн-тесты: без ключей и сети. Модель подменена сценарием."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from agent.core import Agent
from agent.kb import KnowledgeBase
from agent.storage import Storage
from agent.tools import Tools, normalize_phone

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "kb"


def tool_call(id_, name, args):
    return NS(id=id_, function=NS(name=name, arguments=json.dumps(args, ensure_ascii=False)))


class FakeLLM:
    """Отдаёт заранее заданные ответы по очереди и запоминает, что ему прислали."""

    def __init__(self, script):
        self.script, self.seen = list(script), []
        self.chat = NS(completions=NS(create=self._create))

    async def _create(self, **kw):
        self.seen.append(kw["messages"])
        step = self.script.pop(0)
        msg = NS(content=step.get("content"), tool_calls=step.get("tool_calls"))
        return NS(choices=[NS(message=msg)])


def make(script, notes=None):
    storage = Storage(":memory:")

    async def notify(text):
        if notes is not None:
            notes.append(text)

    tools = Tools(storage=storage, kb=KnowledgeBase(KB), schedule_path=KB / "schedule.json",
                  notify_manager=notify)
    llm = FakeLLM(script)
    agent = Agent(client=llm, model="fake", tools=tools, storage=storage,
                  system_prompt="Бизнес {business_name}, сейчас {now}", business_name="Тест")
    return agent, storage, llm


# ---------- база знаний ----------

def test_kb_finds_prices():
    kb = KnowledgeBase(KB)
    top = kb.search("сколько стоит абонемент на 8 занятий")[0][0]
    assert "4 500" in top.text or "4 000" in top.text


def test_kb_finds_what_to_bring():
    top = KnowledgeBase(KB).search("что взять с собой на первую тренировку")[0][0]
    assert "форму" in top.text


def test_kb_empty_for_nonsense():
    assert KnowledgeBase(KB).search("квантовая хромодинамика") == []


# ---------- инструменты ----------

@pytest.mark.parametrize("raw,expected", [
    ("8 912 345-67-89", "+79123456789"),
    ("+7 (912) 345 67 89", "+79123456789"),
    ("9123456789", "+79123456789"),
    ("123", None),
])
def test_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.asyncio
async def test_schedule_filter():
    agent, _, _ = make([])
    res = json.loads(await agent.tools.call(1, "get_schedule", {"weekday": "вт", "group": "женская"}, {}))
    assert res["count"] == 1 and res["classes"][0]["time"] == "19:00–20:15"


@pytest.mark.asyncio
async def test_unknown_tool_does_not_crash():
    agent, storage, _ = make([])
    res = json.loads(await agent.tools.call(1, "rm_rf", {}, {}))
    assert "error" in res
    assert storage.last_traces(1)[0]["tool"] == "rm_rf"


@pytest.mark.asyncio
async def test_bad_phone_rejected():
    agent, storage, _ = make([])
    res = json.loads(await agent.tools.call(1, "create_lead",
                                            {"name": "Иван", "phone": "12", "interest": "пробная"}, {}))
    assert res["ok"] is False and storage.last_leads() == []


# ---------- цикл агента ----------

@pytest.mark.asyncio
async def test_agent_uses_kb_then_answers():
    agent, storage, llm = make([
        {"tool_calls": [tool_call("c1", "search_knowledge", {"query": "цена пробной"})]},
        {"content": "Пробная тренировка бесплатная 🙂"},
    ])
    answer = await agent.reply(42, "Сколько стоит пробная?")
    assert answer == "Пробная тренировка бесплатная 🙂"
    # результат инструмента вернулся модели на втором шаге
    tool_msg = llm.seen[1][-1]
    assert tool_msg["role"] == "tool" and "бесплатная" in tool_msg["content"]
    assert [m["role"] for m in storage.history(42, 10)] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_agent_creates_lead_and_notifies_manager():
    notes = []
    agent, storage, _ = make([
        {"tool_calls": [tool_call("c1", "create_lead", {
            "name": "Иван", "phone": "8 912 345 67 89", "interest": "пробная",
            "preferred_time": "вт 20:15 новички"})]},
        {"content": "Записал вас, Иван!"},
    ], notes)
    await agent.reply(7, "Иван, 89123456789, запишите во вторник", {"username": "ivan"})
    lead = storage.last_leads()[0]
    assert lead["phone"] == "+79123456789"
    assert notes and "Новая заявка" in notes[0] and "@ivan" in notes[0]


@pytest.mark.asyncio
async def test_agent_escalates():
    notes = []
    agent, _, _ = make([
        {"tool_calls": [tool_call("c1", "escalate_to_manager", {
            "reason": "возврат", "summary": "Хочет вернуть деньги за абонемент", "urgency": "high"})]},
        {"content": "Передал менеджеру, он скоро напишет."},
    ], notes)
    await agent.reply(9, "Верните деньги!!!")
    assert "🔴" in notes[0] and "возврат" in notes[0]


@pytest.mark.asyncio
async def test_agent_step_limit_fallback():
    loop = [{"tool_calls": [tool_call(f"c{i}", "search_knowledge", {"query": "x"})]} for i in range(6)]
    agent, _, _ = make(loop)
    answer = await agent.reply(1, "?")
    assert "менеджеру" in answer
