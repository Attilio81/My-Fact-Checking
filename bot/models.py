from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["true", "false", "unverifiable"]
Confidence = Literal["high", "medium", "low"]


class ExtractedClaims(BaseModel):
    """Output dell'extractor: claim atomici check-worthy."""

    claims: list[str] = Field(default_factory=list, max_length=5)


class SearchQueries(BaseModel):
    """Output del query generator: query mirate per cercare evidenze su un claim."""

    queries: list[str] = Field(default_factory=list, max_length=3)
    is_current: bool = False  # claim su eventi/valori correnti → ricerca news recenti


class Evidence(BaseModel):
    """Una evidenza recuperata dal researcher."""

    url: str
    title: str = ""
    content: str = ""
    tier: int = 3  # 0=factchecker, 1=primaria, 2=stampa, 3=resto


class EvidenceQuote(BaseModel):
    url: str
    quote: str


class JudgeOutput(BaseModel):
    """Output strutturato del judge (schema forzato)."""

    verdict: Verdict
    evidence_used: list[EvidenceQuote] = Field(default_factory=list)
    reasoning: str = ""


UnvReason = Literal[
    "",  # verdetto non unverifiable
    "nessuna_evidenza",  # il researcher non ha trovato nulla di pertinente
    "evidenze_insufficienti",  # evidenze trovate ma il judge non ha potuto decidere
    "declassato_quote",  # verdetto true/false perso: citazioni non validate
    "errore_giudizio",  # errore tecnico (API, output non valido)
]


class ClaimResult(BaseModel):
    """Risultato finale per claim, dopo validazione meccanica."""

    claim: str
    verdict: Verdict
    confidence: Confidence
    sources: list[str] = Field(default_factory=list)
    reasoning: str = ""
    unv_reason: UnvReason = ""  # telemetria: perché un claim è uscito unverifiable
