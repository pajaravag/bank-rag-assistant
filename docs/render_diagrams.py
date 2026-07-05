"""Renders the project diagrams to PNG locally using Graphviz.

Usage: python docs/render_diagrams.py   (requires `dot` on PATH)
"""

import pathlib
import subprocess

OUT_DIR = pathlib.Path(__file__).parent / "img"

FONT = "Helvetica"

STYLE = f"""
    graph [fontname="{FONT}", fontsize=13, pad=0.4, nodesep=0.45, ranksep=0.55,
           splines=spline, bgcolor="white"];
    node  [fontname="{FONT}", fontsize=12, shape=box, style="rounded,filled",
           color="#94A3B8", fillcolor="#F8FAFC", penwidth=1.2, margin="0.22,0.12"];
    edge  [fontname="{FONT}", fontsize=11, color="#64748B", penwidth=1.1,
           arrowsize=0.8, labeldistance=2];
"""

# Component palette
UI_STYLE = 'fillcolor="#DBEAFE", color="#2563EB"'
API_STYLE = 'fillcolor="#BFDBFE", color="#1D4ED8"'
DATA_STYLE = 'shape=cylinder, fillcolor="#FEF3C7", color="#D97706"'
OBS_STYLE = 'fillcolor="#EDE9FE", color="#7C3AED"'
JOB_STYLE = 'fillcolor="#D1FAE5", color="#059669"'
EXT_STYLE = 'fillcolor="#F3F4F6", color="#6B7280", style="rounded,filled,dashed"'
DECISION = 'shape=diamond, fillcolor="#FEF9C3", color="#CA8A04", margin="0.05,0.05"'
END_BAD = 'fillcolor="#FEE2E2", color="#DC2626"'
END_GOOD = 'fillcolor="#DCFCE7", color="#16A34A"'
PROC = 'fillcolor="#F1F5F9", color="#64748B"'
HL = 'fillcolor="#E0F2FE", color="#0284C7"'

ARCHITECTURE = f"""
digraph architecture {{
    rankdir=LR;
    {STYLE}
    subgraph cluster_compose {{
        label="docker compose";
        fontsize=14; fontcolor="#475569";
        style="rounded,filled"; fillcolor="#F8FAFC"; color="#CBD5E1";
        ui      [label="Streamlit UI\\n:8501", {UI_STYLE}];
        api     [label="FastAPI\\n:8100", {API_STYLE}];
        qdrant  [label="Qdrant\\n:6333", {DATA_STYLE}];
        sqlite  [label="SQLite\\nhistorial", {DATA_STYLE}];
        phoenix [label="Phoenix\\n:6006", {OBS_STYLE}];
        ingest  [label="ingest\\n(one-shot)", {JOB_STYLE}];
    }}
    groq [label="Groq API\\nLlama 3.x", {EXT_STYLE}];
    web  [label="bancolombia.com", {EXT_STYLE}];

    ui -> api [label="HTTP"];
    api -> qdrant [label="búsqueda\\nvectorial"];
    api -> sqlite [label="historial"];
    api -> phoenix [label="trazas OTel", style=dashed];
    api -> groq [label="LLM"];
    web -> ingest [label="scraping"];
    ingest -> qdrant [label="indexación"];
}}
"""

