# FactChecking Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bot Telegram che verifica notizie (link/testo/foto/YouTube) con pipeline claim→evidenze→verdetto anti-allucinazione.

**Architecture:** Pipeline lineare orchestrata in Python: ingest → extractor (agno+DeepSeek) → researcher (Tavily a tier + Firecrawl) → judge (agno+DeepSeek, JSON vincolato) → validazione meccanica → report Telegram. Storage SQLite locale con cache per URL.

**Tech Stack:** python-telegram-bot, agno (DeepSeek `deepseek-v4-flash`), tavily-python, firecrawl-py (`firecrawl.v1.V1FirecrawlApp`), httpx, yt-dlp + youtube-transcript-api, sqlite3 stdlib, PyYAML, pytest + pytest-asyncio.

Riferimento spec: `docs/superpowers/specs/2026-06-11-factchecking-bot-design.md`.
Pattern API copiati da BrainDrop (`C:\Users\attilio.pregnolato.EGMSISTEMI\Documents\GitHub\BrainDrop`): `Agent(model=DeepSeek(id=...), output_schema=Model)` + `await agent.arun(text)` → `response.content`; Firecrawl `V1FirecrawlApp(...).scrape_url(url, formats=["markdown"]).markdown`.

## File Structure

```
bot/
  __init__.py
  main.py            # entrypoint polling
  config.py          # pydantic-settings
  handlers.py        # Telegram: smistamento input, invio report
  report.py          # formattazione report Telegram
  pipeline.py        # orchestrazione check completo
  models.py          # modelli Pydantic di dominio (Claim, Evidence, JudgeOutput, ClaimResult)
  validation.py      # validazione meccanica verdetti + confidenza calcolata
  sources.py         # caricamento sources.yaml, lookup tier
  agents/
    __init__.py
    extractor.py     # testo → claim atomici
    researcher.py    # claim → evidenze (FactCheck API → Tavily tier → Tavily aperto, Firecrawl)
    judge.py         # claim+evidenze → JudgeOutput
  ingest/
    __init__.py
    article.py       # URL → Firecrawl → testo
    youtube.py       # riuso BrainDrop
    image.py         # vision OCR (riuso pattern photo.py)
db/
  __init__.py
  models.py          # SQLite: checks, claims, cache
tests/               # mirror della struttura
sources.yaml
requirements.txt  .env.example  .gitignore  pytest.ini  README.md
```

---

### Task 1: Scaffold progetto

**Files:**
- Create: `requirements.txt`, `.env.example`, `.gitignore`, `pytest.ini`, `README.md`, `bot/__init__.py`, `bot/agents/__init__.py`, `bot/ingest/__init__.py`, `db/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: requirements.txt**

```
python-telegram-bot>=21.0
agno
pydantic-settings>=2.0.0
python-dotenv
tavily-python
firecrawl-py
httpx
PyYAML
yt-dlp>=2024.1.0
youtube-transcript-api>=0.6.0
pytest
pytest-asyncio>=0.21
```

- [ ] **Step 2: .env.example**

```
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
AUTHORIZED_USER_ID=123456789
DEEPSEEK_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
FIRECRAWL_API_KEY=fc-...
OPENAI_API_KEY=sk-...           # solo vision OCR screenshot
GOOGLE_FACTCHECK_API_KEY=       # opzionale, tier 0
AGENT_TIMEOUT_SECONDS=60
DB_PATH=factcheck.db
```

- [ ] **Step 3: .gitignore** (python standard: `__pycache__/`, `.env`, `*.db`, `.pytest_cache/`, `venv/`, `.venv/`)

- [ ] **Step 4: pytest.ini**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 5: README.md** — descrizione progetto, architettura (diagramma pipeline), setup (venv, pip install, .env), uso, riferimenti spec. Scritto in italiano.

- [ ] **Step 6: `__init__.py` vuoti + commit**

```bash
git add -A && git commit -m "chore: scaffold progetto"
```

---

### Task 2: config.py

**Files:**
- Create: `bot/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: test fallente**

```python
import pytest
from pydantic import ValidationError

def test_settings_from_env(monkeypatch):
    for k, v in {
        "TELEGRAM_BOT_TOKEN": "t", "AUTHORIZED_USER_ID": "1",
        "DEEPSEEK_API_KEY": "d", "TAVILY_API_KEY": "tv",
        "FIRECRAWL_API_KEY": "f", "OPENAI_API_KEY": "o",
    }.items():
        monkeypatch.setenv(k, v)
    from bot.config import Settings
    s = Settings(_env_file=None)
    assert s.AUTHORIZED_USER_ID == 1
    assert s.AGENT_TIMEOUT_SECONDS == 60
    assert s.GOOGLE_FACTCHECK_API_KEY is None
    assert s.DB_PATH == "factcheck.db"
```

