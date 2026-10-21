/**
 * Figures derived from data/, computed at build time.
 *
 * Every number a page shows about interventions, entities, mandates, barrios or languages
 * must come from here, never be typed into the page: hand-written figures drifted three times
 * (581 vs 597, Cabanyal 41/42 vs 43). The QA check G1 fails if a page hardcodes one of them.
 * Figures from other datasets (complaints, participatory budgets…) live in
 * scripts/qa/figures.yml instead. Formulas match the former update-web-stats skill, except that
 * the years of the current mandate come from data/mandats.json and the build date (D3).
 */
import { readFileSync, statSync } from 'fs';
import { resolve } from 'path';
import { readData } from './data.ts';

export const MANDAT_IDS = ['2011-2015', '2015-2019', '2019-2023', '2023-2027'] as const;
export type MandatId = (typeof MANDAT_IDS)[number];

const ENV_TERMS = ['medi_ambient', 'contaminacio', 'zones_verdes', 'emergencies_climatiques',
                   'dana_2024', 'benestar_animal'];

export interface MandatStats {
  id: MandatId;
  count: number;
  /** Years the mandate has lasted: inici→fi, or inici→build date for the current one (max 4). */
  years: number;
  perYear: number;
  /** Share of interventions by original language, in % (rounded). */
  idioma: { valenciano: number; castellano: number };
  env: number;
  urbanisme: number;
  current: boolean;
}

export interface Stats {
  interventions: number;
  entities: number;
  plenosWithInterventions: number;
  mandates: number;
  firstYear: number;
  lastYear: number;
  /** lastYear − firstYear: "15 años de datos". */
  yearsSpan: number;
  byMandat: Record<MandatId, MandatStats>;
  mandats: MandatStats[];
  current: MandatStats;
  first: MandatStats;
  /** Interventions per year, current mandate vs 2011–2015. */
  perYearRatio: number;
  /** Interventions about the environment, current mandate vs 2011–2015 (counts). */
  envRatio: number;
  /** Entities with interventions in all four mandates. */
  entitiesAllMandats: number;
  entitiesThreeMandats: number;
  topBarri: { name: string; count: number };
  zoneCounts: Record<string, number>;
  /** Overall share by original language, in % (rounded). */
  idioma: { valenciano: number; castellano: number };
  avgCapSubtopics: number;
  /** Public dataset sizes in bytes (web/public/datos). */
  fileSizes: Record<string, number>;
}

const publicDir = resolve(process.cwd(), 'public', 'datos');

const readJson = readData;

function yearsBetween(a: string, b: Date): number {
  return (b.getTime() - new Date(a).getTime()) / (365.25 * 24 * 3600 * 1000);
}

function pct(n: number, total: number): number {
  return total ? Math.round((n / total) * 100) : 0;
}

let cached: Stats | null = null;

