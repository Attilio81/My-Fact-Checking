from unittest.mock import AsyncMock, patch

from bot.sources import SourceRegistry

REG = SourceRegistry(
    tier0=["snopes.com"], tier1=["istat.it"], tier2=["corriere.it"], blacklist=["fake.example"]
)


def _tavily_result(url, content="testo evidenza"):
    return {"url": url, "title": "T", "content": content}


async def test_search_assigns_tiers():
    with patch(
        "bot.agents.researcher._tavily_search",
        AsyncMock(side_effect=[[_tavily_result("https://www.istat.it/a")], []]),
    ), patch(
        "bot.agents.researcher._factcheck_search", AsyncMock(return_value=[])
    ), patch(
        "bot.agents.researcher._scrape", AsyncMock(return_value="")
    ):
        from bot.agents.researcher import gather_evidence

        evs = await gather_evidence("claim", REG)
    assert evs[0].tier == 1


async def test_blacklist_filtered():
    with patch(
        "bot.agents.researcher._tavily_search",
        AsyncMock(side_effect=[[_tavily_result("https://fake.example/x")], []]),
    ), patch(
        "bot.agents.researcher._factcheck_search", AsyncMock(return_value=[])
    ), patch(
        "bot.agents.researcher._scrape", AsyncMock(return_value="")
    ):
        from bot.agents.researcher import gather_evidence

        evs = await gather_evidence("claim", REG)
    assert evs == []
