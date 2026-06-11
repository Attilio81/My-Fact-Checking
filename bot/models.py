from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["true", "false", "unverifiable"]
Confidence = Literal["high", "medium", "low"]


class ExtractedClaims(BaseModel):
    """Output dell'extractor: claim atomici check-worthy."""

    claims: list[str] = Field(default_factory=list, max_length=5)


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


class ClaimResult(BaseModel):
    """Risultato finale per claim, dopo validazione meccanica."""

    claim: str
    verdict: Verdict
    confidence: Confidence
    sources: list[str] = Field(default_factory=list)
    reasoning: str = ""
