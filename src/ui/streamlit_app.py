"""Streamlit UI — thin client over the FastAPI backend.

Two views: Chat (conversation with session memory) and Analítica
(metrics over the whole conversation history). All state lives in the
backend; the UI only renders API responses.
"""

from __future__ import annotations

import os
import uuid

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8100")
TIMEOUT = httpx.Timeout(60.0)

st.set_page_config(page_title="Asistente Bancolombia RAG", page_icon="🏦", layout="centered")


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


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🏦 Asistente RAG")
    view = st.radio("Vista", ["💬 Chat", "📊 Analítica"], label_visibility="collapsed")

    st.divider()
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"web-{uuid.uuid4().hex[:8]}"

    st.caption("Sesión actual")
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

# ---------------------------------------------------------------- chat view
if view == "💬 Chat":
    st.header("Pregúntale al sitio del banco")
    st.caption("Respuestas generadas únicamente a partir del contenido scrapeado de bancolombia.com")

    history = api_get(f"/sessions/{st.session_state.session_id}/history")
    for msg in (history or {}).get("messages", []):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("sources"):
                with st.expander("Fuentes"):
                    for url in msg["sources"]:
                        st.markdown(f"- [{url}]({url})")

    if question := st.chat_input("Escribe tu pregunta…"):
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Buscando en el sitio del banco…"):
                result = api_post_chat(st.session_state.session_id, question)
            if result:
                st.markdown(result["answer"])
                if result.get("sources"):
                    with st.expander("Fuentes"):
                        for url in result["sources"]:
                            st.markdown(f"- [{url}]({url})")
                st.caption(f"⏱️ {result['latency_ms']} ms")

# ---------------------------------------------------------------- analytics view
else:
    st.header("Analítica de conversaciones")
    data = api_get("/analytics/summary") or {}

    if not data.get("total_messages"):
        st.info("Aún no hay conversaciones registradas.")
        st.stop()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sesiones", data["total_sessions"])
    col2.metric("Mensajes", data["total_messages"])
    col3.metric("Msjs/sesión", data["avg_messages_per_session"])
    col4.metric("Latencia p50", f"{data['latency_ms']['p50']} ms")

    st.subheader("Mensajes por día")
    st.bar_chart(data["messages_per_day"])

    left, right = st.columns(2)
    with left:
        st.subheader("Páginas más citadas")
        for item in data["top_cited_pages"]:
            label = item["url"].replace("https://www.bancolombia.com", "") or "/"
            st.markdown(f"**{item['citations']}×** [{label}]({item['url']})")
    with right:
        st.subheader("Temas más preguntados")
        for item in data["top_question_topics"][:10]:
            st.markdown(f"**{item['occurrences']}×** {item['term']}")

    st.subheader("Latencia de respuesta")
    lat = data["latency_ms"]
    st.write(f"Promedio: **{lat['avg']} ms** · p50: **{lat['p50']} ms** · p95: **{lat['p95']} ms**")

    st.subheader("Sesiones más activas")
    for item in data["most_active_sessions"]:
        st.markdown(f"- `{item['session_id']}` — {item['messages']} mensajes")
