import { useState, useEffect, useRef } from 'preact/hooks';

interface MandateData {
  range: string;
  alcalde: string;
  count: number;
}

interface Props {
  mandates: MandateData[];
  lang: 'cas' | 'val';
}

export function HomeMandateChart({ mandates, lang }: Props) {
  const [animated, setAnimated] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const max = Math.max(...mandates.map(m => m.count));

  useEffect(() => {
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setAnimated(true); obs.disconnect(); } },
      { threshold: 0.25 }
    );
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);

  return (
    <div ref={ref} style={{ display: 'grid', gap: '1.1rem' }}>
      {mandates.map(({ range, alcalde, count }, i) => {
        const pct = (count / max) * 100;
        const isLatest = i === mandates.length - 1;

        return (
          <div
            key={range}
            style={{
              display: 'grid',
              gridTemplateColumns: '8.5rem 1fr 3rem',
              alignItems: 'center',
              gap: '1rem',
            }}
          >
            <div style={{ textAlign: 'right' }}>
              <span style={{
                fontFamily: "'Sora', system-ui, sans-serif",
                fontSize: '0.8rem',
                fontWeight: isLatest ? 700 : 500,
                color: isLatest ? '#1e1e1e' : '#777',
                display: 'block',
                letterSpacing: '-0.01em',
              }}>{range}</span>
              <span style={{
                fontFamily: "'Outfit', system-ui, sans-serif",
                fontSize: '0.68rem',
                color: '#aaa',
                display: 'block',
              }}>{alcalde}</span>
            </div>

            <div style={{
              height: isLatest ? '14px' : '9px',
              background: '#f0f0f0',
              borderRadius: '100px',
              overflow: 'hidden',
            }}>
              <div style={{
                height: '100%',
                borderRadius: '100px',
                background: isLatest ? '#e8562a' : '#1e1e1e',
                width: animated ? `${pct}%` : '0%',
                opacity: isLatest ? 1 : 0.2 + (i / (mandates.length - 1)) * 0.45,
                transition: `width 1.1s cubic-bezier(0.4, 0, 0.2, 1) ${i * 0.18}s`,
              }} />
            </div>

            <span style={{
              fontFamily: "'Sora', system-ui, sans-serif",
              fontSize: isLatest ? '1.1rem' : '0.88rem',
              fontWeight: isLatest ? 800 : 600,
              color: isLatest ? '#e8562a' : '#666',
              letterSpacing: '-0.03em',
              textAlign: 'right',
            }}>{count}</span>
          </div>
        );
      })}
    </div>
  );
}
