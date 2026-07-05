# SPEC — RAG Conversational Assistant with Web Scraping

> **Nota**: este es el documento de diseño **previo a la implementación**
> (enfoque spec-driven), conservado como artefacto del proceso. El sistema
> final difiere en puntos decididos durante el desarrollo: Phoenix para
> observabilidad, condensación de consultas de seguimiento, umbral de
> relevancia con gating honesto, y Singleton como cuarto patrón en lugar de
> Chain of Responsibility. La documentación del sistema final está en
> [README.md](README.md) y [docs/PROCESO.md](docs/PROCESO.md).

**Role test:** Machine Learning Engineer / AI Engineer
**Deadline:** Sunday, July 5, 11:59 PM
**Delivery:** Public repo (GitHub), Dockerized, meaningful commit history

---

## 1. Problem statement

The brief asks for an internal conversational assistant that answers questions
about content published on a bank's institutional website, without manual
searching. The system is a RAG (Retrieval-Augmented Generation) pipeline in Python.

**Target site: https://www.bancolombia.com/** (the brief allows a bank other
than BBVA). Verified 2026-07-04: bbva.com.co returns HTTP 403 to any
non-browser client (bot protection at the TLS/CDN layer), even with full
browser headers. bancolombia.com returns 200 with server-rendered HTML
(~280 links on the landing page), making it scrapable with plain HTTP —
no headless browser needed. This decision is documented in the README.

## 2. Functional requirements (from the brief)

