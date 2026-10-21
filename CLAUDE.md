# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Critical rules

- **NEVER overwrite data files without asking first.** Before running any script that writes to `data/` (especially `07_build_final_json.py`, `apply_merges.py`, or any build/pipeline script), ALWAYS ask the user for confirmation. These files may contain work produced by expensive API calls that cannot be easily regenerated.
- **Before running a destructive or overwriting operation**, explain exactly which files will be modified and what data could be lost. Wait for explicit approval.
- **Avoid needless permission prompts** (the data guard asks for anything it cannot prove harmless): edit files with Edit/Write, never with `python - <<EOF` or `python -c`; don't prefix allowlisted commands with `time` (the run summary already shows the duration); accept known findings with `scripts/.venv/bin/python scripts/qa/run_checks.py --baseline-add --only CHECKS --reason "…"`; read-only analysis in inline Python (`python - <<EOF`, `python -c`) runs without asking as long as it neither writes nor runs anything (the guard checks it), so keep writes out of it; `run_agents.py` and `complete_manual.py` run freely only with `--dry-run` and `retranslate.py` only without `--translate` (they spend API money: never without the user's yes); `propose.py` runs freely, `--push` included (opening the data PR is allowed); run them from the repo root with these full paths, or the rules don't match; `git fetch|pull|push` and `gh` skip the Bash sandbox (`sandbox.excludedCommands`: on macOS git over SSH and gh's TLS fail inside it) only when run as a standalone command — no `cd … &&`, no `&& echo`, no `git -C`, and on one line (pass a PR body with `--body-file`).

## Project

**La Ciutat Parla** — Intervencions ciutadanes als plens de l'Ajuntament de València.
Extreu les intervencions ciutadanes de les actes dels plens municipals i les publica en una web bilingüe (castellano/valencià).

## Structure

```
laciutatparla/
├── scripts/          # Python extraction pipeline
├── data/             # JSON files (source of truth for the web)
├── meta/             # Internal project docs (not in public repo)
│   ├── docs/         # Memoria, notas, análisis
│   ├── concurso/     # Materiales del concurso 2026
│   └── mockups/      # Diseños y prototipos
│   ├── raw/          # Intermediate files (pdfs/, texts/, session indexes)
│   │   ├── interventions_raw.json  # Source of truth for interventions
│   │   ├── barris_referencia.json  # 88 barrios + 19 districts (open data)
│   │   └── entity_variant_map.json
│   ├── plenos/       # One JSON per pleno with full interventions
│   ├── plenos.json   # Index of all plenos
│   ├── intervencions.json  # All interventions flat list
│   └── entitats.json       # Normalized entity catalog
└── web/              # Astro static site
```

## Pipeline (run in order)

```bash
cd scripts
pip install -r requirements.txt

python 01_crawl_index.py       # Crawl session list → data/raw/sessions_index.json
python 02_crawl_sessions.py    # Fetch each session page → data/raw/sessions_metadata.json
python 03_download_pdfs.py     # Download acta PDFs → data/raw/pdfs/
python 04_extract_text.py      # pdftotext + clean → data/raw/texts/

export ANTHROPIC_API_KEY=...
python 05_parse_interventions.py   # Claude extracts structured data → data/raw/interventions_raw.json
python 06_normalize_entities.py    # Normalize entity names → data/entitats.json
python 07_build_final_json.py      # Build final JSONs → data/plenos.json, data/intervencions.json
```

Scripts 01–04 are idempotent (skip already-done work). Script 05 saves after each session for fault tolerance.

After scripts 05–06, run `apply_merges.py` (in `scripts/`) before script 07. This script:
- Applies entity merges using stable entity text patterns (not IDs, which change each script 06 run)
- Applies floor-cession re-attributions (REASSIGN dict) and deletions
- Patches known bad Claude groupings via VARIANT_MAP_FORCED
- Rebuilds `entity_variant_map.json` and `entitats.json` from actual intervention texts

### Additional processing scripts

Run these after `apply_merges.py` + `07_build_final_json.py`, then re-run `07_build_final_json.py` to incorporate the enriched fields:

