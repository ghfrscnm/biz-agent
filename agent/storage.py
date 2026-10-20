"""SQLite: история диалогов, заявки, передачи менеджеру и журнал вызовов инструментов."""
import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    name TEXT, phone TEXT, interest TEXT, preferred_time TEXT, comment TEXT,
    ts REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    reason TEXT, summary TEXT, urgency TEXT,
    ts REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    tool TEXT NOT NULL,
    args TEXT NOT NULL,
    result TEXT NOT NULL,
    ts REAL NOT NULL
);
"""


class Storage:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # --- история ---
    def add_message(self, chat_id: int, role: str, content: str) -> None:
        self.db.execute(
            "INSERT INTO messages(chat_id, role, content, ts) VALUES (?,?,?,?)",
            (chat_id, role, content, time.time()),
        )
        self.db.commit()

    def history(self, chat_id: int, limit: int) -> list[dict]:
        rows = self.db.execute(
            "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def reset(self, chat_id: int) -> None:
        self.db.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
        self.db.commit()

    # --- заявки ---
    def add_lead(self, chat_id: int, **fields) -> int:
        cur = self.db.execute(
            "INSERT INTO leads(chat_id, name, phone, interest, preferred_time, comment, ts)"
            " VALUES (?,?,?,?,?,?,?)",
            (chat_id, fields.get("name"), fields.get("phone"), fields.get("interest"),
             fields.get("preferred_time"), fields.get("comment"), time.time()),
        )
        self.db.commit()
        return cur.lastrowid

    def last_leads(self, limit: int = 10) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    # --- передачи менеджеру ---
    def add_handoff(self, chat_id: int, reason: str, summary: str, urgency: str) -> int:
        cur = self.db.execute(
            "INSERT INTO handoffs(chat_id, reason, summary, urgency, ts) VALUES (?,?,?,?,?)",
            (chat_id, reason, summary, urgency, time.time()),
        )
        self.db.commit()
        return cur.lastrowid

    # --- журнал инструментов ---
    def add_trace(self, chat_id: int, tool: str, args: dict, result: str) -> None:
        self.db.execute(
            "INSERT INTO traces(chat_id, tool, args, result, ts) VALUES (?,?,?,?,?)",
            (chat_id, tool, json.dumps(args, ensure_ascii=False), result[:2000], time.time()),
        )
        self.db.commit()

    def last_traces(self, chat_id: int | None = None, limit: int = 10) -> list[sqlite3.Row]:
        if chat_id is None:
            q, p = "SELECT * FROM traces ORDER BY id DESC LIMIT ?", (limit,)
        else:
            q, p = "SELECT * FROM traces WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit)
        return self.db.execute(q, p).fetchall()
