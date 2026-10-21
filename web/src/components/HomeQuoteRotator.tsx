import { useState, useEffect } from 'preact/hooks';

export interface QuoteItem {
  text: string;
  text_val?: string | null;
  entity: string;
  location: string;
  year: string;
}

interface Props {
  quotesPool: QuoteItem[];
  lang: 'cas' | 'val';
}

function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export function HomeQuoteRotator({ quotesPool, lang }: Props) {
  // Start with first 8 (SSR-safe), randomize on mount
  const [quotes, setQuotes] = useState<QuoteItem[]>(quotesPool.slice(0, 8));
  const [idx, setIdx] = useState(0);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const picked = shuffle(quotesPool).slice(0, 8);
    setQuotes(picked);
    setIdx(0);
  }, []);

  const goTo = (i: number) => {
    if (i === idx) return;
    setFading(true);
    setTimeout(() => { setIdx(i); setFading(false); }, 280);
  };

  useEffect(() => {
    if (quotes.length === 0) return;
    const timer = setInterval(() => {
      setFading(true);
      setTimeout(() => { setIdx(i => (i + 1) % quotes.length); setFading(false); }, 280);
    }, 5500);
    return () => clearInterval(timer);
  }, [quotes.length]);

  if (quotes.length === 0) return <div style={{ minHeight: '7.5rem' }} />;

  const q = quotes[idx];
  const displayText = lang === 'val' && q.text_val ? q.text_val : q.text;

  return (
    <div style={{ marginBottom: '2.5rem' }}>
      <div style={{ minHeight: '7.5rem', transition: 'opacity 0.28s ease', opacity: fading ? 0 : 1 }}>
        <p style={{
          fontFamily: "'Sora', system-ui, sans-serif",
          fontSize: 'clamp(1.05rem, 2.8vw, 1.45rem)',
          fontWeight: 600,
          fontStyle: 'italic',
          color: '#e8e8e8',
          lineHeight: 1.4,
          letterSpacing: '-0.02em',
          marginBottom: '0.7rem',
          maxWidth: '34rem',
        }}>
          "{displayText}"
        </p>
        <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontFamily: "'Outfit', system-ui, sans-serif", fontSize: '0.78rem', color: '#e8562a', fontWeight: 600 }}>{q.entity}</span>
          {q.location && (
            <>
              <span style={{ color: '#555', fontSize: '0.75rem' }}>·</span>
              <span style={{ color: '#777', fontSize: '0.78rem' }}>{q.location}</span>
            </>
          )}
          <span style={{ color: '#555', fontSize: '0.75rem' }}>·</span>
          <span style={{ color: '#777', fontSize: '0.78rem' }}>{q.year}</span>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '0.35rem', marginTop: '1.1rem', alignItems: 'center' }}>
        {quotes.map((_, i) => (
          <button
            key={i}
            onClick={() => goTo(i)}
            style={{
              width: i === idx ? '1.25rem' : '0.375rem',
              height: '0.375rem',
              borderRadius: '100px',
              background: i === idx ? '#e8562a' : '#3a3a3a',
              border: 'none',
              cursor: 'pointer',
              padding: 0,
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
            }}
            aria-label={`Voice ${i + 1}`}
          />
        ))}
      </div>
    </div>
  );
}