- [ ] **Step 2: run, FAIL (ModuleNotFoundError)**
- [ ] **Step 3: implementazione** — come BrainDrop `config.py` con campi della spec:

```python
from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    TELEGRAM_BOT_TOKEN: SecretStr
    AUTHORIZED_USER_ID: int

    DEEPSEEK_API_KEY: SecretStr
    TAVILY_API_KEY: SecretStr
    FIRECRAWL_API_KEY: SecretStr
    OPENAI_API_KEY: SecretStr
    GOOGLE_FACTCHECK_API_KEY: SecretStr | None = None

    AGENT_TIMEOUT_SECONDS: int = Field(default=60, gt=0)
    DB_PATH: str = "factcheck.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: run, PASS**
- [ ] **Step 5: commit** `feat: config con pydantic-settings`

---

### Task 3: modelli di dominio

**Files:**
- Create: `bot/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: test fallente**

```python
from bot.models import ExtractedClaims, Evidence, EvidenceQuote, JudgeOutput, ClaimResult

def test_judge_output_verdict_enum():
    j = JudgeOutput(verdict="true", evidence_used=[EvidenceQuote(url="https://a.it", quote="x")], reasoning="r")
    assert j.verdict == "true"

def test_claim_result_defaults():
    r = ClaimResult(claim="c", verdict="unverifiable", confidence="low", sources=[], reasoning="")
    assert r.sources == []
```

- [ ] **Step 2: run, FAIL**
- [ ] **Step 3: implementazione**

```python
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
```

- [ ] **Step 4: run, PASS**
- [ ] **Step 5: commit** `feat: modelli di dominio`

---

### Task 4: sources.py + sources.yaml

**Files:**
- Create: `sources.yaml`, `bot/sources.py`
- Test: `tests/test_sources.py`

- [ ] **Step 1: test fallente**

```python
from bot.sources import SourceRegistry

def test_tier_lookup():
    reg = SourceRegistry.load("sources.yaml")
    assert reg.tier_of("https://www.istat.it/comunicato/x") == 1
    assert reg.tier_of("https://open.online/2026/fact/x") == 0
    assert reg.tier_of("https://blogsconosciuto.example/x") == 3

def test_blacklist():
    reg = SourceRegistry.load("sources.yaml")
    reg.blacklist.append("fakesite.example")
    assert reg.is_blacklisted("https://fakesite.example/news") is True

def test_search_domains():
    reg = SourceRegistry.load("sources.yaml")
    assert "istat.it" in reg.trusted_domains()  # tier 1+2 per include_domains Tavily
```

- [ ] **Step 2: run, FAIL**
- [ ] **Step 3: sources.yaml** (domini dalla spec)

```yaml
tier_0_factcheckers:
  - open.online
  - pagellapolitica.it
  - facta.news
  - snopes.com
  - factcheck.org
tier_1_primarie:
  - istat.it
  - eurostat.ec.europa.eu
  - iss.it
  - bancaditalia.it
  - ansa.it
  - reuters.com
  - apnews.com
  - governo.it
  - europa.eu
tier_2_stampa:
  - corriere.it
  - repubblica.it
  - ilsole24ore.com
  - ilpost.it
  - bbc.com
  - theguardian.com
  - nytimes.com
blacklist: []
```

- [ ] **Step 4: bot/sources.py**

```python
from dataclasses import dataclass, field
from urllib.parse import urlparse

import yaml


@dataclass
class SourceRegistry:
    tier0: list[str] = field(default_factory=list)
    tier1: list[str] = field(default_factory=list)
    tier2: list[str] = field(default_factory=list)
    blacklist: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str = "sources.yaml") -> "SourceRegistry":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(
            tier0=data.get("tier_0_factcheckers", []),
            tier1=data.get("tier_1_primarie", []),
            tier2=data.get("tier_2_stampa", []),
            blacklist=data.get("blacklist", []),
        )

    @staticmethod
    def _domain(url: str) -> str:
        return urlparse(url).netloc.lower().removeprefix("www.")

    def _matches(self, url: str, domains: list[str]) -> bool:
        d = self._domain(url)
        return any(d == dom or d.endswith("." + dom) for dom in domains)

    def tier_of(self, url: str) -> int:
        for tier, domains in enumerate([self.tier0, self.tier1, self.tier2]):
            if self._matches(url, domains):
                return tier
        return 3

    def is_blacklisted(self, url: str) -> bool:
        return self._matches(url, self.blacklist)

    def trusted_domains(self) -> list[str]:
        return self.tier1 + self.tier2
```

