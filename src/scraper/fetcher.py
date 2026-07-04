"""Crawls the target site breadth-first and stores raw HTML locally.

Raw pages land in `data/raw/{url_hash}.html` plus a `manifest.jsonl`
recording url, status, timestamp and content hash for each fetch.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from urllib import robotparser
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = "bank-rag-assistant/0.1 (+https://github.com/pajaravag/bank-rag-assistant)"

SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".mp4", ".mp3", ".zip", ".xlsx", ".docx", ".woff", ".woff2",
)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


@dataclass
class FetchResult:
    url: str
    status: int
    path: str | None


class SiteFetcher:
    """Same-domain BFS crawler with robots.txt support and polite delays."""

    def __init__(
        self,
        base_url: str,
        raw_dir: str,
        max_pages: int = 150,
        delay_seconds: float = 0.4,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.domain = urlparse(base_url).netloc
        self.raw_dir = Path(raw_dir)
        self.max_pages = max_pages
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.robots = self._load_robots()

    def _load_robots(self) -> robotparser.RobotFileParser:
        rp = robotparser.RobotFileParser()
        robots_url = f"{urlparse(self.base_url).scheme}://{self.domain}/robots.txt"
        try:
            resp = httpx.get(
                robots_url,
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp.parse([])
        except httpx.HTTPError:
            logger.warning("Could not fetch robots.txt; assuming allow-all")
            rp.parse([])
        return rp

    def _allowed(self, url: str) -> bool:
        return self.robots.can_fetch(USER_AGENT, url)

    def _in_scope(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc != self.domain:
            return False
        if parsed.path.lower().endswith(SKIP_EXTENSIONS):
            return False
        return parsed.scheme in ("http", "https")

    def _extract_links(self, html: str, current_url: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        links = []
        for anchor in soup.find_all("a", href=True):
            absolute, _ = urldefrag(urljoin(current_url, anchor["href"]))
            if self._in_scope(absolute):
                links.append(absolute)
        return links

    def crawl(self) -> list[FetchResult]:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.raw_dir / "manifest.jsonl"
        results: list[FetchResult] = []
        queue: list[str] = [self.base_url + "/"]
        seen: set[str] = set(queue)

        with httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "es-CO,es;q=0.9"},
            timeout=self.timeout_seconds,
            follow_redirects=True,
        ) as client, manifest_path.open("a", encoding="utf-8") as manifest:
            while queue and len(results) < self.max_pages:
                url = queue.pop(0)
                if not self._allowed(url):
                    logger.info("robots.txt disallows %s", url)
                    continue
                try:
                    resp = client.get(url)
                except httpx.HTTPError as exc:
                    logger.warning("Fetch failed %s: %s", url, exc)
                    continue

                content_type = resp.headers.get("content-type", "")
                if resp.status_code != 200 or "text/html" not in content_type:
                    continue

                path = self.raw_dir / f"{url_hash(url)}.html"
                path.write_text(resp.text, encoding="utf-8")
                manifest.write(
                    json.dumps(
                        {
                            "url": url,
                            "status": resp.status_code,
                            "path": str(path),
                            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                results.append(FetchResult(url=url, status=resp.status_code, path=str(path)))
                logger.info("[%d/%d] %s", len(results), self.max_pages, url)

                for link in self._extract_links(resp.text, url):
                    if link not in seen:
                        seen.add(link)
                        queue.append(link)

                time.sleep(self.delay_seconds)

        return results
