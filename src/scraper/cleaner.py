"""Turns raw HTML pages into clean text documents.

Reads `data/raw/manifest.jsonl`, strips boilerplate (nav, scripts,
footer, forms) and writes one JSON per page to `data/clean/`.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

from src.scraper.fetcher import url_hash

logger = logging.getLogger(__name__)

BOILERPLATE_TAGS = ("script", "style", "noscript", "nav", "header", "footer", "form", "iframe", "svg")

# Icon-font tokens leak into text as kebab-case identifiers (angle-right-small, ...)
_ICON_TOKEN_RE = re.compile(r"^[a-z]+(?:-[a-z0-9]+)+$")

# Pure call-to-action lines that carry no information
_CTA_LINES = {
    "conocer más", "conoce más", "ver más", "saber más", "más información",
    "leer más", "quiero saber más", "solicitar", "solicitar ahora",
}


def _is_noise(line: str) -> bool:
    lowered = line.lower()
    if len(line) <= 2:
        return True
    if _ICON_TOKEN_RE.fullmatch(lowered) and len(line) < 40:
        return True
    return lowered in _CTA_LINES


def clean_html(html: str) -> tuple[str, str]:
    """Returns (title, text) extracted from raw HTML."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""

    for tag in soup.find_all(BOILERPLATE_TAGS):
        tag.decompose()

    main = soup.find("main") or soup.body or soup
    lines = [line.strip() for line in main.get_text("\n").splitlines()]

    # Drop noise and repeated blocks (carousels duplicate whole sections)
    seen: set[str] = set()
    kept: list[str] = []
    for line in lines:
        if _is_noise(line):
            continue
        key = " ".join(line.lower().split())
        if key in seen:
            continue
        seen.add(key)
        kept.append(line)
    return title, "\n".join(kept)


class DocumentCleaner:
    def __init__(self, raw_dir: str, clean_dir: str) -> None:
        self.raw_dir = Path(raw_dir)
        self.clean_dir = Path(clean_dir)

    def run(self) -> int:
        self.clean_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.raw_dir / "manifest.jsonl"
        if not manifest_path.exists():
            logger.error("No manifest found at %s — run the fetcher first", manifest_path)
            return 0

        seen_urls: set[str] = set()
        count = 0
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            url = entry["url"]
            if url in seen_urls:  # manifest is append-only; keep latest occurrence only once
                continue
            seen_urls.add(url)

            raw_path = Path(entry["path"])
            if not raw_path.exists():
                continue

            title, text = clean_html(raw_path.read_text(encoding="utf-8"))
            if len(text) < 200:  # skip near-empty pages
                logger.info("Skipping %s (only %d chars of text)", url, len(text))
                continue

            out = {
                "url": url,
                "title": title,
                "text": text,
                "fetched_at": entry["fetched_at"],
            }
            out_path = self.clean_dir / f"{url_hash(url)}.json"
            out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            count += 1

        logger.info("Cleaned %d documents into %s", count, self.clean_dir)
        return count
