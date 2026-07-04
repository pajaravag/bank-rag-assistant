from fastapi.testclient import TestClient

from src.analytics.metrics import ConversationAnalytics
from src.api.app import app, state
from src.llm.base import LLMError
from src.repositories.conversation_repository import ConversationRepository
from src.services.chat_service import ChatResponse


class FakeChatService:
    def ask(self, session_id: str, question: str) -> ChatResponse:
        if question == "boom":
            raise LLMError("proveedor no disponible")
        return ChatResponse(answer="respuesta", sources=["https://x.co/p"], latency_ms=5)


def make_client(tmp_path) -> TestClient:
    # Populate state directly; TestClient without a `with` block skips lifespan
    conversations = ConversationRepository(str(tmp_path / "api.db"))
    state["chat_service"] = FakeChatService()
    state["conversations"] = conversations
    state["analytics"] = ConversationAnalytics(conversations)
    return TestClient(app, raise_server_exceptions=False)


def test_health(tmp_path):
    assert make_client(tmp_path).get("/health").json() == {"status": "ok"}


def test_chat_happy_path(tmp_path):
    resp = make_client(tmp_path).post("/chat", json={"session_id": "s1", "message": "hola"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "respuesta"
    assert body["sources"] == ["https://x.co/p"]


def test_chat_llm_error_maps_to_503(tmp_path):
    resp = make_client(tmp_path).post("/chat", json={"session_id": "s1", "message": "boom"})
    assert resp.status_code == 503
    assert "proveedor" in resp.json()["detail"]


def test_chat_validation_422(tmp_path):
    resp = make_client(tmp_path).post("/chat", json={"session_id": "", "message": ""})
    assert resp.status_code == 422


def test_history_404_for_unknown_session(tmp_path):
    resp = make_client(tmp_path).get("/sessions/desconocida/history")
    assert resp.status_code == 404


def test_history_and_analytics_roundtrip(tmp_path):
    client = make_client(tmp_path)
    state["conversations"].add_message("s9", "user", "pregunta")
    state["conversations"].add_message(
        "s9", "assistant", "ok", sources=["https://x"], latency_ms=10,
        prompt_tokens=100, completion_tokens=20,
    )

    history = client.get("/sessions/s9/history").json()
    assert len(history["messages"]) == 2

    summary = client.get("/analytics/summary").json()
    assert summary["total_sessions"] == 1
    assert summary["tokens"]["prompt"] == 100
    assert summary["coverage"]["rate"] == 1.0