- [ ] **Step 5: run, PASS — commit** `feat: registro fonti a tier`

---

### Task 5: validation.py (cuore anti-allucinazione)

**Files:**
- Create: `bot/validation.py`
- Test: `tests/test_validation.py`

- [ ] **Step 1: test fallenti** (logica pura, TDD pieno)

```python
from bot.models import Evidence, EvidenceQuote, JudgeOutput
from bot.validation import validate_judge_output, compute_confidence

EVIDENCES = [
    Evidence(url="https://www.istat.it/x", content="Il PIL è cresciuto del 2% nel 2025.", tier=1),
    Evidence(url="https://ansa.it/y", content="PIL su del 2 per cento secondo Istat.", tier=1),
]

def _judge(verdict="true", quotes=None):
    return JudgeOutput(verdict=verdict, evidence_used=quotes or [], reasoning="r")

def test_url_inventato_declassa():
    j = _judge(quotes=[EvidenceQuote(url="https://inventato.example/z", quote="Il PIL è cresciuto")])
    result = validate_judge_output(j, EVIDENCES)
    assert result.verdict == "unverifiable"

def test_quote_inventata_declassa():
    j = _judge(quotes=[EvidenceQuote(url="https://www.istat.it/x", quote="frase mai scritta")])
    result = validate_judge_output(j, EVIDENCES)
    assert result.verdict == "unverifiable"

def test_quote_valida_normalizzata():
    j = _judge(quotes=[EvidenceQuote(url="https://www.istat.it/x", quote="il pil È cresciuto del 2%")])
    result = validate_judge_output(j, EVIDENCES)
    assert result.verdict == "true"
    assert result.valid_quotes[0].url == "https://www.istat.it/x"

def test_verdetto_senza_evidenze_forzato_unverifiable():
    j = _judge(verdict="false", quotes=[])
    assert validate_judge_output(j, EVIDENCES).verdict == "unverifiable"

def test_confidence_due_tier1_concordi_high():
    valid = [EVIDENCES[0], EVIDENCES[1]]
    assert compute_confidence("true", valid) == "high"

def test_confidence_una_fonte_low():
    assert compute_confidence("true", [EVIDENCES[0]]) == "low"

def test_confidence_unverifiable_sempre_low():
    assert compute_confidence("unverifiable", EVIDENCES) == "low"
```

- [ ] **Step 2: run, FAIL**
- [ ] **Step 3: implementazione**

```python
import re
import unicodedata
from dataclasses import dataclass, field

from bot.models import Confidence, Evidence, EvidenceQuote, JudgeOutput, Verdict


@dataclass
class ValidatedVerdict:
    verdict: Verdict
    valid_quotes: list[EvidenceQuote] = field(default_factory=list)
    valid_evidences: list[Evidence] = field(default_factory=list)
    reasoning: str = ""


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%]", "", text)).strip()


def validate_judge_output(judge: JudgeOutput, evidences: list[Evidence]) -> ValidatedVerdict:
    """Validazione meccanica: URL citati devono esistere tra le evidenze recuperate,
    le quote devono comparire nel testo dell'evidenza. Violazione → unverifiable."""
    by_url = {e.url: e for e in evidences}
    valid_quotes, valid_evidences = [], []
    for q in judge.evidence_used:
        ev = by_url.get(q.url)
        if ev is None:
            continue  # URL inventato
        if _normalize(q.quote) not in _normalize(ev.content):
            continue  # citazione inventata
        valid_quotes.append(q)
        if ev not in valid_evidences:
            valid_evidences.append(ev)

    verdict = judge.verdict
    if verdict in ("true", "false") and not valid_quotes:
        verdict = "unverifiable"
    return ValidatedVerdict(verdict=verdict, valid_quotes=valid_quotes,
                            valid_evidences=valid_evidences, reasoning=judge.reasoning)


def compute_confidence(verdict: Verdict, valid_evidences: list[Evidence]) -> Confidence:
    """Confidenza calcolata in codice, non autodichiarata dal modello."""
    if verdict == "unverifiable":
        return "low"
    domains = {e.url.split("/")[2] for e in valid_evidences if "//" in e.url}
    strong = [e for e in valid_evidences if e.tier <= 1]
    if len(strong) >= 2 and len(domains) >= 2:
        return "high"
    if len(valid_evidences) >= 2 and len(domains) >= 2:
        return "medium"
    return "low"
```

