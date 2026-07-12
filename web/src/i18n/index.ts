import cas from './cas.json';
import val from './val.json';

export type Lang = 'cas' | 'val';
export type TranslationKey = keyof typeof cas;

const translations = { cas, val };

export function t(lang: Lang, key: string): string {
  const dict = translations[lang] as Record<string, unknown>;
  const parts = key.split('.');
  let val: unknown = dict;
  for (const part of parts) {
    if (val && typeof val === 'object') {
      val = (val as Record<string, unknown>)[part];
    } else {
      return key;
    }
  }
  return typeof val === 'string' ? val : key;
}

export function getLangFromUrl(url: URL): Lang {
  const [, lang] = url.pathname.split('/');
  if (lang === 'val') return 'val';
  return 'cas';
}

const SLUG_MAP: Record<string, Record<Lang, string>> = {
  'otras-voces': { cas: 'otras-voces', val: 'altres-veus' },
  'altres-veus': { cas: 'otras-voces', val: 'altres-veus' },
  'datos':       { cas: 'datos',       val: 'dades' },
  'dades':       { cas: 'datos',       val: 'dades' },
  'analisis':    { cas: 'analisis',    val: 'analisi' },
  'analisi':     { cas: 'analisis',    val: 'analisi' },
};

export function switchLangUrl(url: URL, targetLang: Lang): string {
  const parts = url.pathname.split('/');
  parts[1] = targetLang;
  if (parts[2] && SLUG_MAP[parts[2]]) {
    parts[2] = SLUG_MAP[parts[2]][targetLang];
  }
  return parts.join('/');
}

/** Format a date string (YYYY-MM-DD) to a localized display */
export function formatDate(dateStr: string, lang: Lang): string {
  const date = new Date(dateStr + 'T12:00:00');
  return date.toLocaleDateString(lang === 'val' ? 'ca-ES' : 'es-ES', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}