SCRAPING = f"""
digraph scraping {{
    rankdir=TB;
    {STYLE}
    seed    [label="URL semilla\\nbancolombia.com", {HL}];
    sitemap [label="Sembrar cola con sitemaps oficiales\\nrobots.txt → sitemap-index (~830 URLs)\\ncobertura garantizada + BFS descubre extras", {HL}];
    robots  [label="¿robots.txt\\npermite?", {DECISION}];
    fetch   [label="GET con User-Agent propio\\ndelay 0.4 s · timeout 15 s", {PROC}];
    okhtml  [label="¿200 y\\ntext/html?", {DECISION}];
    raw     [label="Guardar crudo (FR2)\\ndata/raw/{{hash}}.html\\n+ manifest.jsonl", {HL}];
    links   [label="Extraer enlaces <a href>", {PROC}];
    scope   [label="¿mismo dominio,\\nno binario, no visto?", {DECISION}];
    queue   [label="Encolar (BFS)", {PROC}];
    maxq    [label="¿150 páginas\\nalcanzadas?", {DECISION}];
    clean1  [label="LIMPIEZA\\nquitar script · nav · header\\nfooter · form · iframe · svg", {PROC}];
    clean2  [label="Filtrar ruido\\ntokens de iconos · líneas CTA\\nbloques duplicados (carruseles)", {PROC}];
    minlen  [label="¿texto útil\\n> 200 chars?", {DECISION}];
    cleanok [label="Guardar limpio (FR2)\\ndata/clean/{{hash}}.json\\nurl · título · texto · fecha", {END_GOOD}];
    discard [label="descartar", {END_BAD}];

    seed -> sitemap;
    sitemap -> robots;
    robots -> fetch [label="sí"];
    robots -> discard [label="no"];
    fetch -> okhtml;
    okhtml -> raw [label="sí"];
    okhtml -> discard [label="no"];
    raw -> links;
    links -> scope;
    scope -> queue [label="sí"];
    queue -> maxq;
    maxq -> robots [label="no·\\nsiguiente URL"];
    maxq -> clean1 [label="sí"];
    clean1 -> clean2;
    clean2 -> minlen;
    minlen -> cleanok [label="sí"];
    minlen -> discard [label="no"];
}}
"""

RETRIEVAL = f"""
digraph retrieval {{
    rankdir=TB;
    {STYLE}
    q        [label="Pregunta del usuario\\n+ últimos N mensajes", {HL}];
    hashist  [label="¿hay historial?\\n(posible seguimiento)", {DECISION}];
    condense [label="CONDENSACIÓN · Llama 3.1 8B\\nreescribe como pregunta autónoma\\nguardas: 1 línea, ≤ 250 chars", {PROC}];
    embed    [label="Embedding de la consulta\\nmultilingual-e5 · prefijo \\"query:\\"", {PROC}];
    search   [label="Qdrant · top-8\\nsimilitud coseno", {PROC}];
    dedupe   [label="Deduplicar fragmentos\\ncasi idénticos", {PROC}];
    rerank   [label="RERANK · cross-encoder mmarco\\npuntúa cada par (pregunta, fragmento)", {PROC}];
    gate     [label="¿algún score\\n≥ −5.0?", {DECISION}];
    nocontext [label="Respuesta honesta SIN llamar al LLM\\nflag no_context → métrica de cobertura", {END_BAD}];
    prompt   [label="Prompt\\nsistema: solo contexto, citar fuentes\\n+ historial (N) + top-4 fragmentos", {PROC}];
    llm      [label="Groq · Llama 3.3 70B\\nretry con backoff · fallback 8B", {PROC}];
    answer   [label="Respuesta con fuentes\\npersistida con tokens y latencia", {END_GOOD}];

    q -> hashist;
    hashist -> condense [label="sí"];
    hashist -> embed [label="no"];
    condense -> embed;
    embed -> search;
    search -> dedupe;
    dedupe -> rerank;
    rerank -> gate;
    gate -> nocontext [label="no"];
    gate -> prompt [label="sí"];
    prompt -> llm;
    llm -> answer;
}}
"""


def render(source: str, filename: str) -> None:
    out = OUT_DIR / filename
    subprocess.run(
        ["dot", "-Tpng", "-Gdpi=180", "-o", str(out)],
        input=source.encode(),
        check=True,
    )
    print(f"{out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    render(ARCHITECTURE, "architecture.png")
    render(SCRAPING, "scraping-flow.png")
    render(RETRIEVAL, "retrieval-flow.png")
