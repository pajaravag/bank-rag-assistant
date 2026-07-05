from src.scraper.fetcher import parse_sitemap

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://x.co/sitemap-personas.xml</loc></sitemap>
  <sitemap><loc>https://x.co/sitemap-empresas.xml</loc></sitemap>
</sitemapindex>"""

URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://x.co/personas</loc><lastmod>2025-08-21</lastmod></url>
  <url><loc>https://x.co/personas/creditos</loc></url>
</urlset>"""


def test_sitemap_index_yields_child_sitemaps():
    children, urls = parse_sitemap(SITEMAP_INDEX)
    assert children == [
        "https://x.co/sitemap-personas.xml",
        "https://x.co/sitemap-empresas.xml",
    ]
    assert urls == []


def test_urlset_yields_page_urls():
    children, urls = parse_sitemap(URLSET)
    assert children == []
    assert urls == ["https://x.co/personas", "https://x.co/personas/creditos"]


def test_malformed_xml_yields_nothing():
    assert parse_sitemap("this is not xml <<<") == ([], [])
    assert parse_sitemap("") == ([], [])
