def test_settings_from_env(monkeypatch):
    for k, v in {
        "TELEGRAM_BOT_TOKEN": "t",
        "AUTHORIZED_USER_ID": "1",
        "DEEPSEEK_API_KEY": "d",
        "TAVILY_API_KEY": "tv",
        "FIRECRAWL_API_KEY": "f",
        "OPENAI_API_KEY": "o",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GOOGLE_FACTCHECK_API_KEY", raising=False)
    from bot.config import Settings

    s = Settings(_env_file=None)
    assert s.AUTHORIZED_USER_ID == 1
    assert s.AGENT_TIMEOUT_SECONDS == 60
    assert s.GOOGLE_FACTCHECK_API_KEY is None
    assert s.DB_PATH == "factcheck.db"
