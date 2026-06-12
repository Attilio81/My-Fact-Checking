# Stato del progetto — diario di bordo

Ultimo aggiornamento: 2026-06-12. Scopo: riaprire la repo e ripartire senza ricostruire il contesto.

## Cos'è

Bot Telegram di fact-checking (uso personale, single-user). Input: link, testo/domande, screenshot, YouTube, Instagram, TikTok. Output: verdetto per claim (✅/❌/⚠️) con fonti validate meccanicamente + conteggio token. Archivio SQLite + wiki markdown auto-generata.

- Spec: `docs/superpowers/specs/2026-06-11-factchecking-bot-design.md`
- Piano originale: `docs/superpowers/plans/2026-06-11-factchecking-bot.md`
- 64 test, tutti offline. Suite: `pytest -q` (venv in `.venv`).

## Decisioni architetturali (e perché)

| Decisione | Motivo |
|---|---|
| Pipeline lineare orchestrata da Python, non agente autonomo | costi/latenza prevedibili, debug facile (rif. Loki/OpenFactVerification) |
| agno + DeepSeek (`deepseek-v4-flash`, temperature 0) | stack ereditato da BrainDrop, economico; pattern: `Agent(model=..., output_schema=Model)` + `arun()` |
| Judge "bendato": vede solo le evidenze, mai la sua memoria | anti-allucinazione; il giudizio è comprensione del testo, non conoscenza |
| Validazione meccanica in codice (URL + citazioni) | l'allucinazione non si previene nel prompt, si intercetta deterministicamente |
| Confidenza calcolata in codice, non autodichiarata | i modelli stimano male la propria certezza |
| SQLite locale, no Supabase | bot gira in locale, Telegram unica interfaccia |
| Fonti a tier in `sources.yaml` | peso evidenze modificabile senza toccare codice; Fanpage/Today volutamente tier 3 |
| Max 5 claim per notizia | costo/latenza; configurabile nel prompt extractor |

## Lezioni imparate sul campo (casi reali → fix)

Ogni fix è nato da un report vero andato storto. In ordine:

1. **"le scie chimiche fanno male?"** → domande scartate dall'extractor → ora le domande diventano il claim implicito.
2. **Reel Instagram** → Firecrawl non supporta IG → portato modulo instaloader da BrainDrop (caption + OCR caroselli + Whisper reel); poi TikTok con helper comune `ingest/media.py`.
3. **Post @worldyfinance (inflazione USA)** → confutato con dati ISTAT italiani a confidenza alta (falso confidente!) → regole judge: pertinenza geografica/temporale, claim di attribuzione ("X ha detto Y" → verifica la dichiarazione), evidenze datate su valori correnti; extractor preserva paese/periodo; data odierna passata agli agenti.
4. **Verdetto Nvidia perso** → judge parafrasava le quote, validazione le scartava senza spiegazione → match fuzzy (85% contiguo, `difflib`), retry con feedback, declassamento dichiarato nel report. Aneddoti da fonte anonima → 1 claim riassuntivo.
5. **Ponte sullo Stretto (5⚠️ su notizia vera)** — il caso più istruttivo, 4 round di fix:
   - query inglesi su notizia italiana → query SOLO italiane per fatti domestici;
   - paywall ANSA (>500 char di cookie-wall) → marker paywall → Firecrawl forzato;
   - Tavily con `include_domains` riempie SEMPRE 5 risultati → il fallback "se zero risultati" non scattava MAI → filtro di pertinenza (entità del claim come parole intere, min 2) che guida il fallback;
   - "conti" matchava "continued", "ros" matchava "prosecutors" → word boundary `\b`;
   - **scoperta chiave: Tavily topic=news NON indicizza le testate italiane** (query italiana → Newsweek/NPR). Google News RSS scartato (consent wall + URL dietro API interna Google fragile). Soluzione: **Firecrawl search** (SERP live) per claim `is_current` → ANSA/Sole24Ore/RaiNews al primo colpo. Esito finale: 4✅/5.
