"""Chat orchestration: history window + retrieval + prompt assembly + LLM.

Depends only on interfaces (RetrievalStrategy, LLMProvider,
ConversationRepository) — concrete implementations are injected.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from src.llm.base import LLMProvider
from src.repositories.conversation_repository import ConversationRepository
from src.retrieval.strategies import RetrievalStrategy

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Eres un asistente virtual del banco. Respondes preguntas de usuarios internos \
usando EXCLUSIVAMENTE la información del sitio web del banco incluida en el \
bloque CONTEXTO de cada pregunta.

Reglas:
- Responde en español, de forma clara y concisa.
- Si el contexto no contiene la respuesta, dilo honestamente y sugiere \
reformular la pregunta; nunca inventes datos, tasas ni condiciones.
- Cuando uses información del contexto, menciona de qué página proviene.
- Usa el historial de la conversación para resolver referencias \
("eso", "el anterior", etc.)."""

USER_TEMPLATE = """\
CONTEXTO (fragmentos del sitio web del banco):
{context}

PREGUNTA: {question}"""


@dataclass
class ChatResponse:
    answer: str
    sources: list[str]
    latency_ms: int


class ChatService:
    def __init__(
        self,
        retrieval: RetrievalStrategy,
        llm: LLMProvider,
        conversations: ConversationRepository,
        history_window_n: int,
    ) -> None:
        self.retrieval = retrieval
        self.llm = llm
        self.conversations = conversations
        self.history_window_n = history_window_n

    def ask(self, session_id: str, question: str) -> ChatResponse:
        start = time.perf_counter()

        history = self.conversations.last_n(session_id, self.history_window_n)
        retrieved = self.retrieval.retrieve(question)
        sources = list(dict.fromkeys(r.chunk.url for r in retrieved))

        context = "\n\n".join(
            f"[{i + 1}] ({r.chunk.title} — {r.chunk.url})\n{r.chunk.text}"
            for i, r in enumerate(retrieved)
        ) or "(no se encontró contenido relevante)"

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += [{"role": t.role, "content": t.content} for t in history]
        messages.append({"role": "user", "content": USER_TEMPLATE.format(context=context, question=question)})

        answer = self.llm.chat(messages)
        latency_ms = int((time.perf_counter() - start) * 1000)

        self.conversations.add_message(session_id, "user", question)
        self.conversations.add_message(
            session_id, "assistant", answer, sources=sources, latency_ms=latency_ms
        )
        logger.info("session=%s latency=%dms sources=%d", session_id, latency_ms, len(sources))
        return ChatResponse(answer=answer, sources=sources, latency_ms=latency_ms)
