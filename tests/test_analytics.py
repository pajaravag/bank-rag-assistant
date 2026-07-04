from src.analytics.metrics import ConversationAnalytics
from src.repositories.conversation_repository import ConversationRepository


def seeded_analytics(tmp_path) -> ConversationAnalytics:
    repo = ConversationRepository(str(tmp_path / "test.db"))
    repo.add_message("s1", "user", "¿Qué es el factoring para empresas?")
    repo.add_message("s1", "assistant", "El factoring es...", sources=["https://x.co/factoring"], latency_ms=1000)
    repo.add_message("s1", "user", "¿Y el factoring tiene costos?")
    repo.add_message("s1", "assistant", "Sí...", sources=["https://x.co/factoring"], latency_ms=3000)
    repo.add_message("s2", "user", "¿Cómo abro una cuenta de ahorros?")
    repo.add_message("s2", "assistant", "Para abrir...", sources=["https://x.co/cuentas"], latency_ms=2000)
    return ConversationAnalytics(repo)


def test_summary_counts(tmp_path):
    summary = seeded_analytics(tmp_path).summary()
    assert summary["total_sessions"] == 2
    assert summary["total_messages"] == 6
    assert summary["user_messages"] == 3
    assert summary["avg_messages_per_session"] == 3.0


def test_latency_stats(tmp_path):
    summary = seeded_analytics(tmp_path).summary()
    assert summary["latency_ms"]["avg"] == 2000
    assert summary["latency_ms"]["p50"] == 2000


def test_top_cited_pages(tmp_path):
    summary = seeded_analytics(tmp_path).summary()
    top = summary["top_cited_pages"]
    assert top[0] == {"url": "https://x.co/factoring", "citations": 2}


def test_topics_exclude_stopwords(tmp_path):
    summary = seeded_analytics(tmp_path).summary()
    terms = {t["term"] for t in summary["top_question_topics"]}
    assert "factoring" in terms
    assert "qué" not in terms and "para" not in terms


def test_empty_history_summary(tmp_path):
    repo = ConversationRepository(str(tmp_path / "empty.db"))
    assert ConversationAnalytics(repo).summary()["total_messages"] == 0
