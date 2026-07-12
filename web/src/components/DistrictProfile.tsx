import { useState } from 'preact/hooks';

interface DistrictEntity {
  id: string;
  count: number;
  name_cas: string;
  name_val: string;
}

interface DistrictTopic {
  name: string;
  count: number;
}

interface Profile {
  quejas_top: DistrictTopic[];
  cats_top: DistrictTopic[];
  ents_top: DistrictEntity[];
}

interface Props {
  profiles: Record<string, Profile>;
  districtStats: Record<string, { quejas: number; intervencions: number; ratio: number }>;
  cat_labels: Record<string, string>;
  lang: 'cas' | 'val';
  entitats_path: string;
}

export function DistrictProfile({ profiles, districtStats, cat_labels, lang, entitats_path }: Props) {
  const districts = Object.keys(profiles).sort();
  const [selected, setSelected] = useState<string>('Poblats del Sud');

  const profile = profiles[selected];
  const stats = districtStats[selected];

  if (!profile) return null;

  return (
    <div>
      {/* District selector */}
      <div style="display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1.5rem;">
        {districts.map(d => {
          const isActive = d === selected;
          return (
            <button
              key={d}
              onClick={() => setSelected(d)}
              style={{
                fontFamily: "'Outfit', system-ui, sans-serif",
                fontSize: '0.75rem',
                fontWeight: isActive ? '600' : '400',
                color: isActive ? '#fff' : '#666',
                background: isActive ? '#1e1e1e' : '#fff',
                border: isActive ? 'none' : '1px solid #ddd',
                borderRadius: '100px',
                padding: '5px 12px',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {d}
            </button>
          );
        })}
      </div>

      {/* Stats header */}
      {stats && (
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin-bottom: 1.5rem;">
          <div style="background: #fef1ec; border-radius: 12px; padding: 1rem 1.25rem;">
            <span style="display: block; font-family: 'Sora', system-ui, sans-serif; font-size: 1.5rem; font-weight: 800; color: #e8562a; line-height: 1; letter-spacing: -0.03em;">{stats.quejas.toLocaleString('es-ES')}</span>
            <span style="display: block; font-size: 0.7rem; color: #666; margin-top: 3px; font-family: 'Outfit', system-ui, sans-serif;">{lang === 'cas' ? 'quejas' : 'queixes'}</span>
          </div>
          <div style="background: #f5f5f5; border-radius: 12px; padding: 1rem 1.25rem;">
            <span style="display: block; font-family: 'Sora', system-ui, sans-serif; font-size: 1.5rem; font-weight: 800; color: #1e1e1e; line-height: 1; letter-spacing: -0.03em;">{stats.intervencions}</span>
            <span style="display: block; font-size: 0.7rem; color: #666; margin-top: 3px; font-family: 'Outfit', system-ui, sans-serif;">{lang === 'cas' ? 'intervenciones' : 'intervencions'}</span>
          </div>
          <div style="background: #fff; border: 1px solid #eee; border-radius: 12px; padding: 1rem 1.25rem;">
            <span style="display: block; font-family: 'Sora', system-ui, sans-serif; font-size: 1.5rem; font-weight: 800; color: #1e1e1e; line-height: 1; letter-spacing: -0.03em;">{stats.ratio.toFixed(1)}‰</span>
            <span style="display: block; font-size: 0.7rem; color: #666; margin-top: 3px; font-family: 'Outfit', system-ui, sans-serif;">{lang === 'cas' ? 'ratio organización' : "ratio d'organització"}</span>
          </div>
        </div>
      )}

      {/* Three columns */}
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Quejas */}
        <div style="background: #fff; border: 1px solid #eee; border-radius: 12px; padding: 1rem 1.25rem;">
          <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.85rem; font-weight: 700; color: #e8562a; margin-bottom: 0.75rem;">
            ⚠️ {lang === 'cas' ? 'Top quejas' : 'Top queixes'}
          </h4>
          {profile.quejas_top.length === 0 ? (
            <p style="font-size: 0.8rem; color: #aaa; font-style: italic;">—</p>
          ) : (
            <div style="display: grid; gap: 0.5rem;">
              {profile.quejas_top.map(t => (
                <div key={t.name} style="display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.8rem;">
                  <span style="color: #1e1e1e; line-height: 1.3;">{t.name}</span>
                  <span style="color: #666; font-weight: 600; font-family: 'Sora', system-ui, sans-serif; flex-shrink: 0;">{t.count.toLocaleString('es-ES')}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Intervention categories */}
        <div style="background: #fff; border: 1px solid #eee; border-radius: 12px; padding: 1rem 1.25rem;">
          <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.85rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.75rem;">
            📣 {lang === 'cas' ? 'Temas del pleno' : 'Temes del ple'}
          </h4>
          {profile.cats_top.length === 0 ? (
            <p style="font-size: 0.8rem; color: #aaa; font-style: italic;">{lang === 'cas' ? 'Sin intervenciones' : 'Sense intervencions'}</p>
          ) : (
            <div style="display: grid; gap: 0.5rem;">
              {profile.cats_top.map(c => (
                <div key={c.name} style="display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.8rem;">
                  <span style="color: #1e1e1e; line-height: 1.3;">{cat_labels[c.name] || c.name}</span>
                  <span style="color: #666; font-weight: 600; font-family: 'Sora', system-ui, sans-serif; flex-shrink: 0;">{c.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Top entities */}
        <div style="background: #fff; border: 1px solid #eee; border-radius: 12px; padding: 1rem 1.25rem;">
          <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.85rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.75rem;">
            🏛️ {lang === 'cas' ? 'Entidades activas' : 'Entitats actives'}
          </h4>
          {profile.ents_top.length === 0 ? (
            <p style="font-size: 0.8rem; color: #aaa; font-style: italic;">—</p>
          ) : (
            <div style="display: grid; gap: 0.5rem;">
              {profile.ents_top.map(e => (
                <a
                  key={e.id}
                  href={`${entitats_path}${e.id}/`}
                  style="display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.8rem; text-decoration: none; color: inherit;"
                >
                  <span style="color: #1e1e1e; line-height: 1.3; text-decoration: none;">{lang === 'cas' ? e.name_cas : e.name_val}</span>
                  <span style="color: #666; font-weight: 600; font-family: 'Sora', system-ui, sans-serif; flex-shrink: 0;">{e.count}</span>
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
