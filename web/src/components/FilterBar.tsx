import { useState, useMemo, useEffect } from 'preact/hooks';
import { InterventionCard } from './InterventionCard.tsx';

function norm(s: string) {
  return (s ?? '').toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '');
}

function getParam(key: string): string {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get(key) ?? '';
}

interface Intervention {
  id: string;
  pleno_id: string;
  fecha: string;
  mandat_id: string;
  ordre: number;
  intervinient: string;
  entitat: string;
  entitat_id: string;
  tipus_entitat: string;
  barri_o_zona: string | null;
  punts_ordre_dia: string;
  idioma_original: 'valenciano' | 'castellano' | 'mixt';
  text_cas: string;
  text_val: string;
  temes: string[];
  temes_v2: Record<string, string[]>;
  ambit: string;
  zones: string[];
  districtes: string[];
  resum_cas: string;
  resum_val: string;
}

interface Props {
  intervencions: Intervention[];
  lang: 'cas' | 'val';
  labels: {
    filter_tema: string;
    filter_tipus: string;
    filter_mandat: string;
    filter_any: string;
    filter_reset: string;
    filter_todos: string;
    idioma_valenciano: string;
    idioma_castellano: string;
    idioma_mixt: string;
    ver_texto: string;
    ocultar_texto: string;
    traduccion: string;
    original: string;
    punts: string;
    en_representacio: string;
    ambit_labels: Record<string, string>;
  };
  temes_labels: Record<string, string>;
  cat_labels: Record<string, string>;
  sub_labels: Record<string, string>;
  tipus_labels: Record<string, string>;
  mandats_labels: Record<string, string>;
  plens_path: string;
  entitats_path: string;
  pageTitle?: string;
}

const CHEVRON_SVG = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`;

const selectBase: Record<string, string> = {
  appearance: 'none',
  WebkitAppearance: 'none',
  fontFamily: "'Outfit', system-ui, sans-serif",
  fontSize: '0.875rem',
  fontWeight: '500',
  color: '#444',
  background: `#fff ${CHEVRON_SVG} no-repeat right 12px center`,
  border: '1px solid #ddd',
  borderRadius: '100px',
  padding: '9px 36px 9px 16px',
  cursor: 'pointer',
  transition: 'border-color 0.15s, box-shadow 0.15s',
};

const selectActive: Record<string, string> = {
  ...selectBase,
  color: '#1e1e1e',
  borderColor: '#e8562a',
  background: `#fef8f5 ${CHEVRON_SVG} no-repeat right 12px center`,
};

const chipStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '5px',
  fontFamily: "'Outfit', system-ui, sans-serif",
  fontSize: '0.8125rem',
  fontWeight: '500',
  color: '#b84012',
  background: '#fef3ee',
  border: '1px solid #f5c0a8',
  borderRadius: '100px',
  padding: '4px 8px 4px 12px',
  lineHeight: 1.4,
};

const chipBtnStyle = {
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  color: '#b84012',
  fontSize: '0.7rem',
  opacity: 0.7,
  padding: '0 2px',
  lineHeight: 1,
  display: 'flex',
  alignItems: 'center',
};

