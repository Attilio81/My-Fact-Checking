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


def test_cache_miss(tmp_path):
    db = _db(tmp_path)
    assert db.get_recent_check("https://mai.visto/x", days=7) is None