6. **Paper "Agents of Chaos"** → 3 claim "nessuna evidenza" con le risposte NELL'ABSTRACT arXiv già recuperato per il claim 1 → pool evidenze condiviso tra i claim della stessa verifica + `fetch_context_documents` (link a fonti primarie nel post — arXiv/DOI/tier≤1 — scaricati una volta, `is_context=True` = bypass filtro pertinenza, arrivano a OGNI judge). Anti-circolarità: mai il post stesso o blog. Riconosce anche `arXiv:NNNN.NNNNN` e link senza protocollo (caption social). **Retest finale di questo caso non ancora confermato dall'utente.**

## Telemetria (per il prossimo giro di ottimizzazione)

Feedback esterno ricevuto: "il rischio non è che menta, è che dica ⚠️ troppo spesso per motivi tecnici; i problemi stanno nel researcher". Confermato empiricamente. Quindi: ogni claim ⚠️ registra il motivo in `claims.unv_reason`:

- `nessuna_evidenza` → problema retrieval
- `evidenze_insufficienti` → spesso esito corretto (aneddoti)
- `declassato_quote` → problema fuzzy/retry
- `errore_giudizio` → errore tecnico

Visibile su ogni pagina wiki e in classifica su `wiki/INDEX.md`. **Prossima decisione (escalation v2 o tuning) va presa guardando questi dati dopo qualche giorno d'uso.**

## TODO / aperture

- [ ] **Escalation deep research v2** (in spec): claim ⚠️ → il judge dichiara cosa gli manca → secondo giro mirato. Opzioni: deep research nativo agno (Gemini Interactions / OpenAI, serve key extra) o loop DeepSeek+tool. Decidere DOPO la telemetria.
- [ ] `reasoning` non salvato in tabella `claims` (solo su pagine wiki) → aggiungere colonna se serve backfill/analisi.
- [ ] Backfill wiki per le verifiche pre-wiki (pagine mancanti, indice le lista).
- [ ] `MAX_CLAIMS` configurabile da `.env` + parallelizzazione claim (`asyncio.gather`) per dimezzare latenza.
- [ ] Modalità dibattito live (audio TV → Whisper a blocchi → dedup claim → pipeline). Discussa, architettura abbozzata in chat: preferire loopback WASAPI a microfono.
- [ ] CLI di debug (`python -m bot.cli "claim"`) con output verboso per stadio.
- [ ] Semantic Scholar API per claim scientifici (tier 0 dei paper).
- [ ] **LICENSE mancante** (= all rights reserved). Decidere MIT/Apache se si vuole open.

## Accordi di lavoro / preferenze

- Dubbi su API agno → consultare SEMPRE la doc: MCP `agno-docs` (find/blz), o https://docs.agno.com — mai a memoria (le API cambiano: `output_schema`, `arun`...). Stessa prudenza con Tavily/Firecrawl (context7 MCP usato in sessione).
- Pattern di lavoro consolidato: l'utente incolla il report Telegram di un caso reale → analisi onesta (anche dei propri bug) → proposta fix numerati → "si" → TDD, commit per tema, push.
- Test sempre offline; verifiche live (API vere) come script temporanei poi rimossi.
- Fanpage/Today: tier 3 di proposito (conferma sì, fonte primaria no).
- Commit in italiano, Conventional Commits.

## File chiave (dove mettere mano)

| Cosa | Dove |
|---|---|
| Prompt extractor (regole claim) | `bot/agents/extractor.py` |
| Catena retrieval (query, tier, fallback, context doc) | `bot/agents/researcher.py` |
| Regole verdetto + retry | `bot/agents/judge.py` |
| Validazione citazioni + confidenza | `bot/validation.py` |
| Gerarchia fonti | `sources.yaml` |
| Orchestrazione + pool evidenze | `bot/pipeline.py` |
| Wiki + statistiche ⚠️ | `bot/wiki.py`, `wiki/INDEX.md` |
| Telemetria DB | `db/models.py` (`unverifiable_stats`) |
