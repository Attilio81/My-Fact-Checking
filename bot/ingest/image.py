import base64
import logging
from pathlib import Path

import httpx

from bot.config import get_settings

logger = logging.getLogger(__name__)

_PROMPT = (
    "Questo è uno screenshot di un post social o di una notizia. "
    "Estrai TUTTO il testo visibile, parola per parola, in italiano se presente. "
    "Indica anche: autore/account se visibile, piattaforma riconoscibile, data se visibile. "
    "Non aggiungere commenti o interpretazioni: solo il contenuto estratto."
)


async def extract(file_path: str) -> dict | None:
    """Screenshot → testo via gpt-4o-mini vision. None su fallimento."""
    settings = get_settings()
    try:
        b64 = base64.b64encode(Path(file_path).read_bytes()).decode()
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
            "max_tokens": 1024,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY.get_secret_value()}"
                },
            )
            resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return {"text": text, "source_url": None, "title": "Screenshot"} if text else None
    except Exception as e:
        logger.error(f"Estrazione immagine fallita per {file_path}: {e}")
        return None
