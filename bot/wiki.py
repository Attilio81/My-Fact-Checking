"""Wiki markdown delle verifiche: una pagina per check + indice generato dal DB.

Scrittura best-effort: un errore qui non deve mai bloccare la risposta del bot.
"""

import logging
import re
import unicodedata
from pathlib import Path

from bot.models import ClaimResult

logger = logging.getLogger(__name__)

_ICON = {"true": "✅ VERO", "false": "❌ FALSO", "unverifiable": "⚠️ NON VERIFICABILE"}
_CONF = {"high": "alta", "medium": "media", "low": "bassa"}


def _slug(title: str, max_len: int = 50) -> str:
    text = unicodedata.normalize("NFKD", title.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w]+", "-", text).strip("-")
    return text[:max_len].rstrip("-") or "verifica"


def page_path(wiki_dir: str, check_id: int, created_at: str, title: str) -> Path:
    """Percorso deterministico: data + id (univoco) + slug del titolo."""
    date = created_at[:10]
    return Path(wiki_dir) / date[:4] / f"{date}-{check_id}-{_slug(title)}.md"


def write_page(
    wiki_dir: str,
    check_id: int,
    created_at: str,
    title: str,
    input_type: str,
    input_ref: str,
    results: list[ClaimResult],
) -> Path:
    path = page_path(wiki_dir, check_id, created_at, title)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# {title}",
        "",
        f"- **Data**: {created_at}",
        f"- **Tipo**: {input_type}",
    ]
    if input_ref and input_ref.startswith("http"):
        lines.append(f"- **Fonte verificata**: <{input_ref}>")
    lines += ["", "## Claim verificati", ""]

    for i, r in enumerate(results, 1):
        header = f"### {i}. {_ICON[r.verdict]}"
        if r.verdict != "unverifiable":
            header += f" (confidenza {_CONF[r.confidence]})"
        lines += [header, "", f"> {r.claim}", ""]
        if r.reasoning:
            lines += [r.reasoning, ""]
        if r.sources:
            lines.append("Fonti:")
            lines += [f"- <{url}>" for url in r.sources]
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def rebuild_index(wiki_dir: str, summaries: list[dict]) -> None:
    """Rigenera INDEX.md dall'archivio (più recente in alto).

    summaries: [{id, created_at, input_type, input_ref, source_title,
                 true_n, false_n, unv_n}]
    """
    lines = [
        "# Wiki delle verifiche",
        "",
        "Archivio consultabile di tutti i fact-check del bot. "
        "Una pagina per verifica, generata automaticamente.",
        "",
        "| Data | Verifica | Esito | Tipo |",
        "|---|---|---|---|",
    ]
    for s in summaries:
        title = s.get("source_title") or "(senza titolo)"
        rel = page_path(".", s["id"], s["created_at"], title)
        rel_str = str(rel).replace("\\", "/").lstrip("./")
        esito = f"✅{s['true_n']} ❌{s['false_n']} ⚠️{s['unv_n']}"
        lines.append(
            f"| {s['created_at'][:10]} | [{title}]({rel_str}) | {esito} | {s['input_type']} |"
        )
    lines.append("")
    Path(wiki_dir, "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def publish(
    wiki_dir: str,
    check_id: int,
    created_at: str,
    title: str,
    input_type: str,
    input_ref: str,
    results: list[ClaimResult],
    summaries: list[dict],
) -> Path | None:
    """Pagina + indice. Best-effort: logga e ritorna None su errore."""
    try:
        path = write_page(
            wiki_dir, check_id, created_at, title, input_type, input_ref, results
        )
        rebuild_index(wiki_dir, summaries)
        return path
    except Exception as e:
        logger.error(f"Scrittura wiki fallita per check {check_id}: {e}")
        return None
