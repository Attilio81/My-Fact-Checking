import asyncio
import logging

import yt_dlp

from bot.config import get_settings
from bot.ingest.media import transcribe_audio

logger = logging.getLogger(__name__)

_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
}


def _extract_sync(url: str) -> dict | None:
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        logger.warning(f"yt-dlp failed for TikTok {url}: {e}")
        return None

    title = info.get("title", "")
    description = (info.get("description") or "")[:1000]
    uploader = info.get("uploader") or info.get("channel", "")

    api_key = get_settings().OPENAI_API_KEY.get_secret_value()
    transcript = transcribe_audio(url, api_key)

    parts = []
    if uploader:
        parts.append(f"Autore: @{uploader}")
    if description:
        parts.append(f"Caption: {description}")
    if transcript:
        parts.append(f"Transcript:\n{transcript}")

    if not parts:
        logger.warning(f"No content extracted from TikTok {url}")
        return None

    return {
        "text": "\n\n".join(parts),
        "source_url": url,
        "title": title or f"Video TikTok di @{uploader}" if uploader else "Video TikTok",
    }


async def extract(url: str) -> dict | None:
    """Estrae caption e transcript audio da un video TikTok.

    Ritorna dict con chiavi: text, source_url, title. None su fallimento.
    """
    try:
        return await asyncio.to_thread(_extract_sync, url)
    except Exception as e:
        logger.error(f"TikTok extraction failed for {url}: {e}")
        return None
