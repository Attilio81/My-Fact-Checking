# FactChecking Bot 🔍

Bot Telegram personale per il fact-checking delle notizie. Gli mandi una notizia in qualsiasi forma — link, testo copiato, screenshot, video YouTube, post/reel Instagram, video TikTok — e lui la smonta in affermazioni verificabili, cerca le prove sul web e risponde punto per punto: ✅ **VERO**, ❌ **FALSO** o ⚠️ **NON VERIFICABILE**, con le fonti linkate e il costo in token della verifica.

Funziona anche con le domande: "le scie chimiche fanno male?" viene trasformata nel claim implicito da verificare.

```
📰 Verifica: Post Instagram di @thegentleman_post

1. "La Procura di Roma indaga per corruzione sul progetto del Ponte
   sullo Stretto di Messina." → ✅ VERO (confidenza media)
   Le evidenze di Il Sole 24 Ore e Rainews confermano direttamente...
   🔗 https://www.ilsole24ore.com/art/ponte-stretto-procura-roma-...
   🔗 https://www.rainews.it/articoli/2026/06/ponte-sullo-stretto-...

Giudizio complessivo: La notizia appare sostanzialmente confermata:
4 claim su 5 verificati veri, nessuno falso.

🔢 34.083 token LLM in 11 chiamate (in: 27.906 / out: 6.177)
```

## Indice

