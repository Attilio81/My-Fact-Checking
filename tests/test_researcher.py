from unittest.mock import AsyncMock, patch

from bot.models import SearchQueries
from bot.sources import SourceRegistry

REG = SourceRegistry(
    tier0=["snopes.com"], tier1=["istat.it"], tier2=["corriere.it"], blacklist=["fake.example"]
)

_ONE_QUERY = SearchQueries(queries=["claim"], is_current=False)


def _tavily_result(url, content="testo evidenza", raw=None):
    r = {"url": url, "title": "T", "content": content}
    if raw is not None:
        r["raw_content"] = raw
    return r


def _patches(tavily_side_effect):
    return (
        patch("bot.agents.researcher._generate_queries", AsyncMock(return_value=_ONE_QUERY)),
        patch("bot.agents.researcher._tavily_search", AsyncMock(side_effect=tavily_side_effect)),
        patch("bot.agents.researcher._factcheck_search", AsyncMock(return_value=[])),
        patch("bot.agents.researcher._scrape", AsyncMock(return_value="")),
    )


async def test_search_assigns_tiers():
    p1, p2, p3, p4 = _patches([[_tavily_result("https://www.istat.it/a")], []])
    with p1, p2, p3, p4:
        from bot.agents.researcher import gather_evidence

        evs = await gather_evidence("claim", REG)
    assert evs[0].tier == 1


async def test_blacklist_filtered():
    p1, p2, p3, p4 = _patches([[_tavily_result("https://fake.example/x")], []])
    with p1, p2, p3, p4:
        from bot.agents.researcher import gather_evidence

        evs = await gather_evidence("claim", REG)
    assert evs == []


async def test_raw_content_preferred_and_dedup():
    dup = _tavily_result("https://www.istat.it/a", content="snippet", raw="contenuto pieno")
    p1, p2, p3, p4 = _patches([[dup, dup], []])
    with p1, p2, p3, p4:
        from bot.agents.researcher import gather_evidence

        evs = await gather_evidence("claim", REG)
    assert len(evs) == 1
    assert evs[0].content == "contenuto pieno"


async def test_query_generation_fallback_on_error():
    from bot.agents.researcher import _generate_queries

    with patch("bot.agents.researcher._get_query_agent") as ga:
        ga.return_value.arun = AsyncMock(side_effect=RuntimeError("down"))
        sq = await _generate_queries("il PIL è cresciuto")
    assert sq.queries == ["il PIL è cresciuto"]
