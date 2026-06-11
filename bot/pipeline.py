import logging

from bot.agents.extractor import extract_claims
from bot.agents.judge import judge_claim
from bot.agents.researcher import fetch_context_documents, gather_evidence
from bot.models import ClaimResult, Evidence
from bot.report import format_report
from bot.sources import SourceRegistry
from bot.usage import start_tracking

logger = logging.getLogger(__name__)

_registry: SourceRegistry | None = None


def _get_registry() -> SourceRegistry:
    global _registry
    if _registry is None:
        _registry = SourceRegistry.load("sources.yaml")
    return _registry


async def run_check(text: str, title: str = "notizia") -> tuple[str, list[ClaimResult]]:
    """Pipeline completa: testo → claim → evidenze → verdetti → report."""
    usage = start_tracking()

    claims = await extract_claims(text)
    if not claims:
        return ("Nessun claim verificabile trovato nel contenuto.", [])

    registry = _get_registry()
    # documenti primari citati nel contenuto (paper, dati ufficiali) +
    # evidenze raccolte per i claim precedenti: condivisi tra tutti i claim
    pool: list[Evidence] = await fetch_context_documents(text, registry)

    results: list[ClaimResult] = []
    for claim in claims:
        evidences = await gather_evidence(claim, registry, pool=pool)
        results.append(await judge_claim(claim, evidences))

    report = format_report(title, results)
    if usage.calls:
        report += (
            f"\n\n🔢 {usage.total:,} token LLM in {usage.calls} chiamate "
            f"(in: {usage.input_tokens:,} / out: {usage.output_tokens:,})"
        ).replace(",", ".")
    return report, results
