# FactChecking Bot — Design

Data: 2026-06-11
Stato: approvato

## Obiettivo

Bot Telegram che verifica notizie: riceve link articolo, testo libero, screenshot o link YouTube, estrae le affermazioni verificabili (claim), cerca evidenze sul web e risponde con un report per claim (verdetto, confidenza, fonti).

Modellato sull'architettura di BrainDrop (`Documents/GitHub/BrainDrop`): bot python-telegram-bot, agenti specializzati agno + DeepSeek, config pydantic-settings.

## Decisioni chiave

| Tema | Decisione | Motivo |
|---|---|---|
| Interfaccia | Bot Telegram, singolo utente autorizzato | Stesso pattern BrainDrop, già familiare |
| Input | URL articolo, testo libero, immagine (screenshot social), link YouTube | Tutti i canali da cui arrivano notizie da verificare |
| Output | Report per claim: verdetto ✅/❌/⚠️, confidenza, fonti linkate + giudizio complessivo | Trasparente e verificabile dall'utente |
| LLM | DeepSeek via agno | Costi bassi, key già disponibile, stack BrainDrop |
| Ricerca evidenze | Tavily (search) + Firecrawl (scraping fonti chiave); opzionale Google Fact Check Tools API come primo tentativo gratuito | Stack BrainDrop riusabile |
| Architettura verifica | Pipeline lineare a 4 stadi orchestrata da codice Python; agenti agno dentro ogni stadio | Costi/latenza prevedibili, debug facile. Riferimento: Loki/OpenFactVerification |
| Storage | SQLite locale | Bot gira in locale, Telegram unica interfaccia, niente Supabase |

## Architettura

```
bot/
  main.py              # entrypoint, polling Telegram
  handlers.py          # riceve messaggi, riconosce tipo input, smista, formatta report
  config.py            # pydantic-settings da .env
  agents/
    extractor.py       # agno+DeepSeek: testo → lista claim atomici verificabili (max ~5),
                       #   filtro check-worthiness nello stesso prompt
    researcher.py      # per claim: query Tavily → top 3-5 evidenze →
                       #   Firecrawl sulle fonti chiave; opzionale Google Fact Check API prima
    judge.py           # agno+DeepSeek: claim + evidenze → verdetto, confidenza, fonti citate
  ingest/
    article.py         # URL → Firecrawl → testo pulito
    youtube.py         # riuso BrainDrop: yt-dlp metadata + youtube-transcript-api
    image.py           # vision/OCR su screenshot (pattern photo.py di BrainDrop)
db/
  models.py            # SQLite: tabelle checks e claims, funzioni di accesso
tests/
```

## Flusso dati

1. Messaggio Telegram → `handlers.py` riconosce tipo (URL articolo / URL YouTube / foto / testo).
2. Modulo `ingest` corrispondente estrae il testo grezzo.
3. Cache: se URL identico già verificato di recente (es. < 7 giorni) → risposta da DB, fine.
4. `extractor` → lista claim atomici check-worthy (max ~5).
5. Per ogni claim, in sequenza: `researcher` (1 giro di ricerca) → `judge` (verdetto).
6. `handlers` compone il report e lo invia; verifica salvata in SQLite.

Formato report Telegram:

```
📰 Verifica: <titolo/fonte>
1. "Claim..." → ✅ VERO (confidenza alta) — fonte1, fonte2
2. "Claim..." → ❌ FALSO (confidenza media) — fonte3
3. "Claim..." → ⚠️ NON VERIFICABILE
Giudizio complessivo: <sintesi>
```

## Schema SQLite

- `checks`: id, created_at, input_type (article|text|image|youtube), input_ref (URL o hash testo), source_title, report_text
- `claims`: id, check_id (FK), claim_text, verdict (true|false|unverifiable), confidence (high|medium|low), sources (JSON array di URL)

## Anti-allucinazione (requisiti judge e post-validazione)

Principio: il modello non risponde dalla propria memoria — il verdetto deriva esclusivamente dalle evidenze recuperate. Il giudizio è un task di comprensione del testo (le evidenze supportano/confutano il claim?), tassonomia FEVER: supporta / confuta / evidenza insufficiente.

