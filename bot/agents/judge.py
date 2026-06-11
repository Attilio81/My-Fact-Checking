import json
import logging

from agno.agent import Agent
from agno.models.deepseek import DeepSeek

from bot.models import ClaimResult, Evidence, JudgeOutput
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
4. reasoning: 1-3 frasi in italiano che spiegano il verdetto citando le fonti.
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


def _unverifiable(claim: str, reasoning: str) -> ClaimResult:
    return ClaimResult(
        claim=claim, verdict="unverifiable", confidence="low", sources=[], reasoning=reasoning
    )


async def judge_claim(claim: str, evidences: list[Evidence]) -> ClaimResult:
    """Giudica un claim contro le evidenze. Verdetto sempre validato meccanicamente."""
    if not evidences:
        return _unverifiable(claim, "Nessuna evidenza trovata.")

    payload = json.dumps(
        {
            "claim": claim,
            "evidenze": [
                {"url": e.url, "tier": e.tier, "testo": e.content[:3000]} for e in evidences
            ],
        },
        ensure_ascii=False,
    )

    try:
        response = await _get_agent().arun(payload)
        if not isinstance(response.content, JudgeOutput):
            return _unverifiable(claim, "Output del giudice non valido.")
    except Exception as e:
        logger.error(f"Judge fallito per '{claim}': {e}")
        return _unverifiable(claim, "Errore durante il giudizio.")

    validated = validate_judge_output(response.content, evidences)
    confidence = compute_confidence(validated.verdict, validated.valid_evidences)
    return ClaimResult(
        claim=claim,
        verdict=validated.verdict,
        confidence=confidence,
        sources=[q.url for q in validated.valid_quotes],
        reasoning=validated.reasoning,
    )