- [ ] **Step 4: run, PASS — commit** `feat: validazione meccanica anti-allucinazione`

---

### Task 6: db/models.py (SQLite + cache)

**Files:**
- Create: `db/models.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: test fallenti**

```python
from bot.models import ClaimResult
from db.models import Database

def _db(tmp_path):
    return Database(str(tmp_path / "test.db"))

def test_save_and_get_check(tmp_path):
    db = _db(tmp_path)
    results = [ClaimResult(claim="c1", verdict="true", confidence="high",
                           sources=["https://a.it"], reasoning="r")]
    check_id = db.save_check("article", "https://news.example/a", "Titolo", "report", results)
    assert check_id > 0

def test_cache_hit(tmp_path):
    db = _db(tmp_path)
    db.save_check("article", "https://news.example/a", "T", "report-text", [])
    cached = db.get_recent_check("https://news.example/a", days=7)
    assert cached == "report-text"

def test_cache_miss(tmp_path):
    db = _db(tmp_path)
    assert db.get_recent_check("https://mai.visto/x", days=7) is None
```

- [ ] **Step 2: run, FAIL**
- [ ] **Step 3: implementazione** (sqlite3 stdlib, schema dalla spec)

```python
import json
import sqlite3

from bot.models import ClaimResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    input_type TEXT NOT NULL,
    input_ref TEXT NOT NULL,
    source_title TEXT,
    report_text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checks_ref ON checks(input_ref, created_at);
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id INTEGER NOT NULL REFERENCES checks(id),
    claim_text TEXT NOT NULL,
    verdict TEXT NOT NULL,
    confidence TEXT NOT NULL,
    sources TEXT NOT NULL DEFAULT '[]'
);
"""


class Database:
    def __init__(self, path: str):
        self._path = path
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def save_check(self, input_type: str, input_ref: str, source_title: str | None,
                   report_text: str, results: list[ClaimResult]) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO checks (input_type, input_ref, source_title, report_text) VALUES (?,?,?,?)",
                (input_type, input_ref, source_title, report_text),
            )
            check_id = cur.lastrowid
            c.executemany(
                "INSERT INTO claims (check_id, claim_text, verdict, confidence, sources) VALUES (?,?,?,?,?)",
                [(check_id, r.claim, r.verdict, r.confidence, json.dumps(r.sources)) for r in results],
            )
        return check_id

    def get_recent_check(self, input_ref: str, days: int = 7) -> str | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT report_text FROM checks WHERE input_ref = ? "
                "AND created_at >= datetime('now', ?) ORDER BY created_at DESC LIMIT 1",
                (input_ref, f"-{days} days"),
            ).fetchone()
        return row[0] if row else None
```

- [ ] **Step 4: run, PASS — commit** `feat: storage SQLite con cache`

---

### Task 7: agents/extractor.py

**Files:**
- Create: `bot/agents/extractor.py`
- Test: `tests/test_extractor.py`

- [ ] **Step 1: test fallente** (agente mockato, pattern BrainDrop)

```python
from unittest.mock import AsyncMock, patch
from bot.models import ExtractedClaims

async def test_extract_claims_returns_list():
    fake = ExtractedClaims(claims=["Il PIL è cresciuto del 2% nel 2025"])
    with patch("bot.agents.extractor._get_agent") as ga:
        ga.return_value.arun = AsyncMock(return_value=type("R", (), {"content": fake})())
        from bot.agents.extractor import extract_claims
        claims = await extract_claims("testo articolo lungo...")
    assert claims == ["Il PIL è cresciuto del 2% nel 2025"]

async def test_extract_claims_failure_returns_empty():
    with patch("bot.agents.extractor._get_agent") as ga:
        ga.return_value.arun = AsyncMock(side_effect=RuntimeError("api down"))
        from bot.agents.extractor import extract_claims
        assert await extract_claims("testo") == []
```

- [ ] **Step 2: run, FAIL**
- [ ] **Step 3: implementazione**

```python
import logging

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
- Scrivi i claim in italiano.
- Se il testo non contiene claim verificabili, restituisci lista vuota."""

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
        response = await _get_agent().arun(text[:8000])
        if isinstance(response.content, ExtractedClaims):
            return response.content.claims[:5]
        logger.warning(f"Extractor output inatteso: {response.content!r}")
        return []
    except Exception as e:
        logger.error(f"Estrazione claim fallita: {e}")
        return []
