from bot.models import ClaimResult

_ICON = {"true": "✅ VERO", "false": "❌ FALSO", "unverifiable": "⚠️ NON VERIFICABILE"}
_CONF = {"high": "alta", "medium": "media", "low": "bassa"}


def _overall(results: list[ClaimResult]) -> str:
    if not results:
        return "Nessun claim verificabile trovato."
    false_n = sum(1 for r in results if r.verdict == "false")
    true_n = sum(1 for r in results if r.verdict == "true")
    unv_n = len(results) - false_n - true_n
    if false_n > len(results) / 2:
        return "La notizia appare NON ATTENDIBILE: la maggior parte dei claim è falsa."
    if true_n == len(results):
        return "La notizia appare attendibile: tutti i claim verificati risultano veri."
    if unv_n == len(results):
        return "Non è stato possibile verificare i claim: nessuna evidenza sufficiente."
    return (
        f"Quadro misto: {true_n} claim veri, {false_n} falsi, "
        f"{unv_n} non verificabili. Valutare con attenzione."
    )


def format_report(title: str, results: list[ClaimResult]) -> str:
    lines = [f"📰 Verifica: {title}", ""]
    for i, r in enumerate(results, 1):
        line = f'{i}. "{r.claim}" → {_ICON[r.verdict]}'
        if r.verdict != "unverifiable":
            line += f" (confidenza {_CONF[r.confidence]})"
        lines.append(line)
        if r.reasoning:
            lines.append(f"   {r.reasoning}")
        for url in r.sources:
            lines.append(f"   🔗 {url}")
        lines.append("")
    lines.append(f"Giudizio complessivo: {_overall(results)}")
    return "\n".join(lines)