- `bold_highlights.py`: Batch-adds **bold** markers to key phrases in intervention texts via Claude Haiku. Processes `text_original`, `text_cas`, `text_val` in `interventions_raw.json`. Idempotent, saves after each intervention.
- `reclassify_interventions.py`: Classifies interventions with two-level thematic taxonomy + geographic scope via Claude Haiku. Writes `temes_v2`, `ambit`, `zones`, `districtes` to `interventions_raw.json`. Idempotent.
- `cap_classify.py`: Classifies interventions with Comparative Agendas Project codes via Claude Haiku. Writes `cap_major` (1-2 digit major topic codes) and `cap_subtopics` (4-digit subtopic codes) to `interventions_raw.json`. Idempotent.
- `export_dataset.py`: Generates public dataset files in `web/public/datos/`. Run after every data update: `python3 scripts/export_dataset.py`. Outputs `intervencions.json`, `intervencions_metadata.csv`, `entitats.json`.

## Web (Astro)

```bash
cd web
npm install
npm run dev     # dev server (port 4321)
npm run build   # static build → web/dist/
npm run test:e2e   # Playwright on the fixture site: smoke (every route × 2 languages), axe, visual
npm run check      # astro check (61 errors known in older code: don't add more)
```

- After a production build, `scripts/.venv/bin/python scripts/qa/run_checks.py --only W6,W7,W8 --no-state` checks page weight (ratchet in `meta/qa/web_budget.json`: a page may grow only as the data grows; `scripts/qa/web_budget.py --update` locks in an optimisation), i18n key parity and the default language, and internal links. `/apply-approved` runs W6 and W8 on its build; W7 runs in the pre-commit.

- Tests run on `web/tests/fixtures/data` (regenerate with `scripts/qa/make_web_fixture.py`), never on the real data, so they only fail when the web's code changes. Accept a deliberate visual change with `npx playwright test visual --update-snapshots`; after fixing accessibility problems, lock them in with `A11Y_UPDATE=1 npx playwright test a11y` (the baseline in `tests/a11y-baseline.json` can only shrink). Chromium cannot start inside the macOS Bash sandbox, so `npx playwright test…` and `npm run test:e2e…` are `sandbox.excludedCommands` (run them from `web/` as a standalone command, like git); `sandbox.network.allowLocalBinding` lets local servers (`npm run dev`, `astro preview`) bind a port inside it.

- Routes: `/cas/` (castellano) and `/val/` (valencià); valencià is the default: `/` redirects to `/val/` (`astro.config.mjs` and `public/_redirects`) and `hreflang="x-default"` points to each page's `/val/` version
- i18n strings: `src/i18n/cas.json` and `src/i18n/val.json`
- Data loaded at build time through `src/utils/data.ts` (`readData`, `listData`): `../data` relative to `web/`, or `LCP_DATA_DIR` when set
- Interactive components (FilterBar, InterventionCard) use Preact with `client:load`
- Design: Sora (display) + Outfit (body), dark hero, rounded cards, pill buttons
- Shared label helpers in `src/utils/labels.ts` and formatting in `src/utils/format.ts`

**Current pages** (both `/cas/` and `/val/` unless noted):
- `/` — home: stats, topics, map, top entities, insights teaser
- `/plens/` — session index
- `/intervencions/` — filterable intervention browser
- `/entitats/` — entity catalog
- `/mapa/` — interactive choropleth map
- `/otras-voces/` · `/altres-veus/` — 3 participation channels cross-analysis
- `/la-ciutat/` — socioeconomic context (vulnerability, budget, public works)
- `/datos/` · `/dades/` — open dataset download (JSON+CSV, CC BY 4.0)
- `/analisis/` · `/analisi/` — comparative analysis across mandates
- `/metodologia/` — pipeline documentation, AI role, data sources

## Data schema (key fields)