export function getStats(now: Date = new Date()): Stats {
  if (cached) return cached;
  const ivs = readJson<any[]>('intervencions.json');
  const ents = readJson<any[]>('entitats.json');
  const plenos = readJson<any[]>('plenos.json');
  const mandatsMeta = readJson<any[]>('mandats.json');
  const metaById = Object.fromEntries(mandatsMeta.map((m) => [m.id, m]));

  const mandatList: MandatStats[] = MANDAT_IDS.map((id) => {
    const sub = ivs.filter((iv) => iv.mandat_id === id);
    const meta = metaById[id];
    const current = !meta?.fi;
    const end = meta?.fi ? new Date(meta.fi) : now;
    const years = Math.min(4, Math.max(yearsBetween(meta.inici, end), 0.25));
    const lang = (l: string) => pct(sub.filter((iv) => iv.idioma_original === l).length, sub.length);
    const hasTerm = (iv: any, terms: string[]) =>
      terms.some((t) => JSON.stringify(iv.temes_v2 || {}).includes(t));
    return {
      id,
      count: sub.length,
      years,
      perYear: Math.round(sub.length / years),
      idioma: { valenciano: lang('valenciano'), castellano: lang('castellano') },
      env: sub.filter((iv) => hasTerm(iv, ENV_TERMS)).length,
      urbanisme: sub.filter((iv) => 'urbanisme' in (iv.temes_v2 || {})).length,
      current,
    };
  });
  const byMandat = Object.fromEntries(mandatList.map((m) => [m.id, m])) as Record<MandatId, MandatStats>;
  const first = byMandat['2011-2015'];
  const current = mandatList.find((m) => m.current) ?? mandatList[mandatList.length - 1];

  const entityMandats: Record<string, Set<string>> = {};
  for (const iv of ivs) {
    if (!iv.entitat_id || !(MANDAT_IDS as readonly string[]).includes(iv.mandat_id)) continue;
    (entityMandats[iv.entitat_id] ??= new Set()).add(iv.mandat_id);
  }
  const mandatCounts = Object.values(entityMandats).map((s) => s.size);

  const zoneCounts: Record<string, number> = {};
  for (const iv of ivs) for (const z of new Set<string>(iv.zones || [])) zoneCounts[z] = (zoneCounts[z] || 0) + 1;
  const [topName, topCount] = Object.entries(zoneCounts).sort((a, b) => b[1] - a[1])[0] ?? ['', 0];

  const years = ivs.map((iv) => Number(String(iv.fecha).slice(0, 4))).filter(Boolean);
  const withCap = ivs.filter((iv) => (iv.cap_subtopics || []).length);
  const lang = (l: string) => pct(ivs.filter((iv) => iv.idioma_original === l).length, ivs.length);

  const fileSizes: Record<string, number> = {};
  for (const f of ['intervencions.json', 'intervencions_metadata.csv', 'entitats.json', 'intervencions_light.json']) {
    try { fileSizes[f] = statSync(resolve(publicDir, f)).size; } catch { fileSizes[f] = 0; }
  }

  const perYear = (m: MandatStats) => m.count / m.years;
  cached = {
    interventions: ivs.length,
    entities: ents.length,
    plenosWithInterventions: plenos.filter((p) => p.num_intervencions > 0).length,
    mandates: mandatList.filter((m) => m.count > 0).length,
    firstYear: Math.min(...years),
    lastYear: Math.max(...years),
    yearsSpan: Math.max(...years) - Math.min(...years),
    byMandat,
    mandats: mandatList,
    current,
    first,
    perYearRatio: perYear(first) ? perYear(current) / perYear(first) : 0,
    envRatio: first.env ? current.env / first.env : 0,
    entitiesAllMandats: mandatCounts.filter((n) => n === MANDAT_IDS.length).length,
    entitiesThreeMandats: mandatCounts.filter((n) => n === MANDAT_IDS.length - 1).length,
    topBarri: { name: topName, count: topCount },
    zoneCounts,
    idioma: { valenciano: lang('valenciano'), castellano: lang('castellano') },
    avgCapSubtopics: withCap.length
      ? withCap.reduce((s, iv) => s + iv.cap_subtopics.length, 0) / withCap.length : 0,
    fileSizes,
  };
  return cached;
}

// ── Formatting ───────────────────────────────────────────────────────────────

/** 1.234 in both languages (thousands with a dot, as the site already writes them). */
export function fmtInt(n: number): string {
  return Math.round(n).toLocaleString('es-ES', { useGrouping: 'always' } as any);
}

/** "×4.8": ratios keep the dot in both languages, as the site already writes them. */
export function fmtRatio(r: number): string {
  return `×${r.toFixed(1)}`;
}

/** One decimal: dot in cas (as the site writes 4.3 MB), comma in val. */
export function fmtDecimal(n: number, lang: 'cas' | 'val'): string {
  const s = n.toFixed(1);
  return lang === 'val' ? s.replace('.', ',') : s;
}