```

- [ ] **Step 4: run, PASS — commit** `feat: agente extractor claim`

---

### Task 8: agents/researcher.py

**Files:**
- Create: `bot/agents/researcher.py`
- Test: `tests/test_researcher.py`

- [ ] **Step 1: test fallenti** (Tavily/FactCheck/Firecrawl mockati)

```python
from unittest.mock import AsyncMock, MagicMock, patch
from bot.sources import SourceRegistry

REG = SourceRegistry(tier0=["snopes.com"], tier1=["istat.it"], tier2=["corriere.it"], blacklist=["fake.example"])

def _tavily_result(url, content="testo evidenza"):
    return {"url": url, "title": "T", "content": content}

async def test_search_assigns_tiers():
    with patch("bot.agents.researcher._tavily_search") as ts, \
         patch("bot.agents.researcher._factcheck_search", AsyncMock(return_value=[])), \
         patch("bot.agents.researcher._scrape", AsyncMock(return_value="")):
        ts.side_effect = AsyncMock(side_effect=[
            [_tavily_result("https://www.istat.it/a")], []])
        from bot.agents.researcher import gather_evidence
        evs = await gather_evidence("claim", REG)
    assert evs[0].tier == 1

async def test_blacklist_filtered():
    with patch("bot.agents.researcher._tavily_search") as ts, \
         patch("bot.agents.researcher._factcheck_search", AsyncMock(return_value=[])), \
         patch("bot.agents.researcher._scrape", AsyncMock(return_value="")):
        ts.side_effect = AsyncMock(side_effect=[
            [_tavily_result("https://fake.example/x")], []])
        from bot.agents.researcher import gather_evidence
        evs = await gather_evidence("claim", REG)
    assert evs == []
```

- [ ] **Step 2: run, FAIL**
- [ ] **Step 3: implementazione**

```python
import asyncio
import logging

import httpx
from tavily import TavilyClient

from bot.config import get_settings
from bot.models import Evidence
from bot.sources import SourceRegistry

logger = logging.getLogger(__name__)

_MAX_RESULTS = 5
_SCRAPE_TOP_N = 2  # Firecrawl solo sulle prime N evidenze (costo)
_FACTCHECK_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

_tavily: TavilyClient | None = None


def _get_tavily() -> TavilyClient:
    global _tavily
    if _tavily is None:
        _tavily = TavilyClient(api_key=get_settings().TAVILY_API_KEY.get_secret_value())
    return _tavily


async def _tavily_search(query: str, include_domains: list[str] | None) -> list[dict]:
    def _sync() -> list[dict]:
        kwargs = {"max_results": _MAX_RESULTS, "search_depth": "advanced"}
        if include_domains:
            kwargs["include_domains"] = include_domains
        return _get_tavily().search(query, **kwargs).get("results", [])
    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning(f"Tavily fallita per '{query}': {e}")
        return []


async def _factcheck_search(claim: str) -> list[Evidence]:
    """Tier 0: Google Fact Check Tools API (ClaimReview). Skip se key assente."""
    key = get_settings().GOOGLE_FACTCHECK_API_KEY
    if key is None:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_FACTCHECK_URL, params={
                "query": claim, "languageCode": "it", "key": key.get_secret_value()})
            resp.raise_for_status()
        evidences = []
        for c in resp.json().get("claims", [])[:3]:
            for review in c.get("claimReview", [])[:1]:
                evidences.append(Evidence(
                    url=review.get("url", ""),
                    title=review.get("title", ""),
                    content=f"Claim verificato: {c.get('text', '')}. "
                            f"Verdetto editoriale: {review.get('textualRating', '')} "
                            f"({review.get('publisher', {}).get('name', '')})",
                    tier=0,
                ))
        return evidences
    except Exception as e:
        logger.warning(f"FactCheck API fallita: {e}")
        return []


async def _scrape(url: str) -> str:
    """Firecrawl, contenuto completo. Stringa vuota su errore (fallback snippet Tavily)."""
    def _sync() -> str:
        from firecrawl.v1 import V1FirecrawlApp
        app = V1FirecrawlApp(api_key=get_settings().FIRECRAWL_API_KEY.get_secret_value())
        result = app.scrape_url(url, formats=["markdown"])
        return (result.markdown or "")[:6000]
    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning(f"Firecrawl fallito per {url}: {e}")
        return ""


