# FactChecking Bot 🔍

Bot Telegram personale per il fact-checking di notizie. Invii un link, un testo, uno screenshot, un video YouTube, un post/reel Instagram o un video TikTok — il bot estrae le affermazioni verificabili (claim), cerca evidenze sul web e risponde con un verdetto per ogni claim, con fonti citate. Funziona anche con domande ("le scie chimiche fanno male?" → verifica il claim implicito).

## Input supportati

| Input | Estrazione |
|---|---|
| 🔗 Link articolo | Firecrawl → testo |
| 📝 Testo / claim incollato | diretto (domande → claim implicito) |
| 📸 Screenshot post social | OCR vision (gpt-4o-mini) |
| ▶️ Video YouTube | yt-dlp metadata + transcript |
| 📷 Post/reel Instagram | instaloader caption + OCR slide caroselli + Whisper su audio reel |
| 🎵 Video TikTok | yt-dlp caption + Whisper su audio (anche link brevi vm/vt.tiktok.com) |

## Come funziona

```
input (link / testo / foto / YouTube / Instagram / TikTok)
   │
   ▼
ingest ──────────► testo della notizia
   │
   ▼
extractor ───────► claim atomici verificabili (max 5)
   │
   ▼  per ogni claim
researcher ──────► evidenze dal web (fonti a tier: fact-checker → primarie → stampa)
   │
   ▼
judge ───────────► verdetto basato SOLO sulle evidenze (mai sulla memoria del modello)
   │
   ▼
validazione ─────► controllo meccanico: URL e citazioni devono esistere davvero
   │
   ▼
report Telegram:  ✅ VERO / ❌ FALSO / ⚠️ NON VERIFICABILE + fonti
```

### Anti-allucinazione

Il verdetto non si fida del modello:

- il judge riceve **solo** le evidenze recuperate e deve citare URL + frase esatta;
- il codice verifica **meccanicamente** che ogni URL citato sia tra quelli realmente recuperati e che ogni citazione esista nel testo della fonte — citazione inventata → verdetto declassato a `non verificabile`;
- la confidenza è **calcolata** (numero di fonti indipendenti concordi, qualità del dominio), non autodichiarata;
- `⚠️ NON VERIFICABILE` è una risposta legittima: il bot non riempie mai i vuoti.

### Fonti a tier (`sources.yaml`)

| Tier | Fonti | Peso |
|---|---|---|
| 0 | Fact-checker editoriali (Open, Pagella Politica, Facta, Snopes) via Google Fact Check API | massimo |
| 1 | Fonti primarie (ISTAT, Eurostat, ISS, ANSA, Reuters, AP) | alto |
| 2 | Stampa maggiore (Corriere, Repubblica, BBC, Guardian…) | medio |
| 3 | Resto del web | basso |
| ✗ | Blacklist disinformazione | mai conteggiato |

## Stack

- [agno](https://github.com/agno-agi/agno) + DeepSeek — agenti LLM (extractor, judge)
- [Tavily](https://tavily.com) — ricerca evidenze
- [Firecrawl](https://firecrawl.dev) — scraping articoli e fonti
- OpenAI — vision OCR (gpt-4o-mini) e trascrizione audio (Whisper)
- instaloader + yt-dlp — estrazione contenuti social
- python-telegram-bot — interfaccia
- SQLite — archivio verifiche + cache (stesso URL < 7 giorni → risposta immediata)

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # poi compila le chiavi
python -m bot.main
```

In alternativa, doppio click su `start.bat`.

Chiavi richieste: `TELEGRAM_BOT_TOKEN`, `AUTHORIZED_USER_ID`, `DEEPSEEK_API_KEY`, `TAVILY_API_KEY`, `FIRECRAWL_API_KEY`, `OPENAI_API_KEY` (OCR screenshot e Whisper). Opzionale: `GOOGLE_FACTCHECK_API_KEY` (tier 0).

Su Telegram: `/start` mostra le istruzioni; poi invia direttamente il contenuto da verificare. Solo l'utente con `AUTHORIZED_USER_ID` viene servito.

## Test

```bash
pytest -v
```

Tutti i test girano offline: API e LLM sono mockati.

## Documentazione

- Spec di design: [`docs/superpowers/specs/2026-06-11-factchecking-bot-design.md`](docs/superpowers/specs/2026-06-11-factchecking-bot-design.md)
- Piano di implementazione: [`docs/superpowers/plans/2026-06-11-factchecking-bot.md`](docs/superpowers/plans/2026-06-11-factchecking-bot.md)

Roadmap v2: escalation deep research sui claim non verificabili (Gemini Interactions / OpenAI deep research via agno).
