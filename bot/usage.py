"""Conteggio token LLM per singola verifica.

ContextVar: il conteggio segue il task asyncio della verifica corrente,
niente stato condiviso tra verifiche concorrenti.
"""

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


_usage: ContextVar[TokenUsage | None] = ContextVar("token_usage", default=None)


def start_tracking() -> TokenUsage:
    """Azzera e attiva il conteggio per la verifica corrente."""
    usage = TokenUsage()
    _usage.set(usage)
    return usage


def record(metrics) -> None:
    """Accumula i token di una risposta agno (RunOutput.metrics). No-op se
    il tracking non è attivo o le metriche mancano."""
    usage = _usage.get()
    if usage is None or metrics is None:
        return
    usage.input_tokens += getattr(metrics, "input_tokens", 0) or 0
    usage.output_tokens += getattr(metrics, "output_tokens", 0) or 0
    usage.calls += 1
