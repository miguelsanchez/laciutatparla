import { useState, useEffect, useRef, useCallback } from 'preact/hooks';

type IvLight = {
  id: string;
  entitat: string;
  entitat_id: string;
  intervinient: string;
  resum_cas: string;
  resum_val: string;
  fecha: string;
};

type Entitat = {
  id: string;
  nom_cas: string;
  nom_val: string;
  tipus: string;
  num_intervencions: number;
  variants: string[];
};

type Result =
  | { kind: 'iv'; item: IvLight }
  | { kind: 'entitat'; item: Entitat };

function norm(s: string) {
  return (s ?? '').toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '');
}

const MAX_IV = 6;
const MAX_ENT = 4;

interface Props {
  lang: 'cas' | 'val';
  intervencions_path: string;
  entitats_path: string;
}

export function GlobalSearch({ lang, intervencions_path, entitats_path }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Result[]>([]);
  const [selected, setSelected] = useState(0);
  const [data, setData] = useState<{ ivs: IvLight[]; entitats: Entitat[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const isCas = lang === 'cas';
  const placeholder = isCas ? 'Buscar intervenciones, entidades...' : 'Cercar intervencions, entitats...';
  const noResults = isCas ? 'Sin resultados' : 'Sense resultats';
  const lblIv = isCas ? 'Intervenciones' : 'Intervencions';
  const lblEnt = isCas ? 'Entidades' : 'Entitats';

  const loadData = useCallback(async () => {
    if (data || loading) return;
    setLoading(true);
    try {
      const [ivRes, entRes] = await Promise.all([
        fetch('/datos/intervencions_light.json').then((r) => r.json()),
        fetch('/datos/entitats.json').then((r) => r.json()),
      ]);
      setData({ ivs: ivRes, entitats: entRes });
    } finally {
      setLoading(false);
    }
  }, [data, loading]);

  const doOpen = useCallback(() => {
    setOpen(true);
    loadData();
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [loadData]);

  const doClose = useCallback(() => {
    setOpen(false);
    setQuery('');
    setResults([]);
    setSelected(0);
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        open ? doClose() : doOpen();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, doOpen, doClose]);

  useEffect(() => {
    if (!open || !data || !query.trim()) {
      setResults([]);
      setSelected(0);
      return;
    }
    const q = norm(query.trim());
    const matched: Result[] = [];

    for (const iv of data.ivs) {
      if (matched.filter((r) => r.kind === 'iv').length >= MAX_IV) break;
      const haystack = norm(
        [iv.entitat, iv.intervinient, iv.resum_cas, iv.resum_val].join(' ')
      );
      if (haystack.includes(q)) matched.push({ kind: 'iv', item: iv });
    }

    for (const ent of data.entitats) {
      if (matched.filter((r) => r.kind === 'entitat').length >= MAX_ENT) break;
      const haystack = norm([ent.nom_cas, ent.nom_val, ...(ent.variants ?? [])].join(' '));
      if (haystack.includes(q)) matched.push({ kind: 'entitat', item: ent });
    }

    setResults(matched);
    setSelected(0);
  }, [query, data, open]);

  const navigate = useCallback(
    (r: Result) => {
      if (r.kind === 'iv') {
        window.location.href = `${intervencions_path}${r.item.id}/`;
      } else {
        window.location.href = `${entitats_path}${r.item.id}/`;
      }
      doClose();
    },
    [intervencions_path, entitats_path, doClose]
  );

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') { doClose(); return; }
    if (!results.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelected((s) => Math.min(s + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelected((s) => Math.max(s - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      navigate(results[selected]);
    }
  };

  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelectorAll<HTMLElement>('[data-result]')[selected];
    el?.scrollIntoView({ block: 'nearest' });
  }, [selected]);

  const ivResults = results.filter((r): r is { kind: 'iv'; item: IvLight } => r.kind === 'iv');
  const entResults = results.filter((r): r is { kind: 'entitat'; item: Entitat } => r.kind === 'entitat');

  const allIndexed = [...ivResults.map((_, i) => i), ...entResults.map((_, i) => ivResults.length + i)];
  let globalIdx = 0;

  return (
    <>
      {/* Trigger button */}
      <button
        onClick={doOpen}
        aria-label={isCas ? 'Abrir búsqueda global (⌘K)' : 'Obrir cerca global (⌘K)'}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem',
          fontSize: '0.8125rem',
          color: '#888',
          background: '#f5f5f5',
          border: '1px solid #e5e5e5',
          borderRadius: '100px',
          padding: '5px 12px',
          cursor: 'pointer',
          transition: 'all 0.15s',
          fontFamily: "'Outfit', system-ui, sans-serif",
        }}
        class="hover:border-stone-300 hover:text-stone-700"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <span class="hidden md:inline">{isCas ? 'Buscar' : 'Cercar'}</span>
        <kbd class="hidden md:inline" style="font-size:0.7rem;opacity:0.6;font-family:monospace;">⌘K</kbd>
      </button>

      {/* Overlay */}
      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={isCas ? 'Búsqueda global' : 'Cerca global'}
          style="position:fixed;inset:0;z-index:99999;display:flex;align-items:flex-start;justify-content:center;padding-top:clamp(4rem,10vh,8rem);background:rgba(0,0,0,0.45);backdrop-filter:blur(2px);"
          onClick={(e) => { if (e.target === e.currentTarget) doClose(); }}
        >
          <div
            style="background:#fff;border-radius:16px;width:100%;max-width:580px;margin:0 1rem;box-shadow:0 20px 60px rgba(0,0,0,0.18);overflow:hidden;display:flex;flex-direction:column;max-height:70vh;"
          >
            {/* Search input row */}
            <div style="display:flex;align-items:center;gap:0.75rem;padding:1rem 1.25rem;border-bottom:1px solid #f0f0f0;">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#aaa" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex-shrink:0;">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              <input
                ref={inputRef}
                type="text"
                value={query}
                onInput={(e) => setQuery((e.target as HTMLInputElement).value)}
                onKeyDown={onKeyDown}
                placeholder={placeholder}
                style="flex:1;border:none;outline:none;font-size:1rem;font-family:'Outfit',system-ui,sans-serif;color:#1e1e1e;background:transparent;"
                aria-label={placeholder}
                aria-autocomplete="list"
                aria-activedescendant={results.length ? `gs-result-${selected}` : undefined}
                role="combobox"
                aria-expanded={results.length > 0}
                aria-controls="gs-listbox"
              />
              {query && (
                <button
                  onClick={() => { setQuery(''); inputRef.current?.focus(); }}
                  aria-label={isCas ? 'Limpiar' : 'Netejar'}
                  style="color:#aaa;background:none;border:none;cursor:pointer;padding:2px;font-size:1rem;line-height:1;"
                >✕</button>
              )}
              <button
                onClick={doClose}
                aria-label={isCas ? 'Cerrar' : 'Tancar'}
                style="font-size:0.75rem;color:#aaa;background:#f0f0f0;border:none;border-radius:6px;padding:3px 7px;cursor:pointer;"
              >Esc</button>
            </div>

            {/* Results */}
            <div id="gs-listbox" role="listbox" ref={listRef} style="overflow-y:auto;flex:1;">
              {loading && !data && (
                <p style="padding:1.5rem;text-align:center;color:#aaa;font-size:0.875rem;">
                  {isCas ? 'Cargando...' : 'Carregant...'}
                </p>
              )}

              {!query.trim() && !loading && (
                <p style="padding:1.5rem;text-align:center;color:#aaa;font-size:0.875rem;">
                  {isCas ? 'Escribe para buscar intervenciones y entidades' : 'Escriu per cercar intervencions i entitats'}
                </p>
              )}

              {query.trim() && results.length === 0 && !loading && (
                <p style="padding:1.5rem;text-align:center;color:#aaa;font-size:0.875rem;">{noResults}</p>
              )}

              {ivResults.length > 0 && (
                <div>
                  <p style="padding:0.6rem 1.25rem 0.3rem;font-size:0.7rem;font-weight:600;color:#aaa;text-transform:uppercase;letter-spacing:0.06em;">{lblIv}</p>
                  {ivResults.map((r, i) => {
                    const idx = i;
                    return (
                      <button
                        key={r.item.id}
                        id={`gs-result-${idx}`}
                        role="option"
                        aria-selected={selected === idx}
                        data-result
                        onClick={() => navigate(r)}
                        style={{
                          display: 'block',
                          width: '100%',
                          textAlign: 'left',
                          padding: '0.6rem 1.25rem',
                          border: 'none',
                          background: selected === idx ? '#fef8f5' : 'transparent',
                          borderLeft: selected === idx ? '3px solid #e8562a' : '3px solid transparent',
                          cursor: 'pointer',
                          transition: 'background 0.1s',
                        }}
                        onMouseEnter={() => setSelected(idx)}
                      >
                        <p style="font-size:0.875rem;font-weight:600;color:#1e1e1e;margin-bottom:0.1rem;line-height:1.3;">{r.item.entitat}</p>
                        <p style="font-size:0.75rem;color:#888;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                          {r.item.fecha} · {isCas ? (r.item.resum_cas ?? r.item.resum_val) : (r.item.resum_val ?? r.item.resum_cas)}
                        </p>
                      </button>
                    );
                  })}
                </div>
              )}

              {entResults.length > 0 && (
                <div style={ivResults.length > 0 ? 'border-top:1px solid #f5f5f5;' : ''}>
                  <p style="padding:0.6rem 1.25rem 0.3rem;font-size:0.7rem;font-weight:600;color:#aaa;text-transform:uppercase;letter-spacing:0.06em;">{lblEnt}</p>
                  {entResults.map((r, i) => {
                    const idx = ivResults.length + i;
                    return (
                      <button
                        key={r.item.id}
                        id={`gs-result-${idx}`}
                        role="option"
                        aria-selected={selected === idx}
                        data-result
                        onClick={() => navigate(r)}
                        style={{
                          display: 'block',
                          width: '100%',
                          textAlign: 'left',
                          padding: '0.6rem 1.25rem',
                          border: 'none',
                          background: selected === idx ? '#fef8f5' : 'transparent',
                          borderLeft: selected === idx ? '3px solid #e8562a' : '3px solid transparent',
                          cursor: 'pointer',
                          transition: 'background 0.1s',
                        }}
                        onMouseEnter={() => setSelected(idx)}
                      >
                        <p style="font-size:0.875rem;font-weight:600;color:#1e1e1e;margin-bottom:0.1rem;">{isCas ? r.item.nom_cas : r.item.nom_val}</p>
                        <p style="font-size:0.75rem;color:#888;">{r.item.num_intervencions} {isCas ? 'intervenciones' : 'intervencions'}</p>
                      </button>
                    );
                  })}
                </div>
              )}

              {results.length > 0 && (
                <div style="padding:0.5rem 1.25rem;border-top:1px solid #f5f5f5;">
                  <p style="font-size:0.7rem;color:#ccc;text-align:right;">↑↓ navegar · Enter abrir · Esc cerrar</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
