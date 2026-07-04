# Bank RAG Assistant

Conversational RAG (Retrieval-Augmented Generation) system that scrapes a
bank's public website, indexes its content in a vector database, and answers
questions about it through a chat interface with persistent, session-based
conversation history and usage analytics.

> Technical test — Machine Learning Engineer / AI Engineer.
> Target site: https://www.bancolombia.com/ (the brief allows a bank other
> than BBVA; bbva.com.co blocks non-browser clients with HTTP 403 at the CDN
> level, verified 2026-07-04 — see [SPEC.md](SPEC.md) for the full decision).

## Status

🚧 Work in progress — see [SPEC.md](SPEC.md) for the full design: architecture,
stack justification, design patterns, and delivery plan.

## Stack

Python 3.12 · httpx + BeautifulSoup4 · Qdrant (self-hosted) ·
sentence-transformers (multilingual-e5-small) · CrossEncoder reranker ·
Groq (Llama 3.x) · FastAPI · Streamlit · SQLite · Docker Compose

Sections below will be completed as the system is built:

- [ ] Prerequisites
- [ ] Setup & run with Docker (one command)
- [ ] Using the chat interface
- [ ] Analytics
- [ ] Design patterns: which, where, why
- [ ] Stack justification
- [ ] Known limitations & assumptions
- [ ] Future improvements
