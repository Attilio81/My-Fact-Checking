from unittest.mock import AsyncMock, patch


async def test_article_uses_firecrawl():
    with patch("bot.ingest.article._scrape", AsyncMock(return_value="# Titolo\ncorpo")):
        from bot.ingest.article import extract

        result = await extract("https://news.example/a")
    assert result is not None and "corpo" in result["text"]
    assert result["title"] == "Titolo"


async def test_article_failure_returns_none():
    with patch("bot.ingest.article._scrape", AsyncMock(return_value="")):
        from bot.ingest.article import extract

        assert await extract("https://news.example/a") is None
