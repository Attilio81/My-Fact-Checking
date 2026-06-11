from bot.models import ClaimResult
from db.models import Database


def _db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def test_save_and_get_check(tmp_path):
    db = _db(tmp_path)
    results = [
        ClaimResult(
            claim="c1",
            verdict="true",
            confidence="high",
            sources=["https://a.it"],
            reasoning="r",
        )
    ]
    check_id = db.save_check("article", "https://news.example/a", "Titolo", "report", results)
    assert check_id > 0


def test_cache_hit(tmp_path):
    db = _db(tmp_path)
    db.save_check("article", "https://news.example/a", "T", "report-text", [])
    cached = db.get_recent_check("https://news.example/a", days=7)
    assert cached == "report-text"


def test_get_check_and_summary(tmp_path):
    db = _db(tmp_path)
    results = [
        ClaimResult(claim="A", verdict="true", confidence="high", sources=[], reasoning=""),
        ClaimResult(claim="B", verdict="unverifiable", confidence="low", sources=[], reasoning=""),
    ]
    check_id = db.save_check("article", "https://x/a", "Titolo", "report", results)
    check = db.get_check(check_id)
    assert check["source_title"] == "Titolo"
    assert check["created_at"]
    summary = db.list_checks_summary()
    assert summary[0]["true_n"] == 1
    assert summary[0]["unv_n"] == 1
    assert summary[0]["false_n"] == 0


def test_unverifiable_stats(tmp_path):
    db = _db(tmp_path)
    results = [
        ClaimResult(claim="A", verdict="unverifiable", confidence="low",
                    sources=[], reasoning="", unv_reason="nessuna_evidenza"),
        ClaimResult(claim="B", verdict="unverifiable", confidence="low",
                    sources=[], reasoning="", unv_reason="nessuna_evidenza"),
        ClaimResult(claim="C", verdict="unverifiable", confidence="low",
                    sources=[], reasoning="", unv_reason="declassato_quote"),
        ClaimResult(claim="D", verdict="true", confidence="high",
                    sources=["https://x"], reasoning=""),
    ]
    db.save_check("text", "text:x", "T", "report", results)
    stats = db.unverifiable_stats()
    assert stats == {"nessuna_evidenza": 2, "declassato_quote": 1}


def test_cache_miss(tmp_path):
    db = _db(tmp_path)
    assert db.get_recent_check("https://mai.visto/x", days=7) is None