async def gather_evidence(claim: str, registry: SourceRegistry) -> list[Evidence]:
    """Ordine spec: FactCheck API (tier 0) → Tavily domini fidati → Tavily aperto.
    Blacklist sempre esclusa. Firecrawl sulle prime evidenze, fallback snippet."""
    evidences = await _factcheck_search(claim)

    results = await _tavily_search(claim, registry.trusted_domains())
    if not results:
        results = await _tavily_search(claim, None)

    for r in results:
        url = r.get("url", "")
        if not url or registry.is_blacklisted(url):
            continue
        evidences.append(Evidence(url=url, title=r.get("title", ""),
                                  content=r.get("content", ""), tier=registry.tier_of(url)))

    for ev in [e for e in evidences if e.tier > 0][:_SCRAPE_TOP_N]:
        full = await _scrape(ev.url)
        if full:
            ev.content = full

    return evidences[:_MAX_RESULTS + 3]
```

- [ ] **Step 4: run, PASS — commit** `feat: researcher con fonti a tier`

---

### Task 9: agents/judge.py

**Files:**
- Create: `bot/agents/judge.py`
- Test: `tests/test_judge.py`

- [ ] **Step 1: test fallenti**

```python
from unittest.mock import AsyncMock, patch
from bot.models import Evidence, EvidenceQuote, JudgeOutput

EVS = [Evidence(url="https://istat.it/a", content="Il PIL è cresciuto del 2%.", tier=1)]

async def test_judge_returns_validated_result():
    fake = JudgeOutput(verdict="true",
                       evidence_used=[EvidenceQuote(url="https://istat.it/a", quote="Il PIL è cresciuto del 2%")],
                       reasoning="confermato")
    with patch("bot.agents.judge._get_agent") as ga:
        ga.return_value.arun = AsyncMock(return_value=type("R", (), {"content": fake})())
        from bot.agents.judge import judge_claim
        result = await judge_claim("Il PIL è cresciuto del 2%", EVS)
    assert result.verdict == "true"
    assert result.confidence in ("high", "medium", "low")
    assert result.sources == ["https://istat.it/a"]

async def test_judge_no_evidence_short_circuit():
    from bot.agents.judge import judge_claim
    result = await judge_claim("claim", [])  # nessuna chiamata LLM
    assert result.verdict == "unverifiable"

async def test_judge_failure_unverifiable():
    with patch("bot.agents.judge._get_agent") as ga:
        ga.return_value.arun = AsyncMock(side_effect=RuntimeError("down"))
        from bot.agents.judge import judge_claim
        result = await judge_claim("claim", EVS)
    assert result.verdict == "unverifiable"
```

- [ ] **Step 2: run, FAIL**
- [ ] **Step 3: implementazione**

```python
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
    return ClaimResult(claim=claim, verdict="unverifiable", confidence="low",
                       sources=[], reasoning=reasoning)


async def judge_claim(claim: str, evidences: list[Evidence]) -> ClaimResult:
    """Giudica un claim contro le evidenze. Verdetto sempre validato meccanicamente."""
    if not evidences:
        return _unverifiable(claim, "Nessuna evidenza trovata.")

    payload = json.dumps({
        "claim": claim,
        "evidenze": [{"url": e.url, "tier": e.tier, "testo": e.content[:3000]} for e in evidences],
    }, ensure_ascii=False)

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
```

- [ ] **Step 4: run, PASS — commit** `feat: judge vincolato alle evidenze`

---

### Task 10: ingest (article, youtube, image)

**Files:**
- Create: `bot/ingest/article.py`, `bot/ingest/youtube.py`, `bot/ingest/image.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: test fallenti**

```python
from unittest.mock import AsyncMock, patch

async def test_article_uses_firecrawl():
    with patch("bot.ingest.article._scrape", AsyncMock(return_value="# Titolo\ncorpo")):
        from bot.ingest.article import extract
        result = await extract("https://news.example/a")
    assert result is not None and "corpo" in result["text"]

async def test_article_failure_returns_none():
    with patch("bot.ingest.article._scrape", AsyncMock(return_value="")):
        from bot.ingest.article import extract
        assert await extract("https://news.example/a") is None
```

- [ ] **Step 2: run, FAIL**
- [ ] **Step 3: bot/ingest/article.py**

```python
import asyncio
import logging

logger = logging.getLogger(__name__)


async def _scrape(url: str) -> str:
    def _sync() -> str:
        from firecrawl.v1 import V1FirecrawlApp
        from bot.config import get_settings
        app = V1FirecrawlApp(api_key=get_settings().FIRECRAWL_API_KEY.get_secret_value())
        result = app.scrape_url(url, formats=["markdown"])
        return result.markdown or ""
    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning(f"Scraping articolo fallito per {url}: {e}")
        return ""


async def extract(url: str) -> dict | None:
    """URL articolo → {text, source_url, title}. None su fallimento."""
    text = await _scrape(url)
    if not text.strip():
        return None
    title = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#")), url)
    return {"text": text[:12000], "source_url": url, "title": title}
```

