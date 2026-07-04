"""Chat orchestration: history window + retrieval + prompt assembly + LLM.

Depends only on interfaces (RetrievalStrategy, LLMProvider,
ConversationRepository) — concrete implementations are injected.

Conversational retrieval: follow-up questions are condensed into a
standalone query (small, fast model) before embedding, so "¿y eso
sirve para X?" retrieves as well as a fully-specified question.

Every stage emits an OpenTelemetry span; with Phoenix enabled the full
chain (condense -> retrieve -> generate) is visible per conversation turn.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from opentelemetry import trace

from src.llm.base import LLMError, LLMProvider
from src.repositories.conversation_repository import ConversationRepository
from src.retrieval.strategies import RetrievalStrategy

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("bank-rag-assistant")

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

CONDENSE_PROMPT = """\
Reescribe la última pregunta del usuario como una pregunta independiente y \
completa en español, resolviendo referencias al historial de la conversación. \
Devuelve ÚNICAMENTE la pregunta reescrita, sin explicaciones."""

NO_CONTEXT_ANSWER = (
    "No encontré información sobre ese tema en el contenido del sitio web del "
    "banco. Puede que la página no lo cubra o que la pregunta esté fuera del "
    "alcance del asistente. Intenta reformularla o pregunta por productos y "
    "servicios publicados en el sitio."
)


@dataclass
class ChatResponse:
    answer: str
    sources: list[str]
    latency_ms: int
    no_context: bool = False


class ChatService:
    def __init__(
        self,
        retrieval: RetrievalStrategy,
        llm: LLMProvider,
        conversations: ConversationRepository,
        history_window_n: int,
        condenser: LLMProvider | None = None,
    ) -> None:
        self.retrieval = retrieval
        self.llm = llm
        self.conversations = conversations
        self.history_window_n = history_window_n
        self.condenser = condenser

    def ask(self, session_id: str, question: str) -> ChatResponse:
        with tracer.start_as_current_span("chat") as span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("session.id", session_id)
            span.set_attribute("input.value", question)

            start = time.perf_counter()
            history = self.conversations.last_n(session_id, self.history_window_n)

            search_query = self._condense(history, question)
            retrieved = self._retrieve(search_query)

            if not retrieved:
                return self._answer_without_context(span, session_id, question, start)

            sources = list(dict.fromkeys(r.chunk.url for r in retrieved))
            context = "\n\n".join(
                f"[{i + 1}] ({r.chunk.title} — {r.chunk.url})\n{r.chunk.text}"
                for i, r in enumerate(retrieved)
            )

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            messages += [{"role": t.role, "content": t.content} for t in history]
            messages.append(
                {"role": "user", "content": USER_TEMPLATE.format(context=context, question=question)}
            )

            result = self._generate(messages)
            latency_ms = int((time.perf_counter() - start) * 1000)

            self.conversations.add_message(session_id, "user", question)
            self.conversations.add_message(
                session_id, "assistant", result.text,
                sources=sources, latency_ms=latency_ms,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                model=result.model,
            )
            span.set_attribute("output.value", result.text)
            logger.info(
                "session=%s latency=%dms sources=%d tokens=%d+%d model=%s",
                session_id, latency_ms, len(sources),
                result.prompt_tokens, result.completion_tokens, result.model,
            )
            return ChatResponse(answer=result.text, sources=sources, latency_ms=latency_ms)

    def _condense(self, history, question: str) -> str:
        """Rewrites a follow-up into a standalone query for retrieval only."""
        if not history or self.condenser is None:
            return question
        with tracer.start_as_current_span("condense_query") as span:
            span.set_attribute("openinference.span.kind", "LLM")
            span.set_attribute("input.value", question)
            messages = [{"role": "system", "content": CONDENSE_PROMPT}]
            messages += [{"role": t.role, "content": t.content} for t in history]
            messages.append({"role": "user", "content": question})
            try:
                condensed = self.condenser.chat(messages).text.strip()
            except LLMError as exc:
                logger.warning("Condensation failed (%s) — using raw question", exc)
                return question
            span.set_attribute("output.value", condensed)
            logger.info("Condensed %r -> %r", question, condensed)
            return condensed or question

    def _retrieve(self, query: str):
        with tracer.start_as_current_span("retrieve") as span:
            span.set_attribute("openinference.span.kind", "RETRIEVER")
            span.set_attribute("input.value", query)
            retrieved = self.retrieval.retrieve(query)
            span.set_attribute("retrieval.count", len(retrieved))
            span.set_attribute("retrieval.urls", [r.chunk.url for r in retrieved])
            span.set_attribute("retrieval.scores", [round(r.score, 3) for r in retrieved])
            return retrieved

    def _generate(self, messages):
        with tracer.start_as_current_span("generate") as span:
            span.set_attribute("openinference.span.kind", "LLM")
            result = self.llm.chat(messages)
            span.set_attribute("llm.model_name", result.model)
            span.set_attribute("llm.token_count.prompt", result.prompt_tokens)
            span.set_attribute("llm.token_count.completion", result.completion_tokens)
            span.set_attribute("output.value", result.text)
            return result

    def _answer_without_context(self, span, session_id: str, question: str, start: float) -> ChatResponse:
        """No chunk passed the relevance threshold: answer honestly, skip the LLM."""
        latency_ms = int((time.perf_counter() - start) * 1000)
        self.conversations.add_message(session_id, "user", question)
        self.conversations.add_message(
            session_id, "assistant", NO_CONTEXT_ANSWER,
            latency_ms=latency_ms, no_context=True,
        )
        span.set_attribute("output.value", NO_CONTEXT_ANSWER)
        span.set_attribute("retrieval.no_context", True)
        logger.info("session=%s no relevant context — skipped LLM call", session_id)
        return ChatResponse(
            answer=NO_CONTEXT_ANSWER, sources=[], latency_ms=latency_ms, no_context=True
        )