export function FilterBar({
  intervencions,
  lang,
  labels,
  temes_labels,
  cat_labels,
  sub_labels,
  tipus_labels,
  mandats_labels,
  plens_path,
  entitats_path,
  pageTitle,
}: Props) {
  const [query, setQuery]         = useState(() => getParam('q'));
  const [categoria, setCategoria] = useState(() => getParam('cat'));
  const [subcategoria, setSubcategoria] = useState(() => getParam('sub'));
  const [districte, setDistricte] = useState(() => getParam('dist'));
  const [tipus, setTipus]         = useState(() => getParam('tipus'));
  const [mandat, setMandat]       = useState(() => getParam('mandat'));
  const [any, setAny]             = useState(() => getParam('any'));

  // Sync filters → URL (replaceState, no history spam)
  useEffect(() => {
    const p = new URLSearchParams();
    if (query)      p.set('q', query);
    if (categoria)  p.set('cat', categoria);
    if (subcategoria) p.set('sub', subcategoria);
    if (districte)  p.set('dist', districte);
    if (tipus)      p.set('tipus', tipus);
    if (mandat)     p.set('mandat', mandat);
    if (any)        p.set('any', any);
    const qs = p.toString();
    history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname);
  }, [query, categoria, subcategoria, districte, tipus, mandat, any]);

  const clearAll = () => {
    setQuery(''); setCategoria(''); setSubcategoria('');
    setDistricte(''); setTipus(''); setMandat(''); setAny('');
  };

  // Available primary categories
  const allCategories = useMemo(() => {
    const set = new Set<string>();
    for (const iv of intervencions) {
      const tv2 = iv.temes_v2 || {};
      for (const cat of Object.keys(tv2)) set.add(cat);
    }
    return [...set].sort();
  }, [intervencions]);

  // Available subcategories (filtered by selected category)
  const allSubcategories = useMemo(() => {
    if (!categoria) return [];
    const set = new Set<string>();
    for (const iv of intervencions) {
      const subs = (iv.temes_v2 || {})[categoria] || [];
      for (const s of subs) set.add(s);
    }
    return [...set].sort();
  }, [intervencions, categoria]);

  // Available districtes
  const allDistrictes = useMemo(() => {
    const set = new Set<string>();
    for (const iv of intervencions) {
      for (const d of iv.districtes || []) set.add(d);
    }
    return [...set].sort();
  }, [intervencions]);

  const allTipus = useMemo(() => {
    const set = new Set<string>();
    for (const iv of intervencions) set.add(iv.tipus_entitat);
    return [...set].sort();
  }, [intervencions]);

  const allMandats = useMemo(() => {
    const set = new Set<string>();
    for (const iv of intervencions) if (iv.mandat_id) set.add(iv.mandat_id);
    return [...set].sort().reverse();
  }, [intervencions]);

  const allAnys = useMemo(() => {
    const set = new Set<string>();
    for (const iv of intervencions) set.add(iv.fecha.slice(0, 4));
    return [...set].sort().reverse();
  }, [intervencions]);

  const filtered = useMemo(() => {
    const q = norm(query);
    return intervencions.filter((iv) => {
      if (q) {
        const haystack =
          norm(iv.entitat) + ' ' +
          norm(iv.intervinient) + ' ' +
          norm(iv.resum_cas) + ' ' +
          norm(iv.resum_val) + ' ' +
          norm(iv.text_cas) + ' ' +
          norm(iv.text_val);
        if (!haystack.includes(q)) return false;
      }
      if (categoria) {
        const tv2 = iv.temes_v2 || {};
        if (!(categoria in tv2)) return false;
        if (subcategoria && !(tv2[categoria] || []).includes(subcategoria)) return false;
      }
      if (districte && !(iv.districtes || []).includes(districte)) return false;
      if (tipus && iv.tipus_entitat !== tipus) return false;
      if (mandat && iv.mandat_id !== mandat) return false;
      if (any && !iv.fecha.startsWith(any)) return false;
      return true;
    });
  }, [intervencions, query, categoria, subcategoria, districte, tipus, mandat, any]);

  const hasFilters = query || categoria || districte || tipus || mandat || any;

  const cardLabels = {
    idioma_valenciano: labels.idioma_valenciano,
    idioma_castellano: labels.idioma_castellano,
    idioma_mixt: labels.idioma_mixt,
    ver_texto: labels.ver_texto,
    ocultar_texto: labels.ocultar_texto,
    traduccion: labels.traduccion,
    original: labels.original,
    punts: labels.punts,
    en_representacio: labels.en_representacio,
    ambit_labels: labels.ambit_labels,
  };

  return (
    <div>
      {/* Page header with counter */}
      <div class="flex items-baseline justify-between mb-6">
        {pageTitle && (
          <h1 class="text-2xl font-bold text-stone-900">{pageTitle}</h1>
        )}
        <span class="text-sm text-stone-600" style="font-family: 'Sora', system-ui, sans-serif; font-weight: 700; letter-spacing: -0.02em;">
          {filtered.length}<span style="color: #aaa; font-weight: 400;"> / {intervencions.length}</span>
        </span>
      </div>

      {/* Search input */}
      <div style={{ position: 'relative', marginBottom: '1rem' }}>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18" height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke={query ? '#e8562a' : '#aaa'}
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          style={{ position: 'absolute', left: '16px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', transition: 'stroke 0.15s' }}
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          type="search"
          value={query}
          onInput={(e) => setQuery((e.target as HTMLInputElement).value)}
          placeholder={lang === 'cas' ? 'Buscar por entidad, persona o palabra clave...' : 'Cerca per entitat, persona o paraula clau...'}
          aria-label={lang === 'cas' ? 'Buscar intervenciones' : 'Cercar intervencions'}
          style={{
            width: '100%',
            boxSizing: 'border-box',
            fontFamily: "'Outfit', system-ui, sans-serif",
            fontSize: '1rem',
            color: '#1e1e1e',
            background: '#fff',
            border: `1.5px solid ${query ? '#e8562a' : '#ddd'}`,
            borderRadius: '12px',
            padding: '13px 44px 13px 48px',
            outline: 'none',
            boxShadow: query ? '0 0 0 3px rgba(232,86,42,0.1)' : '0 1px 4px rgba(0,0,0,0.05)',
            transition: 'border-color 0.15s, box-shadow 0.15s',
          }}
        />
        {query && (
          <button
            onClick={() => setQuery('')}
            aria-label={lang === 'cas' ? 'Limpiar búsqueda' : 'Netejar cerca'}
            style={{
              position: 'absolute',
              right: '14px',
              top: '50%',
              transform: 'translateY(-50%)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: '#999',
              fontSize: '1rem',
              lineHeight: 1,
              padding: '4px',
            }}
          >
            ✕
          </button>
        )}
      </div>

      {/* Filter controls */}
      <fieldset class="flex flex-wrap gap-3" style="border: none; padding: 0; margin: 0 0 0.75rem 0;">
        <legend class="sr-only">{lang === 'cas' ? 'Filtrar intervenciones' : 'Filtrar intervencions'}</legend>

        <label class="sr-only" for="filter-categoria">{labels.filter_tema}</label>
        <select
          id="filter-categoria"
          aria-label={labels.filter_tema}
          value={categoria}
          onChange={(e) => { setCategoria((e.target as HTMLSelectElement).value); setSubcategoria(''); }}
          style={categoria ? selectActive : selectBase}
          class="focus:outline-2 focus:outline-offset-2 focus:outline-orange-500"
        >
          <option value="">{labels.filter_tema}: {labels.filter_todos}</option>
          {allCategories.map((c) => (
            <option key={c} value={c}>
              {cat_labels[c] ?? c}
            </option>
          ))}
        </select>

        {categoria && allSubcategories.length > 0 && (
          <>
            <label class="sr-only" for="filter-subcategoria">Subcategoria</label>
            <select
              id="filter-subcategoria"
              aria-label="Subcategoria"
              value={subcategoria}
              onChange={(e) => setSubcategoria((e.target as HTMLSelectElement).value)}
              style={subcategoria ? selectActive : selectBase}
              class="focus:outline-2 focus:outline-offset-2 focus:outline-orange-500"
            >
              <option value="">{labels.filter_todos}</option>
              {allSubcategories.map((s) => (
                <option key={s} value={s}>
                  {sub_labels[s] ?? s}
                </option>
              ))}
            </select>
          </>
        )}

        <label class="sr-only" for="filter-districte">{lang === 'cas' ? 'Distrito' : 'Districte'}</label>
        <select
          id="filter-districte"
          aria-label={lang === 'cas' ? 'Distrito' : 'Districte'}
          value={districte}
          onChange={(e) => setDistricte((e.target as HTMLSelectElement).value)}
          style={districte ? selectActive : selectBase}
          class="focus:outline-2 focus:outline-offset-2 focus:outline-orange-500"
        >
          <option value="">{lang === 'cas' ? 'Distrito' : 'Districte'}: {labels.filter_todos}</option>
          {allDistrictes.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <label class="sr-only" for="filter-tipus">{labels.filter_tipus}</label>
        <select
          id="filter-tipus"
          aria-label={labels.filter_tipus}
          value={tipus}
          onChange={(e) => setTipus((e.target as HTMLSelectElement).value)}
          style={tipus ? selectActive : selectBase}
          class="focus:outline-2 focus:outline-offset-2 focus:outline-orange-500"
        >
          <option value="">{labels.filter_tipus}: {labels.filter_todos}</option>
          {allTipus.map((tp) => (
            <option key={tp} value={tp}>
              {tipus_labels[tp] ?? tp}
            </option>
          ))}
        </select>

        <label class="sr-only" for="filter-mandat">{labels.filter_mandat}</label>
        <select
          id="filter-mandat"
          aria-label={labels.filter_mandat}
          value={mandat}
          onChange={(e) => setMandat((e.target as HTMLSelectElement).value)}
          style={mandat ? selectActive : selectBase}
          class="focus:outline-2 focus:outline-offset-2 focus:outline-orange-500"
        >
          <option value="">{labels.filter_mandat}: {labels.filter_todos}</option>
          {allMandats.map((m) => (
            <option key={m} value={m}>
              {mandats_labels[m] ?? m}
            </option>
          ))}
        </select>

        <label class="sr-only" for="filter-any">{labels.filter_any}</label>
        <select
          id="filter-any"
          aria-label={labels.filter_any}
          value={any}
          onChange={(e) => setAny((e.target as HTMLSelectElement).value)}
          style={any ? selectActive : selectBase}
          class="focus:outline-2 focus:outline-offset-2 focus:outline-orange-500"
        >
          <option value="">{labels.filter_any}: {labels.filter_todos}</option>
          {allAnys.map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </fieldset>

      {/* Active filter chips */}
      {hasFilters && (
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px', padding: '0.625rem 0 1.25rem', borderBottom: '1px solid #eee', marginBottom: '2rem' }}>
          {query && (
            <span style={chipStyle}>
              {lang === 'cas' ? 'Búsqueda' : 'Cerca'}: «{query}»
              <button style={chipBtnStyle} onClick={() => setQuery('')} aria-label={lang === 'cas' ? 'Quitar filtro de búsqueda' : 'Treure filtre de cerca'}>✕</button>
            </span>
          )}
          {categoria && (
            <span style={chipStyle}>
              {cat_labels[categoria] ?? categoria}
              <button style={chipBtnStyle} onClick={() => { setCategoria(''); setSubcategoria(''); }} aria-label={lang === 'cas' ? 'Quitar filtro de tema' : 'Treure filtre de tema'}>✕</button>
            </span>
          )}
          {subcategoria && (
            <span style={chipStyle}>
              {sub_labels[subcategoria] ?? subcategoria}
              <button style={chipBtnStyle} onClick={() => setSubcategoria('')} aria-label={lang === 'cas' ? 'Quitar subtema' : 'Treure subtema'}>✕</button>
            </span>
          )}
          {districte && (
            <span style={chipStyle}>
              {districte}
              <button style={chipBtnStyle} onClick={() => setDistricte('')} aria-label={lang === 'cas' ? 'Quitar filtro de distrito' : 'Treure filtre de districte'}>✕</button>
            </span>
          )}
          {tipus && (
            <span style={chipStyle}>
              {tipus_labels[tipus] ?? tipus}
              <button style={chipBtnStyle} onClick={() => setTipus('')} aria-label={lang === 'cas' ? 'Quitar filtro de tipo' : 'Treure filtre de tipus'}>✕</button>
            </span>
          )}
          {mandat && (
            <span style={chipStyle}>
              {mandat}
              <button style={chipBtnStyle} onClick={() => setMandat('')} aria-label={lang === 'cas' ? 'Quitar filtro de mandato' : 'Treure filtre de mandat'}>✕</button>
            </span>
          )}
          {any && (
            <span style={chipStyle}>
              {any}
              <button style={chipBtnStyle} onClick={() => setAny('')} aria-label={lang === 'cas' ? 'Quitar filtro de año' : 'Treure filtre de any'}>✕</button>
            </span>
          )}
          <button
            onClick={clearAll}
            style={{
              fontFamily: "'Outfit', system-ui, sans-serif",
              fontSize: '0.8125rem',
              fontWeight: '500',
              color: '#888',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '4px 4px',
              textDecoration: 'underline',
              textUnderlineOffset: '2px',
            }}
          >
            {labels.filter_reset}
          </button>
        </div>
      )}

      {/* No chips shown: still need the separator */}
      {!hasFilters && (
        <div style={{ borderBottom: '1px solid #eee', marginBottom: '2rem' }} />
      )}

      {/* Results */}
      <div class="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
        {filtered.map((iv) => (
          <InterventionCard
            key={iv.id}
            iv={iv}
            lang={lang}
            showDate={true}
            labels={cardLabels}
            temes_labels={temes_labels}
            cat_labels={cat_labels}
            sub_labels={sub_labels}
            tipus_labels={tipus_labels}
            plens_path={plens_path}
            entitats_path={entitats_path}
          />
        ))}
      </div>

      {filtered.length === 0 && (
        <p class="text-center text-stone-500 py-16">
          {labels.filter_reset}
        </p>
      )}
    </div>
  );
}