- [ ] **Step 4: bot/ingest/youtube.py** — copia letterale da BrainDrop `bot/agents/youtube.py` (già testato lì): `extract(url) -> dict | None` con yt-dlp + youtube-transcript-api. Aggiungi chiave `"title"` al dict di ritorno (`"title": title`).

- [ ] **Step 5: bot/ingest/image.py** — pattern BrainDrop `photo.py`, prompt OCR per fact-checking:

```python
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
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": _PROMPT},
            ]}],
            "max_tokens": 1024,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY.get_secret_value()}"},
            )
            resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return {"text": text, "source_url": None, "title": "Screenshot"} if text else None
    except Exception as e:
        logger.error(f"Estrazione immagine fallita per {file_path}: {e}")
        return None
```

- [ ] **Step 6: run, PASS — commit** `feat: ingest articolo, youtube, immagine`

---

### Task 11: pipeline.py + report.py

**Files:**
- Create: `bot/pipeline.py`, `bot/report.py`
- Test: `tests/test_pipeline.py`, `tests/test_report.py`

- [ ] **Step 1: test fallenti**

```python
# tests/test_report.py
from bot.models import ClaimResult
from bot.report import format_report

def test_format_report_per_claim():
    results = [
        ClaimResult(claim="A", verdict="true", confidence="high", sources=["https://a.it/x"], reasoning="ok"),
        ClaimResult(claim="B", verdict="false", confidence="medium", sources=["https://b.it/y"], reasoning="no"),
        ClaimResult(claim="C", verdict="unverifiable", confidence="low", sources=[], reasoning=""),
    ]
    report = format_report("Titolo notizia", results)
    assert "✅" in report and "❌" in report and "⚠️" in report
    assert "Titolo notizia" in report
    assert "https://a.it/x" in report

def test_overall_judgment_mostly_false():
    results = [ClaimResult(claim=c, verdict="false", confidence="high", sources=["https://x.it"], reasoning="")
               for c in "AB"]
    assert "non attendibile" in format_report("T", results).lower()
```

```python
# tests/test_pipeline.py
from unittest.mock import AsyncMock, patch
from bot.models import ClaimResult

async def test_pipeline_no_claims():
    with patch("bot.pipeline.extract_claims", AsyncMock(return_value=[])):
        from bot.pipeline import run_check
        report, results = await run_check("testo senza fatti")
    assert results == [] and "Nessun claim" in report

async def test_pipeline_full_flow():
    cr = ClaimResult(claim="A", verdict="true", confidence="high", sources=["https://a.it"], reasoning="")
    with patch("bot.pipeline.extract_claims", AsyncMock(return_value=["A"])), \
         patch("bot.pipeline.gather_evidence", AsyncMock(return_value=["fake-ev"])), \
         patch("bot.pipeline.judge_claim", AsyncMock(return_value=cr)):
        from bot.pipeline import run_check
        report, results = await run_check("testo", title="T")
    assert len(results) == 1 and "✅" in report
```

- [ ] **Step 2: run, FAIL**
- [ ] **Step 3: bot/report.py**

```python
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
    return (f"Quadro misto: {true_n} claim veri, {false_n} falsi, "
            f"{unv_n} non verificabili. Valutare con attenzione.")


def format_report(title: str, results: list[ClaimResult]) -> str:
    lines = [f"📰 Verifica: {title}", ""]
    for i, r in enumerate(results, 1):
        line = f"{i}. \"{r.claim}\" → {_ICON[r.verdict]}"
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
```

- [ ] **Step 4: bot/pipeline.py**

```python
import logging

from bot.agents.extractor import extract_claims
from bot.agents.judge import judge_claim
from bot.agents.researcher import gather_evidence
from bot.models import ClaimResult
from bot.report import format_report
from bot.sources import SourceRegistry

logger = logging.getLogger(__name__)

_registry: SourceRegistry | None = None


def _get_registry() -> SourceRegistry:
    global _registry
    if _registry is None:
        _registry = SourceRegistry.load("sources.yaml")
    return _registry


async def run_check(text: str, title: str = "notizia") -> tuple[str, list[ClaimResult]]:
    """Pipeline completa: testo → claim → evidenze → verdetti → report."""
    claims = await extract_claims(text)
    if not claims:
        return ("Nessun claim verificabile trovato nel contenuto.", [])

    results: list[ClaimResult] = []
    for claim in claims:
        evidences = await gather_evidence(claim, _get_registry())
        results.append(await judge_claim(claim, evidences))

    return format_report(title, results), results
```