- [Input supportati](#input-supportati)
- [Come funziona](#come-funziona)
- [Anti-allucinazione: il cuore del progetto](#anti-allucinazione-il-cuore-del-progetto)
- [La ricerca delle evidenze](#la-ricerca-delle-evidenze)
- [Wiki delle verifiche](#wiki-delle-verifiche)
- [Setup](#setup)
- [Uso](#uso)
- [Struttura del progetto](#struttura-del-progetto)
- [Test](#test)
- [Limiti noti](#limiti-noti)
- [Roadmap](#roadmap)

## Input supportati

| Input | Come viene estratto il testo |
|---|---|
| 🔗 Link articolo | Firecrawl → markdown pulito |
| 📝 Testo / claim incollato | diretto; le domande diventano il claim implicito |
| 📸 Screenshot di post social | OCR vision (gpt-4o-mini) |
| ▶️ Video YouTube | yt-dlp (metadata) + youtube-transcript-api (sottotitoli) |
| 📷 Post/reel Instagram | instaloader (caption) + OCR sulle slide dei caroselli + Whisper sull'audio dei reel |
| 🎵 Video TikTok | yt-dlp (caption/autore) + Whisper sull'audio — anche link brevi `vm.`/`vt.tiktok.com` |

## Come funziona

Pipeline lineare a 4 stadi, orchestrata da codice Python (non da un agente autonomo): costi e latenza prevedibili, ogni stadio testabile e controllabile.

```
input (link / testo / foto / YouTube / Instagram / TikTok)
   │
   ▼
ingest ──────────► testo della notizia
   │
   ▼
extractor ───────► claim atomici verificabili (max 5), col contesto esplicito;
   │               storie aneddotiche da fonte anonima → 1 solo claim riassuntivo
   ▼  per ogni claim
researcher ──────► query mirate generate da un agente → evidenze dal web
   │               (fonti a tier + filtro di pertinenza + SERP live per news fresche)
   ▼
judge ───────────► verdetto basato SOLO sulle evidenze fornite
   │               (la conoscenza interna del modello non è ammessa come fonte)
   ▼
validazione ─────► controllo MECCANICO in codice: URL e citazioni
   │               devono esistere davvero nelle fonti recuperate
   ▼
report Telegram:  ✅ VERO / ❌ FALSO / ⚠️ NON VERIFICABILE + fonti + token spesi
```

I claim sono classificati secondo la tassonomia FEVER (supporta / confuta / evidenza insufficiente), con regole specifiche per:

- **claim di attribuzione** ("X ha detto Y") → si verifica che X l'abbia detto, non che Y sia vero;
- **pertinenza geografica/temporale** → evidenze di un paese o periodo diverso da quello del claim non possono confutare né confermare (un claim sull'inflazione USA non si giudica con dati ISTAT);
- **claim al presente su valori che cambiano** (prezzi, tassi, cariche) → evidenze datate portano a "non verificabile", mai a un verdetto stantio.

## Anti-allucinazione: il cuore del progetto

Chiedere a un LLM "questa notizia è vera?" produce risposte inventate con tono sicuro. Qui il modello non può: il giudizio è un task di *comprensione del testo*, non di conoscenza del mondo, e ogni sua affermazione viene verificata dal codice.

1. **Judge bendato** — riceve solo claim + evidenze recuperate, con il divieto esplicito di usare la propria memoria. Temperature 0, output JSON a schema forzato (Pydantic via agno):

   ```json
   {
     "verdict": "true | false | unverifiable",
     "evidence_used": [{"url": "...", "quote": "frase esatta dalla fonte"}],
     "reasoning": "..."
   }
   ```

2. **Validazione meccanica** (in codice, deterministica — `bot/validation.py`):
   - ogni URL citato deve appartenere all'insieme delle evidenze realmente recuperate;
   - ogni citazione deve esistere nel testo della fonte — match esatto normalizzato, oppure fuzzy (almeno l'85% contiguo della frase, `difflib`) per tollerare punteggiatura e parole saltate senza accettare frasi inventate;
   - verdetto true/false senza almeno una citazione valida → forzato a `unverifiable`.

3. **Retry con feedback** — se le citazioni falliscono la validazione (gli LLM parafrasano), il judge riceve una seconda chance con l'elenco delle citazioni respinte e l'ordine di ricopiarle letteralmente. Se fallisce anche il retry, il verdetto viene declassato e **il report lo dichiara**: "(verdetto declassato: citazioni non riscontrate letteralmente nelle fonti)".

4. **Confidenza calcolata, non autodichiarata** — i modelli stimano male la propria certezza. La confidenza la calcola il codice: quante evidenze indipendenti concordano, da quanti domini diversi, di che tier.

5. **⚠️ NON VERIFICABILE è un esito legittimo** — significa "non ho trovato prove sufficienti", che è la risposta onesta. Il bot non riempie mai i vuoti.

## La ricerca delle evidenze

Per ogni claim, in ordine:

1. **Query generator** (agente DeepSeek): 2-3 query mirate con i nomi propri delle entità — in italiano per fatti domestici, in inglese per fatti internazionali. Decide anche se il claim riguarda l'attualità (`is_current`).
2. **Google Fact Check Tools API** (tier 0, gratuita): se un fact-checker professionale (Open, Pagella Politica, Snopes, AFP, FullFact...) ha già verificato il claim, il verdetto editoriale arriva subito.
3. **Tavily** sui domini fidati (tier 1-2), con `topic=news` per i claim di attualità e contenuto completo (`raw_content`).
4. **Firecrawl search** (SERP Google live) per i claim di attualità: copre il ritardo di indicizzazione di Tavily sulle testate italiane fresche — verificato sul campo che senza questo passaggio le notizie italiane del giorno non si trovano.
5. **Filtro di pertinenza** (deterministico): un'evidenza sopravvive solo se contiene le entità del claim come parole intere ("conti" non matcha "continued"). Se le evidenze pertinenti sono meno di 2 → ricerca aperta su tutto il web.
6. **Firecrawl scrape** di rinforzo sulle evidenze con contenuto inutilizzabile (snippet corti, paywall/cookie-wall riconosciuti dai marker).

### Fonti a tier (`sources.yaml`)

| Tier | Fonti | Peso nella confidenza |
|---|---|---|
| 0 | Fact-checker editoriali via Google Fact Check API (Open, Pagella Politica, Facta, Snopes, FactCheck.org) | massimo |
| 1 | Fonti primarie: ISTAT, Eurostat, ISS, Bankitalia, ANSA, AGI, Adnkronos, Reuters, AP + scientifiche (PubMed, Nature, Science, Lancet, NEJM, WHO, CDC, EFSA, IPCC) | alto |
| 2 | Stampa maggiore: Corriere, Repubblica, Sole 24 Ore, Il Post, Fatto Quotidiano, Stampa, Messaggero, TGcom24, RaiNews, Sky TG24, BBC, Guardian, NYT + arXiv e divulgazione scientifica | medio |
| 3 | Resto del web | basso |
| ✗ | Blacklist disinformazione | mai conteggiato |

La gerarchia si modifica in `sources.yaml` senza toccare il codice. Due fonti tier 1 concordi su domini diversi → confidenza alta; una fonte sola → bassa.

## Wiki delle verifiche

Ogni verifica genera automaticamente una pagina markdown nella cartella `wiki/` — un archivio consultabile di tutti i fact-check fatti:

```
wiki/
  INDEX.md                                      # tabella: data | verifica | esito | tipo
  2026/
    2026-06-11-3-post-instagram-di-thegen....md # una pagina per verifica
```

- **`INDEX.md`**: tutte le verifiche, più recenti in alto, con l'esito a colpo d'occhio (`✅4 ❌0 ⚠️1`).
- **Pagina per verifica**: ogni claim con verdetto, motivazione e fonti cliccabili.
- L'indice viene rigenerato dal database a ogni verifica; la scrittura è best-effort (un errore sulla wiki non blocca mai la risposta del bot).
- Cartella configurabile con `WIKI_DIR` nel `.env`. Suggerimento: aprila con Obsidian — diventa una piccola knowledge base navigabile delle bufale verificate.

## Setup

### Prerequisiti

- Python 3.11+ (sviluppato su 3.13)
- Un bot Telegram: crealo con [@BotFather](https://t.me/BotFather) (`/newbot`) → ottieni il token
- Il tuo user ID Telegram: chiedi a [@userinfobot](https://t.me/userinfobot)

### Chiavi API

| Variabile | Servizio | Dove ottenerla | Costo |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram | @BotFather | gratis |
| `AUTHORIZED_USER_ID` | Telegram | @userinfobot | gratis |
| `DEEPSEEK_API_KEY` | DeepSeek (LLM) | [platform.deepseek.com](https://platform.deepseek.com) | centesimi/verifica |
| `TAVILY_API_KEY` | Tavily (search) | [tavily.com](https://tavily.com) | free tier disponibile |
| `FIRECRAWL_API_KEY` | Firecrawl (scraping+SERP) | [firecrawl.dev](https://firecrawl.dev) | free tier disponibile |
| `OPENAI_API_KEY` | OpenAI (OCR + Whisper) | [platform.openai.com](https://platform.openai.com) | solo per screenshot/audio |
| `GOOGLE_FACTCHECK_API_KEY` | Google (tier 0, opzionale) | vedi sotto | gratis |

Per la chiave Google Fact Check (consigliata, gratuita): [abilita la Fact Check Tools API](https://console.cloud.google.com/apis/library/factchecktools.googleapis.com) → [Credenziali](https://console.cloud.google.com/apis/credentials) → **Crea credenziali → Chiave API**. Consigliato limitare la chiave alla sola Fact Check Tools API.

### Installazione

```bash
git clone https://github.com/Attilio81/My-Fact-Checking.git
cd My-Fact-Checking
python -m venv .venv
.venv\Scripts\activate        # Windows — su Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # poi compila le chiavi
python -m bot.main
```

Su Windows, in alternativa: doppio click su `start.bat`.

## Uso

1. Avvia il bot, apri la chat Telegram, manda `/start` per le istruzioni.
2. Invia il contenuto da verificare: link, testo, screenshot, video.
3. Il bot risponde in 1-3 minuti con il report per claim.

Note operative:

- Solo l'utente con `AUTHORIZED_USER_ID` viene servito; gli altri sono ignorati.
- **Cache**: lo stesso URL verificato meno di 7 giorni fa → risposta immediata dall'archivio SQLite (`factcheck.db`), zero costi.
- Ogni report chiude col conteggio token LLM (chiamate DeepSeek; OCR e Whisper sono fatturati a parte da OpenAI).
- Le query generate per ogni claim finiscono nel log a livello INFO — utile per capire perché un claim non trova evidenze.
- Ogni verifica finisce anche nella [wiki markdown](#wiki-delle-verifiche) (`wiki/INDEX.md`).

## Struttura del progetto

```
bot/
  main.py            # entrypoint, polling Telegram
  handlers.py        # riconoscimento tipo input, smistamento, cache, invio report
  config.py          # configurazione da .env (pydantic-settings)
  pipeline.py        # orchestrazione: extractor → researcher → judge per claim
  report.py          # formattazione report e giudizio complessivo
  validation.py      # validazione meccanica citazioni + calcolo confidenza
  sources.py         # caricamento sources.yaml, lookup tier
  usage.py           # conteggio token per verifica (ContextVar)
  wiki.py            # pagine markdown delle verifiche + INDEX.md
  agents/
    extractor.py     # testo → claim atomici (agno + DeepSeek)
    researcher.py    # claim → evidenze (query gen, FactCheck API, Tavily,
                     #   Firecrawl search/scrape, filtro pertinenza)
    judge.py         # claim + evidenze → verdetto validato (retry su quote respinte)
  ingest/
    article.py       # URL → Firecrawl → testo
    youtube.py       # yt-dlp + transcript
    instagram.py     # instaloader + OCR + Whisper
    tiktok.py        # yt-dlp + Whisper
    image.py         # OCR screenshot
    media.py         # helper comune: audio → Whisper
db/
  models.py          # SQLite: tabelle checks e claims, cache
tests/               # 57 test, tutti offline (API e LLM mockati)
sources.yaml         # gerarchia fonti a tier + blacklist
wiki/                # archivio markdown delle verifiche (generato)
```

## Test

```bash
pytest -v
```

Tutti i test girano offline: LLM e API esterne sono mockati. La logica critica (validazione citazioni, confidenza, filtro pertinenza, tier) è pura e testata direttamente.

## Limiti noti

- **Il collo di bottiglia è il retrieval, non il giudizio**: il bot è costruito per non mentire; trovare la verità dipende da cosa pescano le ricerche. Se le fonti giuste non arrivano, l'esito onesto è "non verificabile".
- **Costi**: ogni verifica attraversa fino a 4 API a pagamento (DeepSeek, Tavily, Firecrawl, OpenAI). Una verifica tipica costa centesimi (≈30-50k token DeepSeek + qualche ricerca); la cache aiuta solo sui contenuti ripetuti.
- **Instagram è fragile**: instaloader si rompe periodicamente quando Instagram cambia; i post privati non sono accessibili.
- **Massimo 5 claim per notizia** (i più centrali): scelta di costo/latenza, configurabile nel prompt dell'extractor.
- **Single-user**: progettato per uso personale, un solo utente autorizzato, niente rate limiting multiutente.
- I claim girano in sequenza: ~1-3 minuti per una notizia con 5 claim.

## Roadmap

- **Escalation deep research (v2)**: claim ancora non verificabili dopo il primo giro → una chiamata deep research nativa (Gemini Interactions / OpenAI via agno) il cui report viene ri-giudicato dalla pipeline standard (le citazioni restano evidenze da validare, mai verdetto finale).
- **Modalità dibattito live**: audio TV/streaming → Whisper a blocchi → claim dedup → pipeline → verdetti su Telegram in tempo quasi reale.
- **CLI di debug**: stessa pipeline da terminale con output verboso per iterare sui prompt.
- Parallelizzazione dei claim (`asyncio.gather`) per dimezzare la latenza.
- Semantic Scholar API per i claim scientifici (analogo del tier 0 per i paper).

## Documentazione di progetto

- Spec di design: [`docs/superpowers/specs/2026-06-11-factchecking-bot-design.md`](docs/superpowers/specs/2026-06-11-factchecking-bot-design.md)
- Piano di implementazione: [`docs/superpowers/plans/2026-06-11-factchecking-bot.md`](docs/superpowers/plans/2026-06-11-factchecking-bot.md)

Architettura di riferimento: pipeline ispirata a [Loki/OpenFactVerification](https://github.com/Libr-AI/OpenFactVerification); risorse sul fact-checking automatico: [Automated-Fact-Checking-Resources](https://github.com/Cartus/Automated-Fact-Checking-Resources).
