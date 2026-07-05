"""CLI entrypoint: `python -m src.scraper [--max-pages N]`.

Fetches raw pages then produces clean documents (FR1 + FR2).
"""

import argparse
import logging

from src.config import get_settings
from src.scraper.cleaner import DocumentCleaner
from src.scraper.fetcher import SiteFetcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Scrape the target bank site")
    parser.add_argument("--max-pages", type=int, default=settings.scrape_max_pages)
    parser.add_argument("--skip-fetch", action="store_true", help="Only re-run cleaning")
    args = parser.parse_args()

    if not args.skip_fetch:
        fetcher = SiteFetcher(
            base_url=settings.scrape_base_url,
            raw_dir=settings.raw_dir,
            max_pages=args.max_pages,
            delay_seconds=settings.scrape_delay_seconds,
            timeout_seconds=settings.scrape_timeout_seconds,
            sitemap_seed=settings.sitemap_seed,
        )
        results = fetcher.crawl()
        logging.info("Fetched %d pages", len(results))

    cleaned = DocumentCleaner(settings.raw_dir, settings.clean_dir).run()
    logging.info("Done: %d clean documents", cleaned)


if __name__ == "__main__":
    main()
