import logging
import tempfile
from pathlib import Path

import httpx
import yt_dlp

logger = logging.getLogger(__name__)


def transcribe_audio(video_url: str, api_key: str) -> str:
    """Scarica lo stream audio di un video (IG reel, TikTok, ...) e trascrive con Whisper.

    yt-dlp prende il bestaudio (m4a, di solito <5 MB), entro il limite 25 MB
    di Whisper senza bisogno di ffmpeg. Stringa vuota su qualsiasi errore.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "format": "bestaudio[vcodec=none]/bestaudio",
                "outtmpl": str(Path(tmpdir) / "clip.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                ext = info.get("ext", "m4a")

            downloaded = next(Path(tmpdir).glob(f"clip.{ext}"), None)
            if downloaded is None:
                logger.warning(f"yt-dlp produced no output file for {video_url}")
                return ""

            with httpx.Client(timeout=120) as client:
                with downloaded.open("rb") as audio_file:
                    resp = client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        data={"model": "whisper-1"},
                        files={"file": (f"clip.{ext}", audio_file, f"audio/{ext}")},
                    )
                resp.raise_for_status()
                return resp.json().get("text", "").strip()

    except Exception as e:
        logger.warning(f"Whisper transcription failed for {video_url}: {e}")
        return ""
