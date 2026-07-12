import { useEffect, useRef, useState } from 'preact/hooks';

interface Props {
  districtCounts: Record<string, number>;
  barriCounts: Record<string, number>;
  lang: 'cas' | 'val';
}

// District code → normalized name
const DIST_NAMES: Record<string, string> = {
  '1': 'Ciutat Vella', '2': "L'Eixample", '3': 'Extramurs',
  '4': 'Campanar', '5': 'La Saïdia', '6': 'El Pla del Real',
  '7': "L'Olivereta", '8': 'Patraix', '9': 'Jesús',
  '10': 'Quatre Carreres', '11': 'Poblats Marítims',
  '12': 'Camins al Grau', '13': 'Algirós', '14': 'Benimaclet',
  '15': 'Rascanya', '16': 'Benicalap', '17': 'Poblats del Nord',
  '18': "Poblats de l'Oest", '19': 'Poblats del Sud',
};

function getColor(count: number, max: number): string {
  if (count === 0) return '#f5f5f5';
  const ratio = count / max;
  if (ratio > 0.7) return '#c2410c';
  if (ratio > 0.5) return '#e8562a';
  if (ratio > 0.3) return '#f59e0b';
  if (ratio > 0.1) return '#fbbf24';
  return '#fef3c7';
}

export function DistrictMap({ districtCounts, barriCounts, lang }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const layerRef = useRef<any>(null);
  const [mode, setMode] = useState<'districte' | 'barri'>('districte');
  const [leaflet, setLeaflet] = useState<any>(null);

  // Initialize map once
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    import('leaflet').then((L) => {
      if (!document.querySelector('link[href*="leaflet"]')) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
        document.head.appendChild(link);
      }

      const map = L.map(mapRef.current!, {
        zoomControl: true,
        attributionControl: false,
        dragging: true,
        scrollWheelZoom: false,
        doubleClickZoom: true,
        touchZoom: true,
      });

      map.setView([39.47, -0.377], 13);
      mapInstanceRef.current = map;
      setLeaflet(L);
    });

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  // Update layer when mode changes
  useEffect(() => {
    if (!leaflet || !mapInstanceRef.current) return;

    const map = mapInstanceRef.current;
    const L = leaflet;

    // Remove old layer
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    const file = mode === 'districte' ? '/districtes.geojson' : '/barris.geojson';
    const counts = mode === 'districte' ? districtCounts : barriCounts;
    const maxCount = Math.max(...Object.values(counts), 1);
    const label = lang === 'cas' ? 'intervenciones' : 'intervencions';

    fetch(file)
      .then((r) => r.json())
      .then((geojson) => {
        const geoLayer = L.geoJSON(geojson, {
          style: (feature: any) => {
            const name = getFeatureName(feature, mode);
            const count = counts[name] || 0;
            return {
              fillColor: getColor(count, maxCount),
              weight: mode === 'districte' ? 1.5 : 1,
              color: '#fff',
              fillOpacity: 0.85,
            };
          },
          onEachFeature: (feature: any, layer: any) => {
            const name = getFeatureName(feature, mode);
            const count = counts[name] || 0;

            layer.bindTooltip(
              `<div style="font-family: 'Sora', system-ui, sans-serif; text-align: center;">
                <strong style="font-size: 0.85rem;">${name}</strong><br/>
                <span style="font-size: 1.1rem; font-weight: 800; color: #e8562a;">${count}</span>
                <span style="font-size: 0.7rem; color: #666;"> ${label}</span>
              </div>`,
              { direction: 'top', className: 'district-tooltip' }
            );

            layer.on('mouseover', function (this: any) {
              this.setStyle({ weight: 2.5, color: '#e8562a', fillOpacity: 0.95 });
            });
            layer.on('mouseout', function (this: any) {
              geoLayer.resetStyle(this);
            });
          },
        }).addTo(map);

        layerRef.current = geoLayer;
      });
  }, [mode, leaflet]);

  return (
    <div>
      {/* Toggle */}
      <div style="display: flex; gap: 0.5rem; margin-bottom: 0.75rem;">
        <button
          onClick={() => setMode('districte')}
          style={{
            fontFamily: "'Outfit', system-ui, sans-serif",
            fontSize: '0.8rem',
            fontWeight: mode === 'districte' ? '600' : '400',
            color: mode === 'districte' ? '#fff' : '#666',
            background: mode === 'districte' ? '#1e1e1e' : 'none',
            border: mode === 'districte' ? 'none' : '1px solid #ddd',
            borderRadius: '100px',
            padding: '6px 16px',
            cursor: 'pointer',
            transition: 'all 0.15s',
          }}
          class="focus:outline-2 focus:outline-offset-2 focus:outline-orange-500"
        >
          {lang === 'cas' ? 'Distritos' : 'Districtes'}
        </button>
        <button
          onClick={() => setMode('barri')}
          style={{
            fontFamily: "'Outfit', system-ui, sans-serif",
            fontSize: '0.8rem',
            fontWeight: mode === 'barri' ? '600' : '400',
            color: mode === 'barri' ? '#fff' : '#666',
            background: mode === 'barri' ? '#1e1e1e' : 'none',
            border: mode === 'barri' ? 'none' : '1px solid #ddd',
            borderRadius: '100px',
            padding: '6px 16px',
            cursor: 'pointer',
            transition: 'all 0.15s',
          }}
          class="focus:outline-2 focus:outline-offset-2 focus:outline-orange-500"
        >
          {lang === 'cas' ? 'Barrios' : 'Barris'}
        </button>
      </div>

      {/* Map + legend wrapper */}
      <div style={{ position: 'relative' }}>
        <div
          ref={mapRef}
          style="width: 100%; height: 400px; border-radius: 16px; overflow: hidden; background: #f5f5f5;"
          aria-label={lang === 'cas' ? 'Mapa de intervenciones por distrito' : "Mapa d'intervencions per districte"}
          role="img"
        />

        {/* Legend overlay */}
        <div style={{
          position: 'absolute',
          bottom: '1rem',
          right: '0.75rem',
          background: 'rgba(255,255,255,0.93)',
          backdropFilter: 'blur(6px)',
          borderRadius: '10px',
          padding: '0.55rem 0.7rem',
          boxShadow: '0 2px 10px rgba(0,0,0,0.13)',
          zIndex: 999,
          fontFamily: "'Outfit', system-ui, sans-serif",
        }}>
          <p style={{ fontSize: '0.62rem', fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 0.4rem' }}>
            {lang === 'cas' ? 'Intervenciones' : 'Intervencions'}
          </p>
          {([
            { color: '#c2410c', label: lang === 'cas' ? 'Muy alto'  : 'Molt alt'  },
            { color: '#e8562a', label: lang === 'cas' ? 'Alto'      : 'Alt'       },
            { color: '#f59e0b', label: lang === 'cas' ? 'Medio'     : 'Mitjà'     },
            { color: '#fbbf24', label: lang === 'cas' ? 'Bajo'      : 'Baix'      },
            { color: '#fef3c7', label: lang === 'cas' ? 'Muy bajo'  : 'Molt baix' },
            { color: '#e8e8e8', label: lang === 'cas' ? 'Ninguna'   : 'Cap'       },
          ] as const).map(({ color, label }) => (
            <div key={color} style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '0.2rem' }}>
              <div style={{
                width: '11px',
                height: '11px',
                borderRadius: '3px',
                background: color,
                border: color === '#fef3c7' || color === '#e8e8e8' ? '1px solid #ddd' : 'none',
                flexShrink: 0,
              }} />
              <span style={{ fontSize: '0.68rem', color: '#555', whiteSpace: 'nowrap' }}>{label}</span>
            </div>
          ))}
        </div>
      </div>

      <style>{`
        .district-tooltip {
          background: #fff;
          border: 1px solid #eee;
          border-radius: 8px;
          padding: 6px 10px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.12);
        }
        .district-tooltip .leaflet-tooltip-tip { display: none; }
      `}</style>
    </div>
  );
}

function getFeatureName(feature: any, mode: string): string {
  const props = feature?.properties || {};
  if (mode === 'districte') {
    return DIST_NAMES[props.coddistrit] || props.nombre || '';
  }
  // Barri: normalize from UPPER CASE to Title Case
  const raw = (props.nombre || '').toLowerCase();
  // Title case with special handling
  return raw.replace(/(^|\s|'|-)\w/g, (m: string) => m.toUpperCase())
    .replace(/^L'e/i, "L'E")
    .replace(/^El /i, 'El ')
    .replace(/^La /i, 'La ')
    .replace(/^Les /i, 'Les ')
    .replace("D'a", "d'A")
    .replace("D'o", "d'O")
    .replace(" De ", " de ")
    .replace(" Del ", " del ")
    .replace(" I ", " i ")
    .replace(".li", ".lí")
    .replace("S.lluis", "S.Lluís");
}
