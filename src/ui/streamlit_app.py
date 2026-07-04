"""Streamlit UI — thin client over the FastAPI backend.

Two views: Chat (conversation with session memory) and Analítica
(metrics over the whole conversation history). All state lives in the
backend; the UI only renders API responses.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

import altair as alt
import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8100")
TIMEOUT = httpx.Timeout(60.0)
BASE_HOST = "bancolombia.com"

SUGGESTED_QUESTIONS = [
    "¿Qué tipos de cuentas de ahorro ofrece el banco?",
    "¿Qué es el factoring y cómo funciona?",
    "¿Qué opciones de crédito de vivienda existen?",
    "¿Cómo solicito una tarjeta de crédito?",
]

st.set_page_config(
    page_title="Asistente Bancario RAG",
    page_icon="🏦",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      #MainMenu, footer {visibility: hidden;}
      .block-container {padding-top: 2.2rem; padding-bottom: 4rem;}
      h1 {letter-spacing: -0.5px;}
      [data-testid="stChatMessage"] {border-radius: 12px;}
      [data-testid="stMetric"] {
        background: #F8FAFC; border: 1px solid #E2E8F0;
        border-radius: 10px; padding: 12px 16px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- API client
def api_get(path: str) -> dict | None:
    try:
        resp = httpx.get(f"{API_URL}{path}", timeout=TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"No se pudo contactar la API ({exc.__class__.__name__}). ¿Está corriendo el backend?")
        st.stop()


def api_post_chat(session_id: str, message: str) -> dict | None:
    try:
        resp = httpx.post(
            f"{API_URL}/chat",
            json={"session_id": session_id, "message": message},
            timeout=TIMEOUT,
        )
        if resp.status_code == 503:
            st.warning(resp.json().get("detail", "El proveedor LLM no está disponible"))
            return None
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"Error llamando a la API: {exc}")
        return None


def short_path(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path if path else "/"


def render_sources(urls: list[str]) -> None:
    if not urls:
        return
    with st.expander(f"📄 Fuentes ({len(urls)})"):
        for url in urls:
            st.markdown(f"- [`{short_path(url)}`]({url})")


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("## 🏦 Asistente Bancario")
    st.caption("RAG sobre el sitio público del banco")

    view = st.radio("Vista", ["💬 Chat", "📊 Analítica"], label_visibility="collapsed")
    st.divider()

    if "session_id" not in st.session_state:
        st.session_state.session_id = f"web-{uuid.uuid4().hex[:8]}"

    st.markdown("**Sesión actual**")
    st.code(st.session_state.session_id, language=None)
    if st.button("➕ Nueva sesión", use_container_width=True):
        st.session_state.session_id = f"web-{uuid.uuid4().hex[:8]}"
        st.rerun()

    existing = (api_get("/sessions") or {}).get("sessions", [])
    if existing:
        picked = st.selectbox("Retomar sesión anterior", ["—"] + existing)
        if picked != "—" and picked != st.session_state.session_id:
            st.session_state.session_id = picked
            st.rerun()

    st.divider()
    with st.expander("⚙️ Configuración del sistema"):
        cfg = api_get("/config") or {}
        if cfg:
            st.markdown(
                f"""