export function fmtSize(bytes: number, lang: 'cas' | 'val'): string {
  if (bytes >= 1024 * 1024) return `${fmtDecimal(bytes / (1024 * 1024), lang)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}

// ── Cross-channel periods (otras-voces · la-ciutat) ──────────────────────────
// Each cross compares interventions only over the years every channel in it covers, worked out
// from the data. "2019-2026" used to be typed in, from when the dataset started in 2019.

export interface Period { from: number; to: number }

export interface CrossPeriods {
  interventions: Period;
  /** Participatory budgets: first year of the first edition → second year of the last (2015/16 → 2025/26). */
  budgets: Period;
  complaints: Period;
  /** Interventions × participatory budgets (cross B). */
  ivBudgets: Period;
  /** Interventions × budgets × complaints (table C). */
  allThree: Period;
  /** Latest complete calendar year at build time (the current one is incomplete). */
  lastCompleteYear: number;
}

function overlap(...ps: Period[]): Period {
  return { from: Math.max(...ps.map((p) => p.from)), to: Math.min(...ps.map((p) => p.to)) };
}

let crossCached: CrossPeriods | null = null;

export function getCrossPeriods(now: Date = new Date()): CrossPeriods {
  if (crossCached) return crossCached;
  const s = getStats(now);
  const interventions = { from: s.firstYear, to: s.lastYear };
  const editions = Object.values(readJson<any>('presupuestos_oficial.json')._meta.ediciones) as string[];
  const first = editions[0], last = editions[editions.length - 1];
  const budgets = { from: Number(first.slice(0, 4)), to: 2000 + Number(last.slice(-2)) };
  const qYears = (readJson<any>('quejas.json').years as string[]).map(Number);
  const complaints = { from: Math.min(...qYears), to: Math.max(...qYears) };
  crossCached = {
    interventions, budgets, complaints,
    ivBudgets: overlap(interventions, budgets),
    allThree: overlap(interventions, budgets, complaints),
    lastCompleteYear: now.getFullYear() - 1,
  };
  return crossCached;
}

/** Scopes of an intervention about a place, as opposed to the whole city or several districts. */
export const LOCAL_AMBITS = ['barri', 'districte', 'multi_barri'];

/** Number of interventions mentioning a district (explicitly or through one of its barrios) in a period.
 *  With `localOnly`, only those whose scope is local (LOCAL_AMBITS): a city-wide intervention that names
 *  every district in passing is not about that district. */
export function districtInterventions(district: string, period: Period, localOnly = false): number {
  const barris = readJson<any[]>('raw/barris_referencia.json');
  const toDistrict = Object.fromEntries(barris.map((b) => [b.nom, b.districte_nom]));
  return readJson<any[]>('intervencions.json').filter((iv) => {
    const y = Number(String(iv.fecha).slice(0, 4));
    if (y < period.from || y > period.to) return false;
    if (localOnly && !LOCAL_AMBITS.includes(iv.ambit)) return false;
    const ds = new Set<string>([...(iv.districtes || []),
      ...(iv.zones || []).map((z: string) => toDistrict[z]).filter(Boolean)]);
    return ds.has(district);
  }).length;
}

// ── Reference counts (metodologia · la-ciutat) ───────────────────────────────

export interface ReferenceCounts {
  categories: number;
  subcategories: number;
  barris: number;
  districtes: number;
  /** Mandates, oldest first, with their mayor */
  mandats: { id: string; alcalde: string; current: boolean }[];
  vulnerabilityBarris: number;
  /** First and last year of the population series per barri */
  populationYears: Period;
}

export function getReferenceCounts(): ReferenceCounts {
  const taxonomy = JSON.parse(readFileSync(resolve(process.cwd(), '..', 'scripts', 'lib', 'taxonomy.json'), 'utf-8'));
  const barris = readJson<any[]>('raw/barris_referencia.json');
  const mandats = readJson<any[]>('mandats.json')
    .slice().sort((a, b) => String(a.inici).localeCompare(String(b.inici)))
    .map((m) => ({ id: m.id, alcalde: m.alcalde, current: !m.fi }));
  const pob = readJson<Record<string, any>>('raw/barri_poblacion.json');
  const years = Object.values(pob).flatMap((b: any) => Object.keys(b.poblacion_por_anyo || {})).map(Number);
  return {
    categories: Object.keys(taxonomy.categories).length,
    subcategories: Object.values(taxonomy.categories as Record<string, string[]>).flat().length,
    barris: barris.length,
    districtes: new Set(barris.map((b) => b.districte_nom)).size,
    mandats,
    vulnerabilityBarris: Object.keys(readJson<Record<string, unknown>>('vulnerabilidad.json')).length,
    populationYears: { from: Math.min(...years), to: Math.max(...years) },
  };
}
