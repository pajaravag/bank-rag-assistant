"""Crawls the target site breadth-first and stores raw HTML locally.

Raw pages land in `data/raw/{url_hash}.html` plus a `manifest.jsonl`
recording url, status, timestamp and content hash for each fetch.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import xml.etree.ElementTree as ET
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


def parse_sitemap(xml_text: str) -> tuple[list[str], list[str]]:
    """Parses a sitemap document into (child_sitemaps, page_urls).

    A <sitemapindex> yields child sitemaps; a <urlset> yields page URLs.
    Malformed XML yields nothing (the crawl falls back to plain BFS).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return [], []
    locs = [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
    if root.tag.endswith("sitemapindex"):
        return locs, []
    return [], locs


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
        sitemap_seed: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.domain = urlparse(base_url).netloc
        self.raw_dir = Path(raw_dir)
        self.max_pages = max_pages
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.sitemap_seed = sitemap_seed
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

    def _sitemap_urls(self) -> list[str]:
        """In-scope page URLs declared in the site's official sitemaps.

        Sitemap locations come from robots.txt (`Sitemap:` directives),
        falling back to the conventional /sitemap-index.xml and
        /sitemap.xml. Guarantees coverage of pages that BFS link-following
        alone might never reach.
        """
        scheme = urlparse(self.base_url).scheme
        root = f"{scheme}://{self.domain}"
        candidates: list[str] = []
        try:
            resp = httpx.get(
                f"{root}/robots.txt", headers={"User-Agent": USER_AGENT},
                timeout=self.timeout_seconds, follow_redirects=True,
            )
            candidates = [
                line.split(":", 1)[1].strip()
                for line in resp.text.splitlines()
                if line.lower().startswith("sitemap:")
            ]
        except httpx.HTTPError:
            pass
        if not candidates:
            candidates = [f"{root}/sitemap-index.xml", f"{root}/sitemap.xml"]

        urls: list[str] = []
        visited: set[str] = set()
        queue = list(candidates)
        while queue and len(visited) < 30:  # safety cap on sitemap fan-out
            sitemap_url = queue.pop(0)
            if sitemap_url in visited:
                continue
            visited.add(sitemap_url)
            try:
                resp = httpx.get(
                    sitemap_url, headers={"User-Agent": USER_AGENT},
                    timeout=self.timeout_seconds, follow_redirects=True,
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Could not fetch sitemap %s: %s", sitemap_url, exc)
                continue
            child_maps, page_urls = parse_sitemap(resp.text)
            queue.extend(child_maps)
            urls.extend(u for u in page_urls if self._in_scope(u))

        logger.info("Sitemap seeding: %d URLs from %d sitemap(s)", len(urls), len(visited))
        return urls

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
        if self.sitemap_seed:
            for url in self._sitemap_urls():
                if url not in queue:
                    queue.append(url)
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