| ID | Requirement |
|----|-------------|
| FR1 | Scrape the target bank site (https://www.bancolombia.com/) and extract page content |
| FR2 | Store scraped data locally — **both raw and cleaned** |
| FR3 | Chunk, embed and index the content in a vector database |
| FR4 | Minimal conversational interface for asking questions about the site |
| FR5 | Conversation history per session ID, using the last **N** messages (N configurable), **persisted** |
| FR6 | Analytics feature: traverse conversation history and extract metrics / impact values |
| FR7 | README that lets anyone run the system from scratch |

### Bonus (in scope)
- **B1** Reranker before passing context to the LLM
- **B2** Error handling throughout
- **B3** Externalized configuration (`.env`): N messages, model, chunk size, top-k, etc.

### Non-functional requirements
- Python only; rest of the stack free/open-source where possible
- Runs end-to-end with **one command**: `docker compose up`
- ≥ 3 design patterns, documented (which, where, why) in the README
- Commit history showing logical progression with descriptive messages

## 3. Tech stack (decided)

| Concern | Choice | Justification |
|---|---|---|
| Language | Python 3.12 | Required |
| Scraping | `httpx` + `BeautifulSoup4` | Lightweight; enough for an institutional site; no browser needed (fallback: `playwright` only if the site proves JS-heavy) |
| Raw/clean storage | Local filesystem (`data/raw/*.html`, `data/clean/*.json`) | Explicit FR2; simple and inspectable |
| Vector DB | **Qdrant** (self-hosted container) | Free, production-grade, first-class Docker support; real second service in docker-compose |
| Embeddings | `sentence-transformers` — `intfloat/multilingual-e5-small` | Free, local, multilingual (site content is Spanish), CPU-friendly |
| Reranker | CrossEncoder `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Multilingual, small enough for CPU (bonus B1) |
| LLM | **Groq API** (Llama 3.x) behind a provider abstraction | Free tier, fast, no GPU required; abstracted via Factory so Ollama/others can be swapped in |
| Orchestration | Plain Python (no LangChain/LlamaIndex) | Keeps design patterns genuine and visible; full control; fewer dependencies |
| Backend | **FastAPI** | API-first architecture: chat, sessions, analytics endpoints |
| Frontend | **Streamlit** (thin client over the API) | Fast to build, clean chat components |
| History + analytics store | **SQLite** (via `sqlmodel`/`sqlite3`) | Persistent, zero extra service, easy to aggregate for metrics |
| Config | `pydantic-settings` + `.env` | Bonus B3; typed, validated settings |
| Containerization | Dockerfile (multi-stage) + docker-compose (app, ui, qdrant) | One-command startup requirement |

## 4. Architecture

```
                 ┌────────────────────────────────────────────┐
                 │                docker compose               │
                 │                                            │
  ┌─────────┐    │  ┌───────────┐   HTTP   ┌───────────────┐  │
  │ Browser  │──────▶│ Streamlit │─────────▶│    FastAPI    │  │
  └─────────┘    │  │  (ui)     │          │    (api)      │  │
                 │  └───────────┘          └──────┬────────┘  │
                 │                                │           │
                 │            ┌───────────────────┼─────────┐ │
                 │            ▼                   ▼         ▼ │
                 │       ┌─────────┐        ┌─────────┐ ┌────────┐
                 │       │ Qdrant  │        │ SQLite  │ │ Groq   │
                 │       │(vectors)│        │(history)│ │ (LLM)  │
                 │       └─────────┘        └─────────┘ └────────┘
                 └────────────────────────────────────────────┘

  Offline pipeline (runs inside the api container, CLI entrypoint):
  scrape ──▶ data/raw ──▶ clean ──▶ data/clean ──▶ chunk ──▶ embed ──▶ Qdrant
```

**Query flow:** UI → `POST /chat` → load last N messages for session → embed query
→ Qdrant top-k retrieval → rerank → prompt assembly (history + context) → Groq
→ persist user+assistant turns → response with sources.

## 5. Design patterns (minimum 3, all load-bearing)

| Pattern | Type | Where | Why |
|---|---|---|---|
| **Factory** | Creational | `LLMProviderFactory` — builds the LLM client (Groq default; interface allows Ollama/OpenAI) from config | Decouples the pipeline from a vendor; providers swap via `.env` |
| **Strategy** | Behavioral | Retrieval strategy: `SimilaritySearch` vs `SimilarityWithRerank` | Rerank (bonus) becomes a pluggable strategy selected by config, not an if-branch |
| **Repository** | Structural | `ConversationRepository` (SQLite), `VectorRepository` (Qdrant) | Persistence hidden behind interfaces; storage engines replaceable and testable |
| **Chain of Responsibility** (4th, if time allows) | Behavioral | Ingestion pipeline: fetch → clean → chunk → embed → index as chained handlers | Each stage isolated, ordering explicit |

## 6. Data contracts

- **Raw page:** `data/raw/{url_hash}.html` + `data/raw/manifest.jsonl` (url, fetched_at, status)
- **Clean doc:** `data/clean/{url_hash}.json` → `{url, title, text, fetched_at}`
- **Chunk:** `{id, url, title, text, chunk_index}` → Qdrant payload
- **Message row (SQLite):** `id, session_id, role, content, sources, latency_ms, created_at`

## 7. API surface

| Endpoint | Purpose |
|---|---|
| `POST /chat` | `{session_id, message}` → `{answer, sources[]}` |
| `GET /sessions/{id}/history` | Full persisted history for a session |
| `GET /analytics/summary` | Metrics over all conversations: total sessions/messages, avg messages per session, avg latency, questions per day, top retrieved pages |
| `GET /health` | Liveness for compose healthchecks |

Analytics is also surfaced as a page in the Streamlit UI (FR6).

## 8. Configuration (`.env`)

`GROQ_API_KEY`, `LLM_MODEL`, `HISTORY_WINDOW_N`, `CHUNK_SIZE`, `CHUNK_OVERLAP`,
`TOP_K`, `RERANK_ENABLED`, `RERANK_TOP_K`, `EMBEDDING_MODEL`, `QDRANT_URL`,
`SCRAPE_MAX_PAGES`, `SCRAPE_BASE_URL`

## 9. Repository layout

```
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── README.md
├── src/
│   ├── config.py               # pydantic-settings
│   ├── scraper/                # fetch + clean (FR1, FR2)
│   ├── ingestion/              # chunk, embed, index (FR3)
│   ├── retrieval/              # strategies + reranker (Strategy)
│   ├── llm/                    # provider interface + factory (Factory)
│   ├── repositories/           # conversation + vector repos (Repository)
│   ├── services/               # chat service (history window, prompt assembly)
│   ├── analytics/              # metrics over history (FR6)
│   ├── api/                    # FastAPI app
│   └── ui/                     # Streamlit app
└── tests/                      # unit tests for core services
```

## 10. Delivery plan (maps to commit progression)

1. Scaffold: repo layout, config, docker skeleton, README stub
2. Scraper: crawl within domain, store raw + clean (FR1, FR2)
3. Ingestion: chunking, embeddings, Qdrant indexing (FR3)
4. Retrieval: similarity search strategy + reranker strategy (B1)
5. LLM: provider interface + Groq factory (Factory)
6. Chat service: history window N, prompt assembly, persistence (FR5)
7. API: FastAPI endpoints + error handling (B2)
8. UI: Streamlit chat + analytics page (FR4, FR6)
9. Docker: compose with app + ui + qdrant, one-command startup
10. Polish: README (patterns, stack justification, limitations, future work), tests

## 11. Assumptions & known limitations (to document in README)

- Scraping limited to `SCRAPE_MAX_PAGES` public pages within bancolombia.com, respecting robots.txt; no login-gated content
- BBVA Colombia (the site named in the brief) blocks all non-browser clients with HTTP 403 (CDN-level bot protection, verified 2026-07-04); the brief explicitly allows another bank, so Bancolombia was chosen — server-rendered, scrapable with plain HTTP
- Groq free tier is the default LLM; the Factory keeps the system vendor-neutral
- Spanish-first content; multilingual embedding model chosen accordingly
