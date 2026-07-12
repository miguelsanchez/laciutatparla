import { useState } from 'preact/hooks';

interface Subcategory {
  key: string;
  label: string;
  count: number;
}

interface Category {
  key: string;
  label: string;
  count: number;
  subcategories: Subcategory[];
}

interface Props {
  categories: Category[];
  lang: 'cas' | 'val';
}

const CAT_COLORS: Record<string, { bg: string; glow: string; light: string }> = {
  urbanisme:        { bg: '#e8562a', glow: '#e8562a', light: '#fef1ec' },
  mobilitat:        { bg: '#1e3a5f', glow: '#2a5080', light: '#eef3f9' },
  medi_ambient:     { bg: '#2d6a4f', glow: '#3a8a65', light: '#eef6f1' },
  serveis_publics:  { bg: '#4a3520', glow: '#6b4e2e', light: '#f5f0eb' },
  economia:         { bg: '#5c1e3a', glow: '#7a2850', light: '#f5edf2' },
  drets_i_igualtat: { bg: '#3a1e5c', glow: '#502880', light: '#f0edf6' },
  persones:         { bg: '#1e4a5c', glow: '#286880', light: '#edf4f6' },
  cultura:          { bg: '#5c3a1e', glow: '#7a5028', light: '#f5f0ea' },
  participacio:     { bg: '#1e5c2d', glow: '#287a3a', light: '#edf5ef' },
};

