import json
import logging
from datetime import date

from agno.agent import Agent
from agno.models.deepseek import DeepSeek

from bot.models import ClaimResult, Evidence, JudgeOutput
from bot.usage import record
from bot.validation import compute_confidence, validate_judge_output

logger = logging.getLogger(__name__)

_PROMPT = """Sei un giudice di fact-checking. Ricevi un CLAIM e una lista di EVIDENZE
recuperate dal web (con URL e testo).

Regole vincolanti:
1. Usa ESCLUSIVAMENTE le evidenze fornite. La tua conoscenza interna NON è ammessa come fonte.
2. verdict "true" solo se le evidenze SUPPORTANO chiaramente il claim.
   verdict "false" solo se le evidenze CONFUTANO chiaramente il claim.
   In ogni altro caso (evidenze insufficienti, non pertinenti, contraddittorie): "unverifiable".
3. In evidence_used cita SOLO URL presenti nelle evidenze fornite, con una quote ESATTA
   copiata letteralmente dal testo dell'evidenza (la quote verrà verificata meccanicamente:
   se non esiste nel testo, il verdetto sarà scartato).
4. PERTINENZA: se le evidenze si riferiscono a un PAESE o PERIODO diverso da quello
   del claim (es. claim sull'inflazione USA, evidenze sull'inflazione italiana),
   NON usarle né per confermare né per confutare: verdict "unverifiable",
   segnalando l'ambiguità nel reasoning.
5. ATTRIBUZIONI: per claim del tipo "X ha detto/dichiarato Y", verifica che X
   abbia davvero detto Y — NON se Y è vero. Senza evidenza della dichiarazione:
   "unverifiable".
6. ATTUALITÀ: per claim al presente su valori che cambiano (prezzi, tassi, cariche),
   confronta la data delle evidenze con la data odierna fornita. Evidenze datate
   (mesi o più) → preferisci "unverifiable" e segnala la data dell'evidenza nel
   reasoning.
7. reasoning: 1-3 frasi in italiano che spiegano il verdetto citando le fonti.
"""

_agent: Agent | None = None


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=DeepSeek(id="deepseek-v4-flash", temperature=0),
            instructions=_PROMPT,
            output_schema=JudgeOutput,
        )
    return _agent


_DOWNGRADE_NOTE = (
    " (verdetto declassato: citazioni non riscontrate letteralmente nelle fonti)"
)


def _unverifiable(claim: str, reasoning: str, reason: str) -> ClaimResult:
    return ClaimResult(
        claim=claim,
        verdict="unverifiable",
        confidence="low",
        sources=[],
        reasoning=reasoning,
        unv_reason=reason,
    )


async def _arun_judge(payload: str) -> JudgeOutput | None:
    try:
        response = await _get_agent().arun(payload)
        record(getattr(response, "metrics", None))
        if isinstance(response.content, JudgeOutput):
            return response.content
        logger.warning(f"Judge output inatteso: {response.content!r}")
    except Exception as e:
        logger.error(f"Judge fallito: {e}")
    return None


async def judge_claim(claim: str, evidences: list[Evidence]) -> ClaimResult:
    """Giudica un claim contro le evidenze. Verdetto sempre validato meccanicamente.
    Se le quote falliscono la validazione, un retry con feedback; se fallisce
    anche quello, declassa e lo dichiara nel reasoning."""
    if not evidences:
        return _unverifiable(claim, "Nessuna evidenza trovata.", "nessuna_evidenza")

    payload = json.dumps(
        {
            "data_odierna": date.today().isoformat(),
            "claim": claim,
            "evidenze": [
                {"url": e.url, "tier": e.tier, "testo": e.content[:3000]} for e in evidences
            ],
        },
        ensure_ascii=False,
    )

    judge_out = await _arun_judge(payload)
    if judge_out is None:
        return _unverifiable(claim, "Errore durante il giudizio.", "errore_giudizio")

    validated = validate_judge_output(judge_out, evidences)

    downgraded = judge_out.verdict in ("true", "false") and not validated.valid_quotes
    if downgraded:
        failed = json.dumps(
            [{"url": q.url, "quote": q.quote} for q in judge_out.evidence_used],
            ensure_ascii=False,
        )
        retry_payload = (
            f"{payload}\n\nATTENZIONE: nel tentativo precedente queste citazioni "
            f"NON esistono letteralmente nei testi delle evidenze: {failed}. "
            "Ricopia le citazioni LETTERALMENTE dal testo dell'evidenza, nella "
            "lingua originale, senza tradurre né parafrasare. Il reasoning invece "
            "resta SEMPRE in italiano."
        )
        retry_out = await _arun_judge(retry_payload)
        if retry_out is not None:
            revalidated = validate_judge_output(retry_out, evidences)
            if revalidated.valid_quotes:
                validated = revalidated
                downgraded = False
    if downgraded:
        validated.reasoning += _DOWNGRADE_NOTE

    unv_reason = ""
    if validated.verdict == "unverifiable":
        unv_reason = "declassato_quote" if downgraded else "evidenze_insufficienti"

    confidence = compute_confidence(validated.verdict, validated.valid_evidences)
    return ClaimResult(
        claim=claim,
        verdict=validated.verdict,
        confidence=confidence,
        sources=[q.url for q in validated.valid_quotes],
        reasoning=validated.reasoning,
        unv_reason=unv_reason,
    )
