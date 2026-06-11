import asyncio
import logging

logger = logging.getLogger(__name__)


async def _scrape(url: str) -> str:
    def _sync() -> str:
        from firecrawl.v1 import V1FirecrawlApp

        from bot.config import get_settings

        app = V1FirecrawlApp(api_key=get_settings().FIRECRAWL_API_KEY.get_secret_value())
        result = app.scrape_url(url, formats=["markdown"])
        return result.markdown or ""

    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning(f"Scraping articolo fallito per {url}: {e}")
        return ""


async def extract(url: str) -> dict | None:
    """URL articolo → {text, source_url, title}. None su fallimento."""
    text = await _scrape(url)
    if not text.strip():
        return None
    title = next(
        (l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#")), url
    )
    return {"text": text[:12000], "source_url": url, "title": title}
