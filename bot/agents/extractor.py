import logging
from datetime import date

from agno.agent import Agent
from agno.models.deepseek import DeepSeek

from bot.models import ExtractedClaims

logger = logging.getLogger(__name__)

_PROMPT = """Sei un estrattore di claim per fact-checking. Ricevi il testo di una notizia.

Estrai le affermazioni fattuali verificabili (claim), seguendo queste regole:
- Massimo 5 claim, i più rilevanti e centrali della notizia.
- Ogni claim deve essere ATOMICO: una sola affermazione verificabile, autocontenuta
  (risolvi i pronomi: "lui" → il nome; aggiungi data/luogo se presenti nel testo).
- Solo claim CHECK-WORTHY: fatti oggettivi verificabili con fonti (numeri, eventi,
  dichiarazioni attribuite, dati). Escludi opinioni, previsioni, giudizi di valore.
- PRESERVA IL CONTESTO geografico e temporale: se dal testo si deduce il paese
  (es. autore/tema USA, Fed, Trump, dollari), esplicitalo nel claim
  ("Negli Stati Uniti i prezzi sono saliti del 4,2%..."), mai lasciarlo ambiguo.
  Stessa cosa per il periodo, se presente o deducibile dalla data odierna fornita.
- Scrivi i claim in italiano.
- Se l'input è una DOMANDA (es. "le scie chimiche fanno male?"), trasformala
  nell'affermazione implicita da verificare (es. "Le scie chimiche fanno male alla salute").
- Se l'input è un testo breve con una sola affermazione, quel testo È il claim:
  riportalo ripulito, non scartarlo.
- Restituisci lista vuota SOLO se il testo non contiene nulla di fattualmente
  verificabile (es. puri saluti, opinioni personali, emozioni)."""

_agent: Agent | None = None


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=DeepSeek(id="deepseek-v4-flash", temperature=0),
            instructions=_PROMPT,
            output_schema=ExtractedClaims,
        )
    return _agent


async def extract_claims(text: str) -> list[str]:
    """Estrae claim atomici check-worthy dal testo. Lista vuota su errore."""
    try:
        payload = f"Data odierna: {date.today().isoformat()}\n\n{text[:8000]}"
        response = await _get_agent().arun(payload)
        if isinstance(response.content, ExtractedClaims):
            return response.content.claims[:5]
        logger.warning(f"Extractor output inatteso: {response.content!r}")
        return []
    except Exception as e:
        logger.error(f"Estrazione claim fallita: {e}")
        return []
