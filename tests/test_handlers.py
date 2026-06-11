from bot.handlers import detect_input_type


def test_detect_youtube():
    assert detect_input_type("https://www.youtube.com/watch?v=abc") == "youtube"
    assert detect_input_type("https://youtu.be/abc") == "youtube"


def test_detect_instagram():
    assert detect_input_type("https://www.instagram.com/reel/DJoYWFuNN6k/?igsh=x") == "instagram"
    assert detect_input_type("https://instagram.com/p/Abc123/") == "instagram"


def test_detect_tiktok():
    assert detect_input_type("https://www.tiktok.com/@user/video/123456") == "tiktok"
    assert detect_input_type("https://vm.tiktok.com/ZMabcdef/") == "tiktok"


def test_detect_article():
    assert detect_input_type("guarda https://news.example/articolo") == "article"


def test_detect_text():
    assert detect_input_type("il governo ha stanziato 3 miliardi") == "text"