- **LLM**: `{cfg.get('llm_model', '—')}`
- **Fallback**: `{cfg.get('llm_fallback_model', '—')}`
- **Condensación**: `{cfg.get('condense_model') or 'desactivada'}`
- **Embeddings**: `{cfg.get('embedding_model', '—').split('/')[-1]}`
- **Reranker**: `{'activo' if cfg.get('rerank_enabled') else 'inactivo'}`
- **Memoria (N)**: `{cfg.get('history_window_n', '—')}` mensajes
- **Recuperación**: top-{cfg.get('top_k', '—')} → rerank top-{cfg.get('rerank_top_k', '—')}
"""
            )
    st.caption("Stack 100% gratuito · [repositorio](https://github.com/pajaravag/bank-rag-assistant)")


# ---------------------------------------------------------------- chat view
if view == "💬 Chat":
    st.title("Pregúntale al sitio del banco")
    st.caption(
        f"Respuestas generadas únicamente a partir del contenido scrapeado de {BASE_HOST}, "
        "con citas a las páginas fuente."
    )

    history = api_get(f"/sessions/{st.session_state.session_id}/history")
    messages = (history or {}).get("messages", [])

    for msg in messages:
        avatar = "🏦" if msg["role"] == "assistant" else "🧑‍💻"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                render_sources(msg.get("sources", []))
                if msg.get("latency_ms"):
                    st.caption(f"⏱️ {msg['latency_ms']} ms")

    # Empty state: suggested questions
    if not messages:
        st.markdown("##### Prueba con una de estas preguntas:")
        cols = st.columns(2)
        for i, suggestion in enumerate(SUGGESTED_QUESTIONS):
            if cols[i % 2].button(suggestion, key=f"sug-{i}", use_container_width=True):
                st.session_state.pending_question = suggestion
                st.rerun()

    question = st.chat_input("Escribe tu pregunta sobre el banco…")
    if not question and st.session_state.get("pending_question"):
        question = st.session_state.pop("pending_question")

    if question:
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(question)
        with st.chat_message("assistant", avatar="🏦"):
            with st.spinner("Buscando en el sitio del banco…"):
                result = api_post_chat(st.session_state.session_id, question)
            if result:
                st.markdown(result["answer"])
                render_sources(result.get("sources", []))
                st.caption(f"⏱️ {result['latency_ms']} ms")

# ---------------------------------------------------------------- analytics view
else:
    st.title("Analítica de conversaciones")
    st.caption("Métricas de uso e impacto calculadas sobre todo el historial persistido.")
    data = api_get("/analytics/summary") or {}

    if not data.get("total_messages"):
        st.info("Aún no hay conversaciones registradas. Haz una pregunta en la vista de Chat.")
        st.stop()

    coverage = data.get("coverage", {})
    tokens = data.get("tokens", {})
    latency = data.get("latency_ms", {})

    # --- KPI row
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Sesiones", data["total_sessions"])
    k2.metric("Mensajes", data["total_messages"])
    k3.metric("Msjs / sesión", data["avg_messages_per_session"])
    k4.metric("Latencia p50", f"{latency.get('p50', 0):,} ms")

    k5, k6, k7, k8 = st.columns(4)
    rate = coverage.get("rate")
    k5.metric("Cobertura", f"{rate * 100:.0f}%" if rate is not None else "—",
              help="Porcentaje de preguntas que el corpus pudo responder")
    k6.metric("Latencia p95", f"{latency.get('p95', 0):,} ms")
    k7.metric("Tokens totales", f"{tokens.get('prompt', 0) + tokens.get('completion', 0):,}")
    k8.metric("Ahorro vs API de pago", f"${tokens.get('paid_api_equivalent_usd', 0):.4f}",
              help="Costo que tendría este uso en una API de pago (ref. GPT-4o); el stack actual cuesta $0")

    st.divider()

    # --- Messages per day
    st.subheader("Actividad por día")
    per_day = data.get("messages_per_day", {})
    if per_day:
        df_day = pd.DataFrame({"fecha": list(per_day.keys()), "mensajes": list(per_day.values())})
        chart = (
            alt.Chart(df_day)
            .mark_bar(color="#2563EB", cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=32)
            .encode(x=alt.X("fecha:N", title=None), y=alt.Y("mensajes:Q", title=None))
            .properties(height=220)
        )
        st.altair_chart(chart, use_container_width=True)

    left, right = st.columns(2)

    with left:
        st.subheader("Páginas más citadas")
        pages = data.get("top_cited_pages", [])
        if pages:
            df_pages = pd.DataFrame(pages)
            df_pages["página"] = df_pages["url"].map(short_path)
            chart = (
                alt.Chart(df_pages.head(8))
                .mark_bar(color="#0891B2", cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    x=alt.X("citations:Q", title=None),
                    y=alt.Y("página:N", sort="-x", title=None),
                )
                .properties(height=260)
            )
            st.altair_chart(chart, use_container_width=True)

    with right:
        st.subheader("Temas más preguntados")
        topics = data.get("top_question_topics", [])
        if topics:
            df_topics = pd.DataFrame(topics[:8])
            chart = (
                alt.Chart(df_topics)
                .mark_bar(color="#7C3AED", cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    x=alt.X("occurrences:Q", title=None),
                    y=alt.Y("term:N", sort="-x", title=None),
                )
                .properties(height=260)
            )
            st.altair_chart(chart, use_container_width=True)

    st.divider()

    # --- Coverage detail
    st.subheader("Cobertura del corpus")
    answered = coverage.get("answered", 0)
    no_ctx = coverage.get("no_context", 0)
    st.progress(rate or 0.0, text=f"{answered} respondidas · {no_ctx} sin contexto")
    unanswered = coverage.get("recent_unanswered_questions", [])
    if unanswered:
        with st.expander("Preguntas recientes que el corpus no pudo responder"):
            for q in unanswered:
                st.markdown(f"- {q}")
            st.caption("Señal accionable: contenido que falta en el sitio del banco.")

    # --- Sessions
    st.subheader("Sesiones más activas")
    for item in data.get("most_active_sessions", []):
        st.markdown(f"- `{item['session_id']}` — {item['messages']} mensajes")
