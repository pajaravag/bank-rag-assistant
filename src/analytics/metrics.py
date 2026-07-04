"""Analytics over the persisted conversation history (FR6).

Traverses every stored message and derives usage and impact metrics:
volume, engagement per session, answer latency, most-cited pages and
the dominant topics users ask about.
"""

from __future__ import annotations

import re
from collections import Counter
from statistics import mean, median

from src.repositories.conversation_repository import ConversationRepository

_SPANISH_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en",
    "y", "o", "u", "a", "al", "que", "qué", "como", "cómo", "para", "por",
    "con", "sin", "es", "son", "se", "su", "sus", "mi", "mis", "tu", "tus",
    "me", "te", "le", "lo", "les", "si", "sí", "no", "hay", "más", "pero",
    "este", "esta", "esto", "ese", "esa", "eso", "cuál", "cual", "cuáles",
    "banco", "puedo", "tiene", "tienen", "ofrece", "sobre", "cuánto", "cuánta",
}

_WORD_RE = re.compile(r"[a-záéíóúüñ]{3,}", re.IGNORECASE)


def _percentile(sorted_values: list[int], pct: float) -> int:
    if not sorted_values:
        return 0
    index = min(int(len(sorted_values) * pct), len(sorted_values) - 1)
    return sorted_values[index]


class ConversationAnalytics:
    def __init__(self, conversations: ConversationRepository) -> None:
        self.conversations = conversations

    def summary(self) -> dict:
        messages = self.conversations.all_messages()
        if not messages:
            return {"total_messages": 0, "detail": "No conversations recorded yet"}

        sessions = Counter(m["session_id"] for m in messages)
        user_msgs = [m for m in messages if m["role"] == "user"]
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        latencies = sorted(m["latency_ms"] for m in assistant_msgs if m["latency_ms"])

        source_counter: Counter = Counter()
        for m in assistant_msgs:
            source_counter.update(m["sources"])

        word_counter: Counter = Counter()
        for m in user_msgs:
            words = (w.lower() for w in _WORD_RE.findall(m["content"]))
            word_counter.update(w for w in words if w not in _SPANISH_STOPWORDS)

        per_day = Counter(m["created_at"][:10] for m in messages)

        return {
            "total_sessions": len(sessions),
            "total_messages": len(messages),
            "user_messages": len(user_msgs),
            "assistant_messages": len(assistant_msgs),
            "avg_messages_per_session": round(len(messages) / len(sessions), 2),
            "latency_ms": {
                "avg": int(mean(latencies)) if latencies else 0,
                "p50": int(median(latencies)) if latencies else 0,
                "p95": _percentile(latencies, 0.95),
            },
            "messages_per_day": dict(sorted(per_day.items())),
            "top_cited_pages": [
                {"url": url, "citations": count} for url, count in source_counter.most_common(10)
            ],
            "top_question_topics": [
                {"term": term, "occurrences": count} for term, count in word_counter.most_common(15)
            ],
            "most_active_sessions": [
                {"session_id": sid, "messages": count} for sid, count in sessions.most_common(5)
            ],
        }
