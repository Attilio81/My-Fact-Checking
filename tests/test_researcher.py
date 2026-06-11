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


async def test_paywall_triggers_scrape():
    paywall = "Abbonati per leggere questo articolo. " * 20  # >500 char ma inutilizzabile
    p1, p2, p3, _ = _patches([[_tavily_result("https://www.istat.it/a", content=paywall)], []])
    with p1, p2, p3, patch(
        "bot.agents.researcher._scrape", AsyncMock(return_value="articolo completo dopo scrape")
    ):
        from bot.agents.researcher import gather_evidence

        evs = await gather_evidence("claim", REG)
    assert evs[0].content == "articolo completo dopo scrape"


def test_is_thin_detection():
    from bot.agents.researcher import _is_thin

    assert _is_thin("corto") is True
    assert _is_thin("Abbonati per continuare a leggere. " + "x" * 600) is True
    assert _is_thin("Testo di articolo vero e sostanzioso. " * 30) is False


async def test_irrelevant_filtered_and_open_fallback():
    claim = "La Procura di Roma indaga sul Ponte sullo Stretto di Messina"
    noise = _tavily_result("https://www.bbc.com/korea", content="Korea bridge scandal in Seoul")
    good = _tavily_result(
        "https://www.open.online/ponte",
        content="La Procura di Roma indaga per corruzione sul Ponte sullo Stretto",
    )
    p1, p2, p3, p4 = _patches([[noise], [good]])
    with p1, p2, p3, p4:
        from bot.agents.researcher import gather_evidence

        evs = await gather_evidence(claim, REG)
    assert [e.url for e in evs] == ["https://www.open.online/ponte"]


def test_claim_keys_extraction():
    from bot.agents.researcher import _claim_keys

    keys = _claim_keys("La Procura di Roma indaga sul Ponte: costo 13,5 miliardi")
    assert {"procura", "roma", "ponte", "13,5"} <= keys
    assert "la" not in keys


def test_relevance_word_boundary_no_substring():
    from bot.agents.researcher import _is_relevant
    from bot.models import Evidence

    # 'conti' NON deve matchare 'continued', 'ros' NON deve matchare 'prosecutors'
    noise = Evidence(url="https://x.com", content="Prosecutors continued the investigation in Seoul.")
    assert _is_relevant(noise, {"conti", "ros"}) is False

    good = Evidence(url="https://y.it", content="Il Ros ha indagato; la Corte dei Conti ha deciso.")
    assert _is_relevant(good, {"conti", "ros"}) is True


def test_relevance_requires_two_hits_with_many_keys():
    from bot.agents.researcher import _is_relevant
    from bot.models import Evidence

    keys = {"procura", "roma", "ponte", "stretto", "messina"}
    one_hit = Evidence(url="https://z.com", content="AS Roma won the match yesterday.")
    assert _is_relevant(one_hit, keys) is False
    two_hits = Evidence(url="https://w.it", content="Il ponte sullo stretto approvato.")
    assert _is_relevant(two_hits, keys) is True


async def test_news_search_used_for_current_claims():
    claim = "La Procura di Roma indaga sul Ponte sullo Stretto"
    current = SearchQueries(queries=["q"], is_current=True)
    news_item = {
        "url": "https://www.ansa.it/ponte-indagine",
        "title": "Procura Roma, indagine Ponte Stretto",
        "content": "La Procura di Roma indaga sul Ponte sullo Stretto",
    }
    with patch(
        "bot.agents.researcher._generate_queries", AsyncMock(return_value=current)
    ), patch(
        "bot.agents.researcher._tavily_search", AsyncMock(return_value=[])
    ), patch(
        "bot.agents.researcher._factcheck_search", AsyncMock(return_value=[])
    ), patch(
        "bot.agents.researcher._news_search", AsyncMock(return_value=[news_item])
    ), patch(
        "bot.agents.researcher._scrape", AsyncMock(return_value="")
    ):
        from bot.agents.researcher import gather_evidence

        evs = await gather_evidence(claim, REG)
    assert any(e.url == "https://www.ansa.it/ponte-indagine" for e in evs)


async def test_pool_reused_and_enriched():
    from bot.models import Evidence

    claim = "Nel paper Agents of Chaos gli agenti hanno mentito"
    pool = [
        Evidence(url="https://arxiv.org/abs/1", title="Agents of Chaos",
                 content="agents of chaos: agents reported task completion falsely", tier=1),
        Evidence(url="https://altro.example/x", title="Altro",
                 content="contenuto su tutt'altro tema senza parole chiave", tier=3),
    ]
    new_result = _tavily_result(
        "https://www.ansa.it/chaos", content="il paper Agents of Chaos documenta agenti"
    )
    p1, p2, p3, p4 = _patches([[new_result], []])
    with p1, p2, p3, p4:
        from bot.agents.researcher import gather_evidence

        evs = await gather_evidence(claim, REG, pool=pool)
    urls = [e.url for e in evs]
    assert "https://arxiv.org/abs/1" in urls  # riusata dal pool (pertinente)
    assert "https://altro.example/x" not in urls  # pool ma non pertinente
    assert "https://www.ansa.it/chaos" in urls  # nuova
    assert any(e.url == "https://www.ansa.it/chaos" for e in pool)  # pool arricchito


async def test_fetch_context_documents_only_primary():
    from bot.agents.researcher import fetch_context_documents

    text = (
        "Guarda questo paper https://arxiv.org/abs/2602.20021 e questo blog "
        "https://blogqualsiasi.example/post e i dati https://www.istat.it/dati/x"
    )
    scraped = []

    async def fake_scrape(url):
        scraped.append(url)
        return f"contenuto di {url}"

    with patch("bot.agents.researcher._scrape", side_effect=fake_scrape):
        docs = await fetch_context_documents(text, REG)

    assert [d.url for d in docs] == [
        "https://arxiv.org/abs/2602.20021",
        "https://www.istat.it/dati/x",
    ]
    assert "https://blogqualsiasi.example/post" not in scraped
    assert all(d.tier <= 1 for d in docs)
    assert all(d.is_context for d in docs)


async def test_fetch_context_documents_arxiv_id_and_bare_links():
    from bot.agents.researcher import fetch_context_documents

    text = "Nuovo studio pazzesco! Paper: arXiv:2602.20021 (su arxiv.org/abs/2602.20021)"

    async def fake_scrape(url):
        return "abstract del paper"

    with patch("bot.agents.researcher._scrape", side_effect=fake_scrape):
        docs = await fetch_context_documents(text, REG)

    assert [d.url for d in docs] == ["https://arxiv.org/abs/2602.20021"]


async def test_context_doc_bypasses_relevance_filter():
    from bot.models import Evidence

    claim = "Secondo il paper, alcuni agenti hanno mentito"  # nessuna entità utile
    pool = [
        Evidence(url="https://arxiv.org/abs/1", title="documento citato nel contenuto",
                 content="agents reported task completion falsely", tier=1, is_context=True)
    ]
    p1, p2, p3, p4 = _patches([[], []])
    with p1, p2, p3, p4:
        from bot.agents.researcher import gather_evidence

        evs = await gather_evidence(claim, REG, pool=pool)
    assert any(e.url == "https://arxiv.org/abs/1" for e in evs)


async def test_query_generation_fallback_on_error():
    from bot.agents.researcher import _generate_queries

    with patch("bot.agents.researcher._get_query_agent") as ga:
        ga.return_value.arun = AsyncMock(side_effect=RuntimeError("down"))
        sq = await _generate_queries("il PIL è cresciuto")
    assert sq.queries == ["il PIL è cresciuto"]
