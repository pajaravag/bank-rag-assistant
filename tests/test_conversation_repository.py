from src.repositories.conversation_repository import ConversationRepository


def make_repo(tmp_path):
    return ConversationRepository(str(tmp_path / "test.db"))


def test_add_and_last_n_window(tmp_path):
    repo = make_repo(tmp_path)
    for i in range(10):
        repo.add_message("s1", "user" if i % 2 == 0 else "assistant", f"msg {i}")

    window = repo.last_n("s1", 4)
    assert [t.content for t in window] == ["msg 6", "msg 7", "msg 8", "msg 9"]
    assert window[0].role == "user"


def test_sessions_are_isolated(tmp_path):
    repo = make_repo(tmp_path)
    repo.add_message("s1", "user", "hola desde s1")
    repo.add_message("s2", "user", "hola desde s2")

    assert [t.content for t in repo.last_n("s1", 10)] == ["hola desde s1"]
    assert repo.full_history("s2")[0]["content"] == "hola desde s2"


def test_sources_and_latency_roundtrip(tmp_path):
    repo = make_repo(tmp_path)
    repo.add_message("s1", "assistant", "respuesta", sources=["https://a", "https://b"], latency_ms=1234)

    row = repo.full_history("s1")[0]
    assert row["sources"] == ["https://a", "https://b"]
    assert row["latency_ms"] == 1234


def test_session_ids_most_recent_first(tmp_path):
    repo = make_repo(tmp_path)
    repo.add_message("old", "user", "a")
    repo.add_message("new", "user", "b")
    assert repo.session_ids() == ["new", "old"]


def test_empty_history(tmp_path):
    repo = make_repo(tmp_path)
    assert repo.last_n("nope", 5) == []
    assert repo.full_history("nope") == []
    assert repo.all_messages() == []
