import { useState, useMemo } from 'preact/hooks';

type Entitat = {
  id: string;
  nom_cas: string;
  nom_val: string;
  tipus: string;
  num_intervencions: number;
  barri?: string;
  temes_principals?: string[];
};

type Props = {
  entitats: Entitat[];
  lang: 'cas' | 'val';
  labels: {
    entitats_intervencions: string;
    sort_az: string;
    sort_count: string;
    search_placeholder: string;
  };
  tipus_labels: Record<string, string>;
  temes_labels: Record<string, string>;
  entitats_path: string;
};

function getParam(key: string): string {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get(key) ?? '';
}

function norm(s: string): string {
  return (s ?? '').toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '');
}

const TIPUS_BADGE: Record<string, string> = {
  av:         'background:#dbeafe;color:#1e40af',
  plataforma: 'background:#f3e8ff;color:#7e22ce',
  ong:        'background:#d1fae5;color:#065f46',
  sindical:   'background:#fef9c3;color:#854d0e',
  cultural:   'background:#fef3c7;color:#92400e',
  educacio:   'background:#ccfbf1;color:#115e59',
  esportiu:   'background:#ffedd5;color:#9a3412',
  empresa:    'background:#f1f5f9;color:#475569',
  particular: 'background:#f5f5f4;color:#57534e',
  altres:     'background:#f5f5f4;color:#57534e',
};

export function EntitatsBrowser({ entitats, lang, labels, tipus_labels, temes_labels, entitats_path }: Props) {
  const [query, setQuery] = useState<string>(() => getParam('q'));
  const [ordre, setOrdre] = useState<string>(() => getParam('ordre') || 'az');

  function syncURL(q: string, o: string) {
    const p = new URLSearchParams();
    if (q) p.set('q', q);
    if (o && o !== 'az') p.set('ordre', o);
    const qs = p.toString();
    history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname);
  }

  function handleQuery(val: string) {
    setQuery(val);
    syncURL(val, ordre);
  }

  function handleOrdre(val: string) {
    setOrdre(val);
    syncURL(query, val);
  }

  const filtered = useMemo(() => {
    const nomKey = lang === 'val' ? 'nom_val' : 'nom_cas';
    const q = norm(query);
    let list = q
      ? entitats.filter(e =>
          norm(e.nom_cas).includes(q) ||
          norm(e.nom_val).includes(q) ||
          norm(e.barri ?? '').includes(q)
        )
      : [...entitats];
    if (ordre === 'count') {
      list.sort((a, b) => b.num_intervencions - a.num_intervencions);
    } else {
      list.sort((a, b) => (a[nomKey] ?? '').localeCompare(b[nomKey] ?? '', lang === 'val' ? 'ca' : 'es'));
    }
    return list;
  }, [entitats, query, ordre, lang]);

  const hasQuery = query.length > 0;

  return (
    <div>
      {/* Search + sort bar */}
      <div class="flex gap-3 mb-4 items-center">
        <div class="relative flex-1">
          <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"/>
          </svg>
          <input
            type="search"
            value={query}
            onInput={(e) => handleQuery((e.target as HTMLInputElement).value)}
            placeholder={labels.search_placeholder}
            class="w-full pl-9 pr-8 py-2 text-sm border border-stone-200 rounded-lg outline-none transition-all focus:border-orange-400 focus:ring-2 focus:ring-orange-100"
            style={hasQuery ? 'border-color:#f97316;box-shadow:0 0 0 3px #fff7ed' : ''}
          />
          {hasQuery && (
            <button
              type="button"
              onClick={() => handleQuery('')}
              class="absolute right-2.5 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-600 text-base leading-none"
              aria-label="Limpiar búsqueda"
            >
              ✕
            </button>
          )}
        </div>
        <div class="flex gap-1 shrink-0">
          <button
            type="button"
            onClick={() => handleOrdre('az')}
            class={`text-xs px-3 py-2 rounded-lg border font-medium transition-colors ${
              ordre !== 'count'
                ? 'bg-stone-800 text-white border-stone-800'
                : 'bg-white text-stone-500 border-stone-200 hover:border-stone-300'
            }`}
          >
            {labels.sort_az}
          </button>
          <button
            type="button"
            onClick={() => handleOrdre('count')}
            class={`text-xs px-3 py-2 rounded-lg border font-medium transition-colors ${
              ordre === 'count'
                ? 'bg-stone-800 text-white border-stone-800'
                : 'bg-white text-stone-500 border-stone-200 hover:border-stone-300'
            }`}
          >
            {labels.sort_count}
          </button>
        </div>
      </div>

      {/* Count */}
      <p class="text-xs text-stone-400 mb-4">
        {filtered.length !== entitats.length
          ? `${filtered.length} / ${entitats.length}`
          : `${entitats.length}`}
      </p>

      {/* Grid */}
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map(entitat => {
          const nom = lang === 'val' ? entitat.nom_val : entitat.nom_cas;
          return (
            <a
              key={entitat.id}
              href={`${entitats_path}${entitat.id}/`}
              class="bg-white rounded-xl border border-stone-200 p-5 shadow-sm hover:border-orange-300 hover:shadow-md transition-all group"
            >
              <h2 class="font-semibold text-stone-900 group-hover:text-orange-600 transition-colors leading-snug mb-2">
                {nom}
              </h2>
              <div class="flex items-center justify-between gap-2">
                <span
                  class="text-xs px-2 py-0.5 rounded-full"
                  style={TIPUS_BADGE[entitat.tipus || 'altres']}
                >
                  {tipus_labels[entitat.tipus] ?? entitat.tipus}
                </span>
                <span class="text-sm font-medium text-orange-500 shrink-0">
                  {entitat.num_intervencions} {labels.entitats_intervencions}
                </span>
              </div>
              {entitat.barri && (
                <p class="text-xs text-stone-400 mt-1">{entitat.barri}</p>
              )}
              {entitat.temes_principals && entitat.temes_principals.length > 0 && (
                <div class="flex flex-wrap gap-1 mt-2">
                  {entitat.temes_principals.slice(0, 2).map(tema => (
                    <span key={tema} class="text-xs px-1.5 py-0.5 bg-orange-50 text-orange-600 rounded">
                      {temes_labels[tema] ?? tema}
                    </span>
                  ))}
                </div>
              )}
            </a>
          );
        })}
      </div>
    </div>
  );
}
