from unittest.mock import patch


def _info(**kw):
    base = {"title": "Video title", "description": "caption del video", "uploader": "utente"}
    base.update(kw)
    return base


async def test_tiktok_extract_combines_caption_and_transcript(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("AUTHORIZED_USER_ID", "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
    monkeypatch.setenv("TAVILY_API_KEY", "tv")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "f")
    monkeypatch.setenv("OPENAI_API_KEY", "o")

    import bot.ingest.tiktok as tt

    class _FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            return _info()

    with patch.object(tt.yt_dlp, "YoutubeDL", _FakeYDL), patch.object(
        tt, "transcribe_audio", return_value="testo trascritto"
    ):
        result = await tt.extract("https://www.tiktok.com/@utente/video/1")

    assert result is not None
    assert "caption del video" in result["text"]
    assert "testo trascritto" in result["text"]
    assert result["title"] == "Video title"