export function HomeThemeBubbles({ categories, lang }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const max = Math.max(...categories.map(c => c.count));

  const handleBubbleClick = (key: string) => {
    setSelected(prev => (prev === key ? null : key));
  };

  const selectedCat = categories.find(c => c.key === selected);
  const selectedColors = selected ? (CAT_COLORS[selected] ?? { bg: '#1e1e1e', glow: '#333', light: '#f5f5f5' }) : null;

  return (
    <div>
      {/* Bubble cluster */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '0.85rem',
        justifyContent: 'center',
        alignItems: 'center',
        padding: '0.5rem 0 1rem',
      }}>
        {categories.map(({ key, label, count }) => {
          const ratio = count / max;
          const size = Math.round(78 + ratio * 88);
          const isSelected = selected === key;
          const isDimmed = selected !== null && !isSelected;
          const { bg, glow } = CAT_COLORS[key] ?? { bg: '#1e1e1e', glow: '#333', light: '#f5f5f5' };

          return (
            <button
              key={key}
              onClick={() => handleBubbleClick(key)}
              style={{
                width: `${size}px`,
                height: `${size}px`,
                borderRadius: '50%',
                background: bg,
                border: isSelected ? '3px solid rgba(255,255,255,0.9)' : '3px solid transparent',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                padding: 0,
                transform: isSelected ? 'scale(1.12)' : isDimmed ? 'scale(0.88)' : 'scale(1)',
                opacity: isDimmed ? 0.28 : 1,
                transition: 'transform 0.28s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.25s ease, border-color 0.2s ease, box-shadow 0.25s ease',
                boxShadow: isSelected
                  ? `0 12px 40px ${glow}aa, 0 0 0 6px ${glow}22`
                  : '0 2px 10px rgba(0,0,0,0.18)',
              }}
              aria-expanded={isSelected}
              aria-label={`${label}: ${count} intervencions`}
            >
              <span style={{
                fontFamily: "'Sora', system-ui, sans-serif",
                fontSize: `${0.68 + ratio * 0.55}rem`,
                fontWeight: 800,
                color: '#fff',
                lineHeight: 1,
                letterSpacing: '-0.03em',
                pointerEvents: 'none',
              }}>{count}</span>
              <span style={{
                fontFamily: "'Outfit', system-ui, sans-serif",
                fontSize: `${Math.max(0.52, 0.55 + ratio * 0.1)}rem`,
                color: 'rgba(255,255,255,0.85)',
                textAlign: 'center',
                lineHeight: 1.25,
                marginTop: '0.2rem',
                maxWidth: '82%',
                pointerEvents: 'none',
              }}>{label}</span>
            </button>
          );
        })}
      </div>

      {/* Expansion panel */}
      <div style={{
        maxHeight: selected ? '500px' : '0px',
        opacity: selected ? 1 : 0,
        overflow: 'hidden',
        transition: 'max-height 0.45s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease',
      }}>
        {selectedCat && selectedColors && (
          <div style={{
            marginTop: '1.25rem',
            background: selectedColors.light,
            border: `1.5px solid ${selectedColors.bg}22`,
            borderRadius: '20px',
            padding: '1.5rem 1.75rem',
            position: 'relative',
          }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.1rem' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.75rem' }}>
                <span style={{
                  fontFamily: "'Sora', system-ui, sans-serif",
                  fontSize: '1.15rem',
                  fontWeight: 800,
                  color: selectedColors.bg,
                  letterSpacing: '-0.025em',
                }}>{selectedCat.label}</span>
                <span style={{
                  fontFamily: "'Sora', system-ui, sans-serif",
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  color: `${selectedColors.bg}99`,
                  letterSpacing: '-0.02em',
                }}>{selectedCat.count} {lang === 'cas' ? 'intervenciones' : 'intervencions'}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <a
                  href={`/${lang}/intervencions/?cat=${selectedCat.key}`}
                  style={{
                    fontFamily: "'Outfit', system-ui, sans-serif",
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    color: selectedColors.bg,
                    textDecoration: 'none',
                    borderBottom: `1px solid ${selectedColors.bg}44`,
                    paddingBottom: '1px',
                    transition: 'border-color 0.15s',
                  }}
                >
                  {lang === 'cas' ? 'Ver todas →' : 'Veure totes →'}
                </a>
                <button
                  onClick={() => setSelected(null)}
                  style={{
                    background: `${selectedColors.bg}18`,
                    border: 'none',
                    borderRadius: '50%',
                    width: '1.6rem',
                    height: '1.6rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    color: selectedColors.bg,
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    transition: 'background 0.15s',
                    flexShrink: 0,
                  }}
                  aria-label={lang === 'cas' ? 'Cerrar' : 'Tancar'}
                >✕</button>
              </div>
            </div>

            {/* Subcategory pills */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {selectedCat.subcategories.map(({ key, label, count }, i) => (
                <a
                  key={key}
                  href={`/${lang}/intervencions/?cat=${selectedCat.key}&sub=${key}`}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.4rem',
                    padding: '0.4rem 0.9rem 0.4rem 0.5rem',
                    background: '#fff',
                    border: `1.5px solid ${selectedColors.bg}28`,
                    borderRadius: '100px',
                    textDecoration: 'none',
                    color: '#1e1e1e',
                    fontFamily: "'Outfit', system-ui, sans-serif",
                    fontSize: '0.83rem',
                    fontWeight: 500,
                    transition: 'border-color 0.15s, background 0.15s, transform 0.15s',
                    animation: `pill-in 0.3s ease both`,
                    animationDelay: `${i * 0.04}s`,
                  }}
                  class="subtopic-pill"
                >
                  <span style={{
                    fontFamily: "'Sora', system-ui, sans-serif",
                    fontSize: '0.7rem',
                    fontWeight: 800,
                    color: selectedColors.bg,
                    background: `${selectedColors.bg}14`,
                    borderRadius: '100px',
                    padding: '1px 7px',
                    lineHeight: '1.6',
                    letterSpacing: '-0.02em',
                  }}>{count}</span>
                  {label}
                </a>
              ))}
            </div>
          </div>
        )}
      </div>

      <style>{`
        @keyframes pill-in {
          from { opacity: 0; transform: translateY(6px) scale(0.94); }
          to   { opacity: 1; transform: none; }
        }
        .subtopic-pill:hover {
          border-color: currentColor;
          background: #f8f8f8;
          transform: translateY(-1px);
        }
      `}</style>
    </div>
  );
}
