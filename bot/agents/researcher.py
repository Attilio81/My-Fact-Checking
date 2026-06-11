import asyncio
import logging
from datetime import date

import httpx
from agno.agent import Agent
from agno.models.deepseek import DeepSeek
from tavily import TavilyClient

from bot.config import get_settings
from bot.models import Evidence, SearchQueries
from bot.sources import SourceRegistry
from bot.usage import record

logger = logging.getLogger(__name__)

_QUERY_PROMPT = """Sei un generatore di query di ricerca per il fact-checking di un claim.

Genera 2-3 query brevi e mirate per trovare evidenze sul claim, seguendo queste regole:
- Parole chiave essenziali, NON la frase intera del claim. Includi sempre i nomi
  propri delle entità (persone, enti, luoghi: "Ponte Stretto Procura Roma indagine").
- Angolazioni diverse: dato ufficiale/statistica, notizia, eventuale smentita.
- LINGUA: per fatti italiani domestici (procure, ministeri, politica interna,
  cronaca italiana) le query devono essere SOLO IN ITALIANO — query inglesi
  pescano rumore estero. L'inglese va usato (almeno una query) SOLO per fatti
  genuinamente internazionali: USA, guerre, aziende globali, scienza.
- is_current = true se il claim riguarda eventi recenti o valori che cambiano
  (prezzi, tassi, guerre in corso, dichiarazioni di attualità); false per fatti
  storici o scientifici consolidati."""

_MAX_RESULTS = 5
_SCRAPE_TOP_N = 3  # Firecrawl solo sulle prime N evidenze magre (costo)

# marker di paywall/cookie-wall: contenuto presente ma inutilizzabile
_PAYWALL_MARKERS = (
    "abbonati",
    "abbonamento",
    "accedi per leggere",
    "registrati per leggere",
    "contenuto riservato",
    "consenso ai cookie",
    "subscribe to read",
    "sign in to read",
    "create a free account",
)


def _is_thin(content: str) -> bool:
    """Contenuto inutilizzabile: troppo corto, o testa piena di marker paywall."""
    if len(content) < 500:
        return True
    head = content[:1200].lower()
    return any(m in head for m in _PAYWALL_MARKERS)
_FACTCHECK_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

_tavily: TavilyClient | None = None
_query_agent: Agent | None = None


def _get_query_agent() -> Agent:
    global _query_agent
    if _query_agent is None:
        _query_agent = Agent(
            model=DeepSeek(id="deepseek-v4-flash", temperature=0),
            instructions=_QUERY_PROMPT,
            output_schema=SearchQueries,
        )
    return _query_agent


async def _generate_queries(claim: str) -> SearchQueries:
    """Query mirate per il claim. Fallback: il claim stesso come unica query."""
    try:
        payload = f"Data odierna: {date.today().isoformat()}\nClaim: {claim}"
        response = await _get_query_agent().arun(payload)
        record(getattr(response, "metrics", None))
        if isinstance(response.content, SearchQueries) and response.content.queries:
            return response.content
    except Exception as e:
        logger.warning(f"Query generation fallita per '{claim}': {e}")
    return SearchQueries(queries=[claim], is_current=False)


def _get_tavily() -> TavilyClient:
    global _tavily
    if _tavily is None:
        _tavily = TavilyClient(api_key=get_settings().TAVILY_API_KEY.get_secret_value())
    return _tavily


async def _tavily_search(
    query: str, include_domains: list[str] | None, news: bool = False
) -> list[dict]:
    def _sync() -> list[dict]:
        kwargs = {
            "max_results": _MAX_RESULTS,
            "search_depth": "advanced",
            "include_raw_content": True,
        }
        if include_domains:
            kwargs["include_domains"] = include_domains
        if news:
            kwargs["topic"] = "news"
            kwargs["time_range"] = "year"
        return _get_tavily().search(query, **kwargs).get("results", [])

    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning(f"Tavily fallita per '{query}': {e}")
        return []


async def _factcheck_search(query: str) -> list[Evidence]:
    """Tier 0: Google Fact Check Tools API (ClaimReview). Skip se key assente.
    Nessun filtro lingua: la copertura italiana è scarsa, i fact-check
    internazionali (AFP, Reuters, Snopes) sono quasi tutti in inglese."""
    key = get_settings().GOOGLE_FACTCHECK_API_KEY
    if key is None:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _FACTCHECK_URL,
                params={"query": query, "key": key.get_secret_value()},
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
    Query mirate generate da un agente (incluso inglese per claim internazionali).
    Blacklist sempre esclusa. raw_content Tavily, Firecrawl come rinforzo."""
    sq = await _generate_queries(claim)

    evidences: list[Evidence] = []
    fc_seen: set[str] = set()
    for q in [claim, *sq.queries]:
        for ev in await _factcheck_search(q):
            if ev.url and ev.url not in fc_seen:
                fc_seen.add(ev.url)
                evidences.append(ev)
        if evidences:
            break  # primo match tier 0 basta, niente chiamate ridondanti

    results: list[dict] = []
    for q in sq.queries:
        results += await _tavily_search(q, registry.trusted_domains(), news=sq.is_current)
    if not results:
        for q in sq.queries:
            results += await _tavily_search(q, None, news=sq.is_current)
            if results:
                break

    seen_urls = {e.url for e in evidences}
    for r in results:
        url = r.get("url", "")
        if not url or url in seen_urls or registry.is_blacklisted(url):
            continue
        seen_urls.add(url)
        content = r.get("raw_content") or r.get("content") or ""
        evidences.append(
            Evidence(
                url=url,
                title=r.get("title", ""),
                content=content[:6000],
                tier=registry.tier_of(url),
            )
        )

    # Firecrawl dove Tavily non ha dato contenuto utilizzabile (corto o paywall)
    thin = [e for e in evidences if e.tier > 0 and _is_thin(e.content)]
    for ev in thin[:_SCRAPE_TOP_N]:
        full = await _scrape(ev.url)
        if full:
            ev.content = full

    return evidences[: _MAX_RESULTS + 3]
