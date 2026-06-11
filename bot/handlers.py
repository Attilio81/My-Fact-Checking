import hashlib
import logging
import re
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import get_settings
from bot.ingest import article, image, instagram, tiktok, youtube
from bot.pipeline import run_check
from db.models import Database

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+")
_YT_RE = re.compile(r"(youtube\.com/watch|youtu\.be/|youtube\.com/shorts)")
_IG_RE = re.compile(r"instagram\.com/(p|reel)/")
_TT_RE = re.compile(r"(vm\.|vt\.|www\.)?tiktok\.com/")

_db: Database | None = None


def _get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(get_settings().DB_PATH)
    return _db


def detect_input_type(text: str) -> str:
    m = _URL_RE.search(text or "")
    if m:
        if _YT_RE.search(m.group()):
            return "youtube"
        if _IG_RE.search(m.group()):
            return "instagram"
        if _TT_RE.search(m.group()):
            return "tiktok"
        return "article"
    return "text"


def _authorized(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == get_settings().AUTHORIZED_USER_ID


_WELCOME = (
    "👋 Ciao! Sono il tuo bot di fact-checking.\n\n"
    "Inviami una notizia da verificare:\n"
    "🔗 link a un articolo\n"
    "📝 testo o claim incollato\n"
    "📸 screenshot di un post social\n"
    "▶️ link a un video YouTube\n"
    "📷 link a un post o reel Instagram\n"
    "🎵 link a un video TikTok\n\n"
    "Estraggo le affermazioni verificabili, cerco evidenze sul web e ti rispondo "
    "con un verdetto per ciascuna: ✅ vero, ❌ falso o ⚠️ non verificabile, con le fonti."
)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update) or update.message is None:
        return
    await update.message.reply_text(_WELCOME)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update) or update.message is None:
        return
    msg = update.message
    text = msg.text or msg.caption or ""

    await msg.chat.send_action("typing")

    if msg.photo:
        input_type, input_ref = "image", None
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            file = await msg.photo[-1].get_file()
            await file.download_to_drive(tmp.name)
            extracted = await image.extract(tmp.name)
    else:
        input_type = detect_input_type(text)
        if input_type == "youtube":
            url = _URL_RE.search(text).group()
            input_ref = url
            extracted = await youtube.extract(url)
        elif input_type == "instagram":
            url = _URL_RE.search(text).group()
            input_ref = url
            extracted = await instagram.extract(url)
        elif input_type == "tiktok":
            url = _URL_RE.search(text).group()
            input_ref = url
            extracted = await tiktok.extract(url)
        elif input_type == "article":
            url = _URL_RE.search(text).group()
            input_ref = url
            extracted = await article.extract(url)
        else:
            input_ref = None
            extracted = (
                {"text": text, "source_url": None, "title": "Testo inoltrato"}
                if text.strip()
                else None
            )

    if extracted is None:
        await msg.reply_text(
            "⚠️ Non sono riuscito a estrarre il contenuto. Riprova o incolla il testo direttamente."
        )
        return

    if input_ref is None:
        input_ref = "text:" + hashlib.sha256(extracted["text"].encode()).hexdigest()[:16]

    cached = _get_db().get_recent_check(input_ref, days=7)
    if cached:
        await msg.reply_text("♻️ Già verificata di recente:\n\n" + cached)
        return

    await msg.reply_text("🔍 Sto verificando, ci vorrà qualche minuto...")
    try:
        report, results = await run_check(
            extracted["text"], title=extracted.get("title") or "notizia"
        )
    except Exception as e:
        logger.error(f"Pipeline fallita: {e}")
        await msg.reply_text("❌ Errore durante la verifica. Riprova più tardi.")
        return

    _get_db().save_check(input_type, input_ref, extracted.get("title"), report, results)
    await msg.reply_text(report, disable_web_page_preview=True)
