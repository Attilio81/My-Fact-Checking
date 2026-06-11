from bot.models import ClaimResult
from bot.wiki import page_path, publish, rebuild_index, write_page

RESULTS = [
    ClaimResult(
        claim="La Procura di Roma indaga sul Ponte",
        verdict="true",
        confidence="high",
        sources=["https://www.ansa.it/x"],
        reasoning="Confermato da ANSA.",
    ),
    ClaimResult(
        claim="Claim ignoto", verdict="unverifiable", confidence="low", sources=[], reasoning=""
    ),
]


def test_page_path_deterministic():
    p = page_path("wiki", 7, "2026-06-11 15:42:00", "Post Instagram di @utente!")
    assert p.as_posix() == "wiki/2026/2026-06-11-7-post-instagram-di-utente.md"


def test_write_page_content(tmp_path):
    path = write_page(
        str(tmp_path), 1, "2026-06-11 15:42:00", "Titolo verifica",
        "article", "https://news.example/a", RESULTS,
    )
    text = path.read_text(encoding="utf-8")
    assert "# Titolo verifica" in text
    assert "✅ VERO (confidenza alta)" in text
    assert "> La Procura di Roma indaga sul Ponte" in text
    assert "https://www.ansa.it/x" in text
    assert "⚠️ NON VERIFICABILE" in text


def test_rebuild_index(tmp_path):
    summaries = [
        {
            "id": 2, "created_at": "2026-06-11 16:00:00", "input_type": "instagram",
            "input_ref": "https://ig/x", "source_title": "Post B",
            "true_n": 4, "false_n": 0, "unv_n": 1,
        },
        {
            "id": 1, "created_at": "2026-06-10 10:00:00", "input_type": "text",
            "input_ref": "text:abc", "source_title": "Claim A",
            "true_n": 0, "false_n": 1, "unv_n": 0,
        },
    ]
    rebuild_index(str(tmp_path), summaries)
    text = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    assert "✅4 ❌0 ⚠️1" in text
    assert "[Post B](2026/2026-06-11-2-post-b.md)" in text
    assert text.index("Post B") < text.index("Claim A")  # più recente in alto


def test_publish_never_raises(tmp_path):
    # wiki_dir non scrivibile (file al posto di directory) → None, nessuna eccezione
    blocker = tmp_path / "blocked"
    blocker.write_text("x")
    result = publish(
        str(blocker / "sub"), 1, "2026-06-11 15:00:00", "T", "text", "text:x", RESULTS, []
    )
    assert result is None