1. **Judge vincolato**: riceve solo claim + evidenze. Prompt: usa esclusivamente le evidenze fornite; se insufficienti o contraddittorie → `unverifiable`; conoscenza interna non ammessa come fonte. Temperature 0.
2. **Output strutturato** (Pydantic via agno):
   ```json
   {
     "verdict": "true | false | unverifiable",
     "confidence": "high | medium | low",
     "evidence_used": [{"url": "...", "quote": "frase esatta dall'evidenza"}],
     "reasoning": "..."
   }
   ```
3. **Validazione meccanica in codice** (deterministica, dopo il judge):
   - ogni `url` citato deve appartenere all'insieme degli URL realmente recuperati; URL estraneo → verdetto declassato a `unverifiable`;
   - ogni `quote` deve esistere nel testo dell'evidenza (match stringa normalizzato); citazione inventata → declassamento;
   - `verdict` true/false senza almeno 1 evidenza valida → forzato `unverifiable`.
4. **Confidenza calcolata in codice**, non autodichiarata dal modello: numero di evidenze indipendenti concordi, diversità di domini, tier delle fonti, presenza di contraddizioni (fonti discordanti → `unverifiable` con nota).
5. `unverifiable` mostrato all'utente è un esito legittimo, mai riempito.

## Fonti a tier

Config `sources.yaml` con gerarchia di fiducia, usata dal researcher (ordine di ricerca) e dal calcolo confidenza (peso evidenze):

- **tier 0 — fact-checker**: verdetti editoriali esistenti via Google Fact Check Tools API (ClaimReview): open.online, pagellapolitica.it, facta.news, snopes.com, reuters.com/fact-check…
- **tier 1 — fonti primarie**: istat.it, eurostat, iss.it, bancaditalia.it, ansa.it, reuters.com, apnews.com…
- **tier 2 — stampa maggiore**: corriere.it, repubblica.it, ilsole24ore.com, bbc.com, theguardian.com…
- **tier 3 — resto del web**: ammesso, peso basso.
- **blacklist**: noti siti di disinformazione, evidenza mai conteggiata.

Ordine di ricerca per claim: Fact Check API (tier 0, gratuita) → Tavily con `include_domains` tier 1-2 → Tavily aperto (tier 3). Confidenza pesata per tier (2 fonti tier 1 concordi > 5 blog tier 3).

## Escalation deep research (progettata, implementazione v2)

Claim `unverifiable` dopo il primo giro → una chiamata deep research → report con citazioni → ri-giudicato dalla pipeline standard (judge + validazione meccanica: le citazioni del report sono evidenze da verificare, non verdetto finale) → ancora nulla → `unverifiable` onesto.

Opzioni implementative (decisione in v2):
- deep research nativo agno: Gemini Interactions (`deep-research-preview-*`, citazioni strutturate, preferito) o OpenAI `o4-mini-deep-research` — richiede key aggiuntiva;
- agente iterativo DeepSeek + tool di ricerca (DeepSeek non ha deep research nativo), pattern minimale dzhng/deep-research.

Costo controllato: parte solo sui claim difficili.

## Gestione errori

- Timeout per ogni chiamata agente (`AGENT_TIMEOUT_SECONDS`, default 60s come BrainDrop).
- Claim senza evidenze sufficienti → verdetto `unverifiable`, mai inventato.
- Scraping Firecrawl fallito → fallback su titolo + snippet dei risultati Tavily.
- Ingest fallito (es. video senza transcript) → messaggio di errore chiaro all'utente.

## Test

- pytest + pytest-asyncio (pattern BrainDrop).
- Agenti LLM e API esterne mockati nei test unitari.
- Test pipeline end-to-end con fixture (articolo di esempio, risposte Tavily registrate).

## Fuori scope v1

- Valutazione affidabilità della testata/dominio.
- Multi-utente.
- Admin web.
- Escalation deep research sui claim non verificabili (progettata sopra, implementazione v2).
- Supabase / deploy remoto.

## Riferimenti

- BrainDrop: `C:\Users\attilio.pregnolato.EGMSISTEMI\Documents\GitHub\BrainDrop`
- Loki / OpenFactVerification (pipeline di riferimento): https://github.com/Libr-AI/OpenFactVerification
- ClaimeAI (Claimify + Tavily): https://github.com/BharathxD/ClaimeAI
- Lista risorse: https://github.com/Cartus/Automated-Fact-Checking-Resources
- Google Fact Check Tools API: https://developers.google.com/fact-check/tools/api
