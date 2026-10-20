"""База знаний: markdown-файлы из kb/, нарезка по заголовкам, поиск BM25.

Без внешних сервисов и эмбеддингов: работает бесплатно и мгновенно на базах
до нескольких тысяч фрагментов. Для большой базы класс легко заменить на
pgvector/Qdrant — интерфейс тот же: search(query, k) -> list[Chunk].
"""
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
STOP = {
    "и", "в", "во", "на", "с", "со", "по", "к", "у", "о", "об", "от", "до", "за", "из",
    "а", "но", "или", "ли", "же", "не", "что", "как", "это", "то", "для", "при", "мне",
    "я", "вы", "мы", "он", "она", "они", "есть", "ваш", "ваши", "наш", "можно", "какой",
    "какая", "какие", "сколько", "где", "когда", "the", "a", "is",
}


def tokenize(text: str) -> list[str]:
    """Нижний регистр + грубый стемминг (первые 5 букв) — хватает для русского."""
    out = []
    for w in WORD_RE.findall(text.lower().replace("ё", "е")):
        if w in STOP:
            continue
        out.append(w[:5] if not w.isdigit() else w)
    return out


@dataclass
class Chunk:
    source: str
    title: str
    text: str


def load_chunks(kb_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(kb_dir.glob("*.md")):
        title, buf = path.stem, []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                if "".join(buf).strip():
                    chunks.append(Chunk(path.name, title, "\n".join(buf).strip()))
                title, buf = line.lstrip("# ").strip(), []
            else:
                buf.append(line)
        if "".join(buf).strip():
            chunks.append(Chunk(path.name, title, "\n".join(buf).strip()))
    return chunks


class KnowledgeBase:
    def __init__(self, kb_dir: Path, k1: float = 1.5, b: float = 0.75):
        self.chunks = load_chunks(kb_dir)
        self.k1, self.b = k1, b
        # заголовок учитываем дважды — он самый информативный
        self.docs = [tokenize(f"{c.title} {c.title} {c.text}") for c in self.chunks]
        self.avgdl = sum(map(len, self.docs)) / max(len(self.docs), 1)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    def search(self, query: str, k: int = 3) -> list[tuple[Chunk, float]]:
        q = tokenize(query)
        scored = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                    )
            if s > 0:
                scored.append((self.chunks[i], s))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]
