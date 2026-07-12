import { useState, useEffect, useRef } from 'preact/hooks';

function renderBoldMarkup(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} style="font-weight: 600; color: #1e1e1e;">{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function FormattedText({ text }: { text: string }) {
  if (!text) return <p style="color: #999; font-style: italic; font-size: 0.875rem;">Texto no disponible.</p>;

  const speakerRe = /^(Sr\.|Sra\.|Sr |Sra ).+:$/;
  const paragraphs = text.split('\n').filter((line) => line.trim() !== '');

  return (
    <div style="font-size: 1rem; line-height: 1.9; color: #44403c; max-width: 40rem;">
      {paragraphs.map((line, i) => {
        const trimmed = line.trim();
        if (speakerRe.test(trimmed)) {
          return (
            <p key={i} style="font-weight: 600; color: #1e1e1e; margin-top: 1.5rem; margin-bottom: 0.25rem; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.03em;">
              {trimmed}
            </p>
          );
        }
        return (
          <p key={i} style="margin-bottom: 0.85rem;">
            {renderBoldMarkup(trimmed)}
          </p>
        );
      })}
    </div>
  );
}

function formatLocation(iv: { zones: string[]; districtes: string[]; ambit: string }, labels: { ambit_labels?: Record<string, string> }): string {
  if (iv.zones && iv.zones.length > 0) {
    // Show "barrio, distrito" for each zone paired with its district
    if (iv.districtes && iv.districtes.length === 1) {
      // Single district: "Barrio1, Barrio2, Distrito"
      return iv.zones.join(', ') + ', ' + iv.districtes[0];
    }
    // Multiple districts or no district: just zones
    return iv.zones.join(', ');
  }
  if (iv.districtes && iv.districtes.length > 0) {
    return iv.districtes.join(', ');
  }
  return labels.ambit_labels?.[iv.ambit] ?? iv.ambit;
}

interface Intervention {
  id: string;
  pleno_id: string;
  fecha: string;
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
  iv: Intervention;
  lang: 'cas' | 'val';
  showDate?: boolean;
  labels: {
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
  plens_path: string;
  entitats_path: string;
}

const TEMA_STYLE: Record<string, string> = {
  urbanisme:        'background:#dbeafe;color:#1e40af',
  mobilitat:        'background:#ccfbf1;color:#115e59',
  medi_ambient:     'background:#d1fae5;color:#065f46',
  serveis_publics:  'background:#e0e7ff;color:#3730a3',
  economia:         'background:#fef3c7;color:#92400e',
  drets_i_igualtat: 'background:#ffe4e6;color:#9f1239',
  persones:         'background:#f3e8ff;color:#7e22ce',
  cultura:          'background:#ffedd5;color:#9a3412',
  participacio:     'background:#e0f2fe;color:#075985',
};
const TEMA_DEFAULT = 'background:#f0f0f0;color:#555';
const GEO_STYLE    = 'background:#f1f5f9;color:#64748b';

const TIPUS_BADGE: Record<string, string> = {
  av: 'bg-blue-100 text-blue-800',
  plataforma: 'bg-purple-100 text-purple-800',
  ong: 'bg-green-100 text-green-800',
  sindical: 'bg-yellow-100 text-yellow-800',
  cultural: 'bg-amber-100 text-amber-800',
  educacio: 'bg-teal-100 text-teal-800',
  esportiu: 'bg-orange-100 text-orange-800',
  empresa: 'bg-slate-100 text-slate-800',
  particular: 'bg-stone-100 text-stone-700',
  altres: 'bg-stone-100 text-stone-700',
};

const IDIOMA_ICON: Record<string, string> = {
  valenciano: '🟠',
  castellano: '🔵',
  mixt: '🟡',
};

import { formatIntervinient, formatFecha } from '../utils/format';

export function TextModal({
  iv,
  lang,
  labels,
  temes_labels,
  onClose,
}: {
  iv: Intervention;
  lang: 'cas' | 'val';
  labels: Props['labels'];
  temes_labels: Record<string, string>;
  onClose: () => void;
}) {
  const [showTranslation, setShowTranslation] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  const text = lang === 'cas' ? iv.text_cas : iv.text_val;
  const textOther = lang === 'cas' ? iv.text_val : iv.text_cas;
  const needsTranslation =
    (lang === 'cas' && iv.idioma_original === 'valenciano') ||
    (lang === 'val' && iv.idioma_original === 'castellano');
  const idiomaLabel =
    iv.idioma_original === 'valenciano'
      ? labels.idioma_valenciano
      : iv.idioma_original === 'castellano'
      ? labels.idioma_castellano
      : labels.idioma_mixt;

  useEffect(() => {
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = '';
      document.removeEventListener('keydown', onKey);
    };
  }, []);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${iv.intervinient} — ${iv.entitat}`}
      style="position: fixed; inset: 0; z-index: 9999; display: flex; align-items: center; justify-content: center;"
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        style="position: absolute; inset: 0; background: rgba(0,0,0,0.5); backdrop-filter: blur(2px);"
      />

      {/* Panel */}
      <style>{`.iv-modal-panel { position: relative; background: #fff; display: flex; flex-direction: column; overflow: hidden; width: 100%; height: 100%; } @media (min-width: 768px) { .iv-modal-panel { max-width: 42rem; max-height: 92vh; border-radius: 16px; margin: 0 1rem; } }`}</style>
      <div class="iv-modal-panel">
        {/* Header */}
        <div style="padding: 1.25rem 1.5rem; border-bottom: 1px solid #eee; flex-shrink: 0;">
          <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem;">
            <div style="min-width: 0; flex: 1;">
              <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.35rem;">
                <span style="font-size: 0.75rem; font-weight: 600; color: #b83a14; background: #fef1ec; padding: 1px 8px; border-radius: 100px; white-space: nowrap;">{iv.fecha}</span>
                <span style="font-size: 0.75rem; color: #999;" role="img" aria-label={idiomaLabel}>{IDIOMA_ICON[iv.idioma_original]}</span>
              </div>
              <h2 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.15rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 0.15rem;">
                {formatIntervinient(iv.intervinient, lang)}
              </h2>
              <p style="font-size: 0.875rem; color: #666;">{iv.entitat}</p>
              {iv.ambit && iv.ambit !== 'no_especificat' && (
                <p style="font-size: 0.75rem; color: #999; margin-top: 0.2rem;">
                  <span aria-hidden="true">📍</span>{' '}
                  {formatLocation(iv, labels)}
                </p>
              )}
            </div>
            <button
              ref={closeRef}
              onClick={onClose}
              aria-label={lang === 'cas' ? 'Cerrar' : 'Tancar'}
              style="flex-shrink: 0; width: 36px; height: 36px; border-radius: 100px; border: 1px solid #eee; background: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; color: #999; transition: all 0.15s;"
              class="hover:text-stone-900 hover:border-stone-300 focus:outline-2 focus:outline-offset-2 focus:outline-orange-500"
            >
              ✕
            </button>
          </div>
          {/* Themes */}
          {iv.temes.length > 0 && (
            <div style="display: flex; flex-wrap: wrap; gap: 0.25rem; margin-top: 0.75rem;">
              {iv.temes.map((tema) => (
                <span key={tema} style="font-size: 0.7rem; padding: 1px 8px; background: #f5f5f5; color: #666; border-radius: 100px;">
                  {temes_labels[tema] ?? tema}
                </span>
              ))}
            </div>
          )}
          {/* Translation toggle */}
          {needsTranslation && (
            <div style="display: flex; gap: 0.75rem; margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #f5f5f5;">
              <button
                onClick={() => setShowTranslation(false)}
                style={{
                  fontSize: '0.75rem',
                  fontWeight: !showTranslation ? '600' : '400',
                  color: !showTranslation ? '#e8562a' : '#999',
                  background: 'none',
                  border: 'none',
                  borderBottom: !showTranslation ? '2px solid #e8562a' : '2px solid transparent',
                  paddingBottom: '2px',
                  cursor: 'pointer',
                }}
                class="focus:outline-2 focus:outline-offset-2 focus:outline-orange-500"
              >
                <span lang={lang === 'cas' ? 'es' : 'ca'}>{lang === 'cas' ? 'Castellano' : 'Valencià'}</span>
              </button>
              <button
                onClick={() => setShowTranslation(true)}
                style={{
                  fontSize: '0.75rem',
                  fontWeight: showTranslation ? '600' : '400',
                  color: showTranslation ? '#e8562a' : '#999',
                  background: 'none',
                  border: 'none',
                  borderBottom: showTranslation ? '2px solid #e8562a' : '2px solid transparent',
                  paddingBottom: '2px',
                  cursor: 'pointer',
                }}
                class="focus:outline-2 focus:outline-offset-2 focus:outline-orange-500"
              >
                {labels.original} ({iv.idioma_original})
              </button>
            </div>
          )}
        </div>

        {/* Body — scrollable */}
        <div style="flex: 1; overflow-y: auto; padding: 1.5rem; padding-bottom: 3rem;">
          <FormattedText text={needsTranslation && showTranslation ? textOther : text} />
        </div>
      </div>
    </div>
  );
}

export function InterventionCard({
  iv,
  lang,
  showDate = false,
  labels,
  temes_labels,
  cat_labels,
  sub_labels,
  tipus_labels,
  plens_path,
  entitats_path,
}: Props) {
  const [modalOpen, setModalOpen] = useState(false);

  const resum = lang === 'cas' ? iv.resum_cas : iv.resum_val;
  const badgeClass = TIPUS_BADGE[iv.tipus_entitat] ?? TIPUS_BADGE.altres;
  const cats = Object.keys(iv.temes_v2 || {});
  const hasGeo = iv.ambit && iv.ambit !== 'no_especificat';

  return (
    <>
      <article class="bg-white rounded-xl border border-stone-200 p-5 shadow-sm hover:shadow-md transition-shadow flex flex-col">

        {/* (0) Tipo badge */}
        <div class="mb-2">
          <span class={`text-xs px-2 py-0.5 rounded-full font-medium ${badgeClass}`}>
            {tipus_labels[iv.tipus_entitat] ?? iv.tipus_entitat}
          </span>
        </div>

        {/* (1) Entitat — primary heading */}
        <h3 class="font-semibold text-stone-900 leading-snug mb-2.5">
          <a
            href={`${entitats_path}${iv.entitat_id}/`}
            class="hover:text-orange-600 transition-colors"
          >
            {iv.entitat}
          </a>
        </h3>

        {/* (2) Resumen — main body, most prominent */}
        <p class="text-sm text-stone-700 leading-relaxed mb-3 flex-1">{resum}</p>

        {/* (3a) Tema tags — one colour per category */}
        {cats.length > 0 && (
          <div class="flex flex-wrap gap-1 mb-1.5">
            {cats.map((cat) => (
              <span key={cat} class="text-xs px-2 py-0.5 rounded-full font-medium" style={TEMA_STYLE[cat] ?? TEMA_DEFAULT}>
                {cat_labels[cat] ?? cat}
              </span>
            ))}
          </div>
        )}

        {/* (3b) Geo tags — each zone/district as its own badge */}
        {hasGeo && (
          <div class="flex flex-wrap gap-1 mb-3">
            {iv.zones?.length > 0
              ? iv.zones.map((z) => (
                  <span key={z} class="text-xs px-2 py-0.5 rounded-full" style={GEO_STYLE}>📍 {z}</span>
                ))
              : iv.districtes?.length > 0
              ? iv.districtes.map((d) => (
                  <span key={d} class="text-xs px-2 py-0.5 rounded-full" style={GEO_STYLE}>📍 {d}</span>
                ))
              : (
                  <span class="text-xs px-2 py-0.5 rounded-full" style={GEO_STYLE}>
                    📍 {labels.ambit_labels?.[iv.ambit] ?? iv.ambit}
                  </span>
                )
            }
          </div>
        )}

        {/* spacer when there are tema tags but no geo */}
        {cats.length > 0 && !hasGeo && <div class="mb-3" />}

        {/* (4) Footer — speaker · date + ver texto */}
        <div class="flex items-center justify-between gap-3 pt-2.5 border-t border-stone-100">
          <div class="min-w-0 flex-1">
            <p class="text-xs text-stone-500 truncate">
              {formatIntervinient(iv.intervinient, lang)}
              {showDate && (
                <> · <a href={`${plens_path}${iv.pleno_id}/`} class="hover:text-orange-600 transition-colors">{formatFecha(iv.fecha, lang)}</a></>
              )}
            </p>
          </div>
          <button
            onClick={() => setModalOpen(true)}
            class="text-xs font-medium text-orange-600 hover:text-orange-700 focus:outline-2 focus:outline-offset-2 focus:outline-orange-500 transition-colors shrink-0"
          >
            {labels.ver_texto} <span aria-hidden="true">→</span>
          </button>
        </div>
      </article>

      {/* Modal */}
      {modalOpen && (
        <TextModal
          iv={iv}
          lang={lang}
          labels={labels}
          temes_labels={temes_labels}
          onClose={() => setModalOpen(false)}
        />
      )}
    </>
  );
}
