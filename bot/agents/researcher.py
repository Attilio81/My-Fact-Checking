import asyncio
import logging

import httpx
from tavily import TavilyClient

from bot.config import get_settings
from bot.models import Evidence
from bot.sources import SourceRegistry

logger = logging.getLogger(__name__)

_MAX_RESULTS = 5
_SCRAPE_TOP_N = 2  # Firecrawl solo sulle prime N evidenze (costo)
_FACTCHECK_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

_tavily: TavilyClient | None = None


def _get_tavily() -> TavilyClient:
    global _tavily
    if _tavily is None:
        _tavily = TavilyClient(api_key=get_settings().TAVILY_API_KEY.get_secret_value())
    return _tavily


async def _tavily_search(query: str, include_domains: list[str] | None) -> list[dict]:
    def _sync() -> list[dict]:
        kwargs = {"max_results": _MAX_RESULTS, "search_depth": "advanced"}
        if include_domains:
            kwargs["include_domains"] = include_domains
        return _get_tavily().search(query, **kwargs).get("results", [])

    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning(f"Tavily fallita per '{query}': {e}")
        return []


async def _factcheck_search(claim: str) -> list[Evidence]:
    """Tier 0: Google Fact Check Tools API (ClaimReview). Skip se key assente."""
    key = get_settings().GOOGLE_FACTCHECK_API_KEY
    if key is None:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _FACTCHECK_URL,
                params={"query": claim, "languageCode": "it", "key": key.get_secret_value()},
            )
            resp.raise_for_status()
        evidences = []
        for c in resp.json().get("claims", [])[:3]:
            for review in c.get("claimReview", [])[:1]:
                evidences.append(
                    Evidence(
                        url=review.get("url", ""),
                        title=review.get("title", ""),
                        content=(
                            f"Claim verificato: {c.get('text', '')}. "
                            f"Verdetto editoriale: {review.get('textualRating', '')} "
                            f"({review.get('publisher', {}).get('name', '')})"
                        ),
                        tier=0,
                    )
                )
        return evidences
    except Exception as e:
        logger.warning(f"FactCheck API fallita: {e}")
        return []


async def _scrape(url: str) -> str:
    """Firecrawl, contenuto completo. Stringa vuota su errore (fallback snippet Tavily)."""

    def _sync() -> str:
        from firecrawl.v1 import V1FirecrawlApp

        app = V1FirecrawlApp(api_key=get_settings().FIRECRAWL_API_KEY.get_secret_value())
        result = app.scrape_url(url, formats=["markdown"])
        return (result.markdown or "")[:6000]

    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning(f"Firecrawl fallito per {url}: {e}")
        return ""


async def gather_evidence(claim: str, registry: SourceRegistry) -> list[Evidence]:
    """Ordine spec: FactCheck API (tier 0) → Tavily domini fidati → Tavily aperto.
    Blacklist sempre esclusa. Firecrawl sulle prime evidenze, fallback snippet."""
    evidences = await _factcheck_search(claim)

    results = await _tavily_search(claim, registry.trusted_domains())
    if not results:
        results = await _tavily_search(claim, None)

    for r in results:
        url = r.get("url", "")
        if not url or registry.is_blacklisted(url):
            continue
        evidences.append(
            Evidence(
                url=url,
                title=r.get("title", ""),
                content=r.get("content", ""),
                tier=registry.tier_of(url),
            )
        )

    for ev in [e for e in evidences if e.tier > 0][:_SCRAPE_TOP_N]:
        full = await _scrape(ev.url)
        if full:
            ev.content = full

    return evidences[: _MAX_RESULTS + 3]
