import { t } from '../i18n/index.ts';
import type { Lang } from '../i18n/index.ts';
// Single source of categories, subcategories and scopes, shared with the Python pipeline (F1.1).
// Every id needs its cat_/sub_/ambit_ key in src/i18n/{cas,val}.json (QA check C2).
import taxonomy from '../../../scripts/lib/taxonomy.json';

const CATEGORIES: Record<string, string[]> = taxonomy.categories;
// Not a subcategory any more, but older classifications still carry it: keep its label.
const LEGACY_SUBS = ['cultura'];

export function getCatLabels(lang: Lang): Record<string, string> {
  return Object.fromEntries(Object.keys(CATEGORIES).map((c) => [c, t(lang, `cat_${c}`)]));
}

export function getSubLabels(lang: Lang): Record<string, string> {
  const subs = [...Object.values(CATEGORIES).flat(), ...LEGACY_SUBS];
  return Object.fromEntries(subs.map((s) => [s, t(lang, `sub_${s}`)]));
}

export function getAmbitLabels(lang: Lang): Record<string, string> {
  return Object.fromEntries(taxonomy.ambits.map((a: string) => [a, t(lang, `ambit_${a}`)]));
}