- [ ] **Step 5: run, PASS — commit** `feat: pipeline e report`

---

### Task 12: handlers.py + main.py

**Files:**
- Create: `bot/handlers.py`, `bot/main.py`
- Test: `tests/test_handlers.py`

- [ ] **Step 1: test fallenti** (solo logica di riconoscimento input, no rete)

```python
from bot.handlers import detect_input_type

def test_detect_youtube():
    assert detect_input_type("https://www.youtube.com/watch?v=abc") == "youtube"
    assert detect_input_type("https://youtu.be/abc") == "youtube"

def test_detect_article():
    assert detect_input_type("guarda https://news.example/articolo") == "article"

def test_detect_text():
    assert detect_input_type("il governo ha stanziato 3 miliardi") == "text"
```

- [ ] **Step 2: run, FAIL**
- [ ] **Step 3: bot/handlers.py** (pattern BrainDrop handlers: auth su `AUTHORIZED_USER_ID`, messaggio "sto verificando...", typing action)

```python
import hashlib
import logging
import re
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import get_settings
from bot.ingest import article, image, youtube
from bot.pipeline import run_check
from db.models import Database

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+")
_YT_RE = re.compile(r"(youtube\.com/watch|youtu\.be/|youtube\.com/shorts)")

_db: Database | None = None


def _get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(get_settings().DB_PATH)
    return _db


def detect_input_type(text: str) -> str:
    m = _URL_RE.search(text or "")
    if m:
        return "youtube" if _YT_RE.search(m.group()) else "article"
    return "text"


def _authorized(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == get_settings().AUTHORIZED_USER_ID


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update) or update.message is None:
        return
    msg = update.message
    text = msg.text or msg.caption or ""

    await msg.chat.send_action("typing")

    if msg.photo:
        input_type, input_ref = "image", None
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            file = await msg.photo[-1].get_file()
            await file.download_to_drive(tmp.name)
            extracted = await image.extract(tmp.name)
    else:
        input_type = detect_input_type(text)
        if input_type == "youtube":
            url = _URL_RE.search(text).group()
            input_ref = url
            extracted = await youtube.extract(url)
        elif input_type == "article":
            url = _URL_RE.search(text).group()
            input_ref = url
            extracted = await article.extract(url)
        else:
            input_ref = None
            extracted = {"text": text, "source_url": None, "title": "Testo inoltrato"} if text.strip() else None

    if extracted is None:
        await msg.reply_text("⚠️ Non sono riuscito a estrarre il contenuto. Riprova o incolla il testo direttamente.")
        return

    if input_ref is None:
        input_ref = "text:" + hashlib.sha256(extracted["text"].encode()).hexdigest()[:16]

    cached = _get_db().get_recent_check(input_ref, days=7)
    if cached:
        await msg.reply_text("♻️ Già verificata di recente:\n\n" + cached)
        return

    await msg.reply_text("🔍 Sto verificando, ci vorrà qualche minuto...")
    try:
        report, results = await run_check(extracted["text"], title=extracted.get("title") or "notizia")
    except Exception as e:
        logger.error(f"Pipeline fallita: {e}")
        await msg.reply_text("❌ Errore durante la verifica. Riprova più tardi.")
        return

    _get_db().save_check(input_type, input_ref, extracted.get("title"), report, results)
    await msg.reply_text(report, disable_web_page_preview=True)
```

- [ ] **Step 4: bot/main.py** (pattern BrainDrop main.py)

```python
import logging

from dotenv import load_dotenv

load_dotenv()  # esporta .env in os.environ per le librerie (Tavily, DeepSeek)

from telegram.ext import Application, MessageHandler, filters

from bot.config import get_settings
from bot.handlers import handle_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def main() -> None:
    settings = get_settings()
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN.get_secret_value()).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.CAPTION, handle_message))
    logging.getLogger(__name__).info("FactChecking bot avviato (polling)")
    app.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: run tutti i test, PASS — commit** `feat: handlers Telegram e entrypoint`

---

### Task 13: verifica finale

- [ ] **Step 1: suite completa** — `pytest -v`, tutti PASS
- [ ] **Step 2: smoke import** — `python -c "import bot.main"` senza errori (con .env presente)
- [ ] **Step 3: README aggiornato** se divergenze emerse durante implementazione
- [ ] **Step 4: commit finale + push**

---

## Note esecuzione

- Test con API mockate: nessuna chiamata di rete nei test.
- Ogni task committa separatamente.
- Prova end-to-end reale (bot live con key vere) è manuale, fuori dalla suite: `python -m bot.main`, inviare un link di notizia al bot.
