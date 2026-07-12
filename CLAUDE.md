# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Critical rules

- **NEVER overwrite data files without asking first.** Before running any script that writes to `data/` (especially `07_build_final_json.py`, `apply_merges.py`, or any build/pipeline script), ALWAYS ask the user for confirmation. These files may contain work produced by expensive API calls that cannot be easily regenerated.
- **Before running a destructive or overwriting operation**, explain exactly which files will be modified and what data could be lost. Wait for explicit approval.

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

- `bold_highlights.py`: Batch-adds **bold** markers to key phrases in intervention texts via Claude Haiku. Processes `text_original`, `text_cas`, `text_val` in `interventions_raw.json`. Idempotent, saves after each intervention.
- `reclassify_interventions.py`: Classifies interventions with two-level thematic taxonomy + geographic scope via Claude Haiku. Writes `temes_v2`, `ambit`, `zones`, `districtes` to `interventions_raw.json`.
- `export_dataset.py`: Generates public dataset files in `web/public/datos/`. Run after every data update: `python3 scripts/export_dataset.py`. Outputs `intervencions.json`, `intervencions_metadata.csv`, `entitats.json`.

## Web (Astro)

```bash
cd web
npm install
npm run dev     # dev server (port 4321)
npm run build   # static build → web/dist/
```

- Routes: `/cas/` (castellano) and `/val/` (valencià), `/` redirects to `/cas/`
- i18n strings: `src/i18n/cas.json` and `src/i18n/val.json`
- Data loaded at build time from `../data/*.json` (relative to `web/`)
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
- `idioma_original`: `valenciano | castellano | mixt`
- `text_cas`, `text_val`: full text in both languages (with **bold** markers and paragraph breaks)
- `resum_cas`, `resum_val`: 1-2 sentence summary
- `temes`: array from old flat list (kept for backwards compatibility)
- `temes_v2`: two-level taxonomy `{ "category": ["subcategory1", "subcategory2"] }`
- `ambit`: geographic scope (`barri | districte | multi_barri | multi_districte | ciutat | area_metropolitana | no_especificat`)
- `zones`: array of normalized barrio names
- `districtes`: array of normalized district names
- `cap_major`: list of CAP major topic codes (1-2 digits)
- `cap_subtopics`: list of CAP subtopic codes (3-4 digits)

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

## Current data state (2026-05-17)

- **570 interventions** from **4 mandates** (2011–2026)
  - 2011–2015 (Rita Barberá): 75 · 2015–2019 (Ribó I): 116 · 2019–2023 (Ribó II): 115 · 2023–2027 (Catalá): 262
- **277 normalized entities** after merges
- 5 entities present in all 4 mandates: Candombe, Nazaret Unido, Lambda, Acció Ecologista-Agró, FAVV

## Key pipeline notes

- Script 06 is non-deterministic (Claude groupings vary per run) — never rely on entity IDs it produces. Always run `apply_merges.py` after.
- `interventions_raw.json` has no `entitat_id` field — that is computed by script 07 via `entity_variant_map.json`.
- Script 07 `paragraphize()` auto-splits long text blocks into paragraphs at sentence boundaries.
- Two intervention section header formats: `INTERVENCIONS CIUTADANES` (plural, general block) and `INTERVENCIÓ CIUTADANA` (singular, tied to a specific agenda item).
- Script 05 uses `claude-haiku-4-5-20251001` with `max_tokens=8096`.
- API key: `.env` uses `ANTHROPIC=sk-ant-...`; scripts support both `ANTHROPIC_API_KEY` and `ANTHROPIC`.
- Geographic reference data from Valencia Open Data Portal (geoportal.valencia.es): 88 barrios, 19 districts.
