from bot.sources import SourceRegistry


def test_tier_lookup():
    reg = SourceRegistry.load("sources.yaml")
    assert reg.tier_of("https://www.istat.it/comunicato/x") == 1
    assert reg.tier_of("https://open.online/2026/fact/x") == 0
    assert reg.tier_of("https://blogsconosciuto.example/x") == 3


def test_blacklist():
    reg = SourceRegistry.load("sources.yaml")
    reg.blacklist.append("fakesite.example")
    assert reg.is_blacklisted("https://fakesite.example/news") is True


def test_search_domains():
    reg = SourceRegistry.load("sources.yaml")
    assert "istat.it" in reg.trusted_domains()