**Intervention** (`data/intervencions.json`):
- `id`, `pleno_id`, `fecha`, `mandat_id`, `intervinient`, `entitat`, `entitat_id`, `tipus_entitat`
- `entitat_cessio`: floor cession — `null`, or `{nom_cas, nom_val, entitat_id}` naming the organisation the speaker actually represented. `entitat`/`entitat_id` stay the **registered** entity (so every aggregate counts it there); this field is a display-only mention, rendered as "en nombre de …" / "en nom de …". Its `entitat_id` is kept only when it resolves to a real catalog entity, so the web links it; otherwise `null` and the mention is plain text. Source: `entitat_cessio` in `data/corrections/reassignments.yml`.
- `idioma_original`: `valenciano | castellano` — the language of more than 50 % of the speech, in characters paragraph by paragraph (QA check C4). There is no `mixt`.
- The text in that language is `text_original` verbatim (in `interventions_raw.json` that field is empty; script 07 fills it); the other is a full translation, with no paragraph left untranslated. `scripts/qa/retranslate.py` fixes what C4 flags.
- `text_cas`, `text_val`: full text in both languages (with **bold** markers and paragraph breaks)
- `resum_cas`, `resum_val`: 1-2 sentence summary
- `temes`: array from old flat list (kept for backwards compatibility)
- `temes_v2`: two-level taxonomy `{ "category": ["subcategory1", "subcategory2"] }`
- `ambit`: geographic scope (`barri | districte | multi_barri | multi_districte | ciutat | area_metropolitana | no_especificat`)
- `zones`: array of normalized barrio names
- `districtes`: array of normalized district names
- `cap_major`: list of CAP major topic codes (1-2 digits)
- `cap_subtopics`: list of CAP subtopic codes (3-4 digits)

**Pleno** (`data/plenos.json`, `data/plenos/{id}.json`) — video fields:
- `url_video`: the session's recording (first part when it is split). May still hold the
  generic live-player URL for sessions the video archive does not list.
- `url_videos`: every part of a split recording, in order. **Empty when there is only one.**
- Both come from `data/corrections/session_videos.yml`, which script 07 overlays on the
  scraped session metadata. Regenerate it with `python3 scripts/scrape_video_archive.py`.
  The session pages on valencia.es no longer publish per-session recording links — only a
  live player identical on every session — so `url_video` as scraped by script 02 is
  useless for most sessions. Script 02 never downgrades a recording it already has.

**Thematic taxonomy** (9 categories, 30+ subcategories):
- `urbanisme`: espai_public, habitatge, patrimoni, usos_turistics
- `mobilitat`: transit, mobilitat_activa, transport_public, aparcament, zbe
- `medi_ambient`: contaminacio, zones_verdes, emergencies_climatiques, dana_2024, benestar_animal
- `serveis_publics`: seguretat, serveis_socials, educacio, salut
- `economia`: pressupostos, comerc_ocupacio, agricultura
- `drets_i_igualtat`: interculturalitat_i_antiracisme, igualtat_de_genere, diversitat, drets_humans, drets_linguistics
- `persones`: joventut, gent_major
- `cultura`: esports, patrimoni_cultural, associacionisme, festes
- `participacio`: participacio, processos_participatius, transparencia, consells_sectorials

## Current data state (2026-10-18)

- **602 interventions** from **4 mandates** (2011–2026)
  - 2011–2015 (Rita Barberá): 75 · 2015–2019 (Ribó I): 117 · 2019–2023 (Ribó II): 108 · 2023–2027 (Catalá): 300 · no mandate (`desconegut`): 2
- **247 normalized entities** after merges
- 7 entities present in all 4 mandates: Candombe, Nazaret Unido, Lambda, Acció Ecologista-Agró, FAVV, AV Patraix, AV Cabanyal-Canyamelar

## Key pipeline notes

- Script 06 is non-deterministic (Claude groupings vary per run) — never rely on entity IDs it produces. Always run `apply_merges.py` after.
- `interventions_raw.json` has no `entitat_id` field — that is computed by script 07 via `entity_variant_map.json`.
- Script 07 `paragraphize()` auto-splits long text blocks into paragraphs at sentence boundaries.
- Two intervention section header formats: `INTERVENCIONS CIUTADANES` (plural, general block) and `INTERVENCIÓ CIUTADANA` (singular, tied to a specific agenda item).
- Script 05 uses `claude-haiku-4-5-20251001` with `max_tokens=8096`.
- Script 05 decides what to parse from the `pleno_id`s missing in `interventions_raw.json`, so an acta whose extractions were all later deleted looks unprocessed on every run and gets re-parsed forever. `data/corrections/skip_plenos.yml` lists those actas so the loop stops costing API calls.
- API key: `.env` uses `ANTHROPIC=sk-ant-...`; scripts support both `ANTHROPIC_API_KEY` and `ANTHROPIC`.
- Geographic reference data from Valencia Open Data Portal (geoportal.valencia.es): 88 barrios, 19 districts.
