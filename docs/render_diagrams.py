"""Renders the project's Mermaid diagrams to PNG via mermaid.ink.

Usage: python docs/render_diagrams.py
Only the diagram source text is sent to the rendering service.
"""

import base64
import json
import pathlib

import httpx

OUT_DIR = pathlib.Path(__file__).parent / "img"

ARCHITECTURE = """flowchart LR
    subgraph compose["docker compose"]
        UI["Streamlit UI<br/>:8501"] -->|HTTP| API["FastAPI<br/>:8100"]
        API --> QD[("Qdrant<br/>:6333")]
        API --> SQ[("SQLite<br/>historial")]
        API -.->|OTel traces| PH["Phoenix<br/>:6006"]
        ING["ingest (one-shot)"] -->|scrape + index| QD
    end
    API -->|LLM| GROQ["Groq API<br/>Llama 3.x"]
    ING -->|crawl| WEB["bancolombia.com"]"""

SCRAPING = """flowchart TD
    A["URL semilla<br/>bancolombia.com"] --> B{"robots.txt<br/>permite?"}
    B -- no --> SKIP["descartar URL"]
    B -- si --> C["GET con User-Agent propio<br/>+ delay 0.4s"]
    C --> D{"200 y<br/>text/html?"}
    D -- no --> SKIP
    D -- si --> E["Guardar HTML crudo<br/>data/raw/hash.html<br/>+ manifest.jsonl"]
    E --> F["Extraer enlaces"]
    F --> G{"mismo dominio,<br/>no binario,<br/>no visto?"}
    G -- si --> H["Encolar (BFS)"]
    H --> B
    G -- no --> SKIP2["ignorar"]
    E --> I{"llego a max<br/>150 paginas?"}
    I -- no --> B
    I -- si --> J["FASE DE LIMPIEZA"]
    J --> K["Quitar script / nav / header /<br/>footer / form / iframe / svg"]
    K --> L["Filtrar ruido: tokens de iconos,<br/>lineas CTA, bloques duplicados"]
    L --> M{"texto util mayor a<br/>200 caracteres?"}
    M -- no --> SKIP3["descartar pagina"]
    M -- si --> N["data/clean/hash.json<br/>url + titulo + texto + fecha"]"""

RETRIEVAL = """flowchart TD
    Q["Pregunta del usuario<br/>+ ultimos N mensajes"] --> C{"hay historial?<br/>(posible seguimiento)"}
    C -- si --> CO["CONDENSACION - Llama 3.1 8B<br/>reescribe como pregunta autonoma<br/>guardas: 1 linea, max 250 chars"]
    C -- no --> E
    CO --> E["Embedding de la consulta<br/>e5 con prefijo query:"]
    E --> V["Qdrant: top-8 por<br/>similitud coseno"]
    V --> DD["Deduplicar fragmentos<br/>casi identicos"]
    DD --> RR["RERANK cross-encoder mmarco<br/>puntua cada par pregunta-fragmento"]
    RR --> TH{"algun score<br/>mayor o igual a -5.0?"}
    TH -- no --> NC["Respuesta honesta SIN llamar al LLM<br/>+ flag no_context<br/>alimenta metrica de cobertura"]
    TH -- si --> P["Prompt: sistema exige responder solo<br/>con contexto y citar fuentes<br/>+ historial N + top-4 fragmentos"]
    P --> LLM["Groq Llama 3.3 70B<br/>retry con backoff + fallback 8B"]
    LLM --> R["Respuesta con fuentes, persistida<br/>con tokens y latencia"]"""


def render(code: str, filename: str, width: int = 1200) -> None:
    payload = json.dumps({"code": code, "mermaid": {"theme": "neutral"}})
    b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    url = f"https://mermaid.ink/img/{b64}?type=png&width={width}&scale=2"
    resp = httpx.get(url, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    out = OUT_DIR / filename
    out.write_bytes(resp.content)
    print(f"{out} ({len(resp.content)} bytes)")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    render(ARCHITECTURE, "architecture.png", width=1400)
    render(SCRAPING, "scraping-flow.png", width=1100)
    render(RETRIEVAL, "retrieval-flow.png", width=1100)
