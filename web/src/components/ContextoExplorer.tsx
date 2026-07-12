import { useEffect, useRef, useState, useMemo } from 'preact/hooks';

/**
 * ContextoExplorer — "La ciudad en cifras" / "La ciutat en xifres"
 *
 * Iteration 1: vulnerability map + population evolution + vulnerability × interventions cross.
 * Iterations 2-3 will add budget data and demographic census.
 */

interface VulnEntry {
  distrito: string;
  ind_equipamientos: number;
  ind_demografico: number;
  ind_socioeconomico: number;
  ind_global: number;
  vul_global: string;
}

interface BarriPob {
  district: string;
  poblacion_por_anyo: Record<string, number>;
}

interface SlimIv {
  id: string;
  districtes: string[];
  zones: string[];
  temes: string[];
}

interface Obra {
  titulo: string;
  ambito: string;
  descripcion: string;
  tipo: string;
  financiacion: string;
  participacion_ciudadana: boolean;
  presupuesto: number;
  lng: number;
  lat: number;
}

interface PresupuestoData {
  years: string[];
  categories: string[];
  by_year: Record<string, Record<string, number>>;
  totals_by_year: Record<string, number>;
}

interface Props {
  vulnerabilidad: Record<string, VulnEntry>;
  barriPoblacion: Record<string, BarriPob>;
  barriToDistrict: Record<string, string>;
  intervencions: SlimIv[];
  presupuesto: PresupuestoData;
  obras: Obra[];
  lang: 'cas' | 'val';
}

type VulnMode = 'global' | 'equipamientos' | 'demografico' | 'socioeconomico';

const DIST_NAMES: Record<string, string> = {
  '1': 'Ciutat Vella', '2': "L'Eixample", '3': 'Extramurs',
  '4': 'Campanar', '5': 'La Saïdia', '6': 'El Pla del Real',
  '7': "L'Olivereta", '8': 'Patraix', '9': 'Jesús',
  '10': 'Quatre Carreres', '11': 'Poblats Marítims',
  '12': 'Camins al Grau', '13': 'Algirós', '14': 'Benimaclet',
  '15': 'Rascanya', '16': 'Benicalap', '17': 'Poblats del Nord',
  '18': "Poblats de l'Oest", '19': 'Poblats del Sud',
};

const CAT_COLORS: Record<string, string> = {
  urbanisme: '#6366f1',
  mobilitat: '#0ea5e9',
  medi_ambient: '#22c55e',
  serveis_publics: '#f97316',
  economia: '#eab308',
  drets_i_igualtat: '#ec4899',
  persones: '#a855f7',
  cultura: '#14b8a6',
  participacio: '#f43f5e',
};

const CAT_LABELS: Record<string, { cas: string; val: string }> = {
  urbanisme:        { cas: 'Urbanismo',          val: 'Urbanisme' },
  mobilitat:        { cas: 'Movilidad',          val: 'Mobilitat' },
  medi_ambient:     { cas: 'Medio ambiente',     val: 'Medi ambient' },
  serveis_publics:  { cas: 'Servicios públicos', val: 'Serveis públics' },
  economia:         { cas: 'Economía',           val: 'Economia' },
  drets_i_igualtat: { cas: 'Derechos e igualdad',val: 'Drets i igualtat' },
  persones:         { cas: 'Personas',           val: 'Persones' },
  cultura:          { cas: 'Cultura',            val: 'Cultura' },
  participacio:     { cas: 'Participación',      val: 'Participació' },
};

function vulnColor(v: number): string {
  // Index ranges 1-5 (lower = more vulnerable)
  if (v <= 2.0) return '#dc2626';  // high vulnerability = red
  if (v <= 2.4) return '#f97316';  // medium-high
  if (v <= 2.6) return '#facc15';  // medium
  if (v <= 3.0) return '#86efac';  // medium-low
  return '#22c55e';                // low vulnerability = green
}

function fmt(n: number): string {
  return n.toLocaleString('es-ES');
}

export function ContextoExplorer({ vulnerabilidad, barriPoblacion, barriToDistrict, intervencions, presupuesto, obras, lang }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const layerRef = useRef<any>(null);
  const [leaflet, setLeaflet] = useState<any>(null);
  const [vulnMode, setVulnMode] = useState<VulnMode>('global');
  const [selectedBarri, setSelectedBarri] = useState<string | null>(null);
  const [showObras, setShowObras] = useState(false);
  const obrasLayerRef = useRef<any>(null);

  const vulnModeLabels = {
    global:          lang === 'cas' ? 'Global'          : 'Global',
    equipamientos:   lang === 'cas' ? 'Equipamientos'   : 'Equipaments',
    demografico:     lang === 'cas' ? 'Demográfico'     : 'Demogràfic',
    socioeconomico:  lang === 'cas' ? 'Socioeconómico'  : 'Socioeconòmic',
  };

  const vulnModeKey: Record<VulnMode, keyof VulnEntry> = {
    global: 'ind_global',
    equipamientos: 'ind_equipamientos',
    demografico: 'ind_demografico',
    socioeconomico: 'ind_socioeconomico',
  };

  // Interventions per barri for the cross section
  const ivsByBarri = useMemo(() => {
    const res: Record<string, number> = {};
    for (const iv of intervencions) {
      const seen = new Set<string>();
      for (const z of iv.zones || []) {
        if (!seen.has(z)) { seen.add(z); res[z] = (res[z] || 0) + 1; }
      }
    }
    return res;
  }, [intervencions]);

  // Sorted vulnerability ranking for the table
  const vulnRanking = useMemo(() => {
    return Object.entries(vulnerabilidad)
      .map(([name, v]) => ({
        name,
        district: barriToDistrict[name] || v.distrito,
        ...v,
        intervenciones: ivsByBarri[name] || 0,
        pob2025: barriPoblacion[name]?.poblacion_por_anyo?.['2025'] || 0,
      }))
      .sort((a, b) => a.ind_global - b.ind_global);
  }, [vulnerabilidad, barriToDistrict, ivsByBarri, barriPoblacion]);

  // =========================================================
  // Init map
  // =========================================================
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
        zoomControl: true, attributionControl: false,
        dragging: true, scrollWheelZoom: false,
        doubleClickZoom: true, touchZoom: true,
      });
      map.setView([39.47, -0.377], 12);
      mapInstanceRef.current = map;
      setLeaflet(L);
    });
    return () => { if (mapInstanceRef.current) { mapInstanceRef.current.remove(); mapInstanceRef.current = null; } };
  }, []);

  // =========================================================
  // Update map layer
  // =========================================================
  useEffect(() => {
    if (!leaflet || !mapInstanceRef.current) return;
    const map = mapInstanceRef.current;
    const L = leaflet;
    if (layerRef.current) { map.removeLayer(layerRef.current); layerRef.current = null; }

    const upperToCanon: Record<string, string> = {};
    for (const b of Object.keys(barriToDistrict)) upperToCanon[b.toUpperCase()] = b;

    const key = vulnModeKey[vulnMode];

    fetch('/barris.geojson').then(r => r.json()).then(geojson => {
      const layer = L.geoJSON(geojson, {
        style: (f: any) => {
          const raw = f?.properties?.nombre || '';
          const name = upperToCanon[raw.toUpperCase()] || raw;
          const entry = vulnerabilidad[name];
          const v = entry ? (entry as any)[key] : null;
          return {
            fillColor: v != null ? vulnColor(v) : '#e5e5e5',
            weight: selectedBarri === name ? 3 : 0.8,
            color: selectedBarri === name ? '#6366f1' : '#fff',
            fillOpacity: v != null ? 0.8 : 0.3,
          };
        },
        onEachFeature: (f: any, l: any) => {
          const raw = f?.properties?.nombre || '';
          const name = upperToCanon[raw.toUpperCase()] || raw;
          const entry = vulnerabilidad[name];
          const v = entry ? (entry as any)[key] : null;
          const distrito = barriToDistrict[name] || '';
          const label = vulnModeLabels[vulnMode];
          const hasData = v != null;
          l.bindTooltip(
            `<div style="font-family: 'Sora', system-ui, sans-serif; text-align: center;">
              <strong>${name}</strong><br/>
              ${distrito ? `<span style="font-size: 0.7rem; color: #666;">${distrito}</span><br/>` : ''}
              ${hasData
                ? `<span style="font-size: 1.1rem; font-weight: 800; color: ${vulnColor(v)};">${v.toFixed(1)}</span>
                   <span style="font-size: 0.7rem; color: #666;"> ${label}</span>`
                : `<span style="font-size: 0.8rem; color: #aaa;">${lang === 'cas' ? 'Sin datos' : 'Sense dades'}</span>`}
            </div>`,
            { direction: 'top', className: 'district-tooltip' }
          );
          l.on('mouseover', function (this: any) {
            if (name !== selectedBarri) this.setStyle({ weight: 2.5, color: '#6366f1', fillOpacity: 0.95 });
          });
          l.on('mouseout', function (this: any) { layer.resetStyle(this); });
          l.on('click', () => setSelectedBarri(name));
        },
      }).addTo(map);
      layerRef.current = layer;
    });
  }, [leaflet, vulnMode, vulnerabilidad, selectedBarri, barriToDistrict, lang]);

  // =========================================================
  // Obras ejecutadas layer
  // =========================================================
  useEffect(() => {
    if (!leaflet || !mapInstanceRef.current) return;
    const map = mapInstanceRef.current;
    const L = leaflet;

    // Remove previous
    if (obrasLayerRef.current) { map.removeLayer(obrasLayerRef.current); obrasLayerRef.current = null; }

    if (!showObras || !obras.length) return;

    const group = L.layerGroup();
    for (const obra of obras) {
      if (!obra.lat || !obra.lng) continue;
      const isPC = obra.participacion_ciudadana;
      const color = isPC ? '#e8562a' : '#6366f1';
      const radius = isPC ? 7 : 5;
      const marker = L.circleMarker([obra.lat, obra.lng], {
        radius,
        fillColor: color,
        color: '#fff',
        weight: 1.5,
        fillOpacity: 0.85,
      });
      const pres = obra.presupuesto > 0 ? `${(obra.presupuesto / 1000).toFixed(0)}k€` : '';
      marker.bindTooltip(
        `<div style="font-family: 'Sora', system-ui, sans-serif; max-width: 220px;">
          <strong style="font-size: 0.8rem;">${obra.titulo}</strong><br/>
          <span style="font-size: 0.7rem; color: #666;">${obra.tipo || ''}</span><br/>
          <span style="font-size: 0.75rem; font-weight: 600; color: ${color};">${obra.financiacion}</span>
          ${pres ? `<br/><span style="font-size: 0.7rem; color: #666;">${pres}</span>` : ''}
        </div>`,
        { direction: 'top' }
      );
      group.addLayer(marker);
    }
    group.addTo(map);
    obrasLayerRef.current = group;
  }, [leaflet, showObras, obras]);

  return (
    <div style="font-family: 'Outfit', system-ui, sans-serif;">

      {/* ─── Bloque 1: Vulnerabilidad ─── */}
      <section style="padding: 2.5rem 1rem; background: #fff;">
        <div class="max-w-5xl mx-auto">
          <h2 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.5rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 0.5rem;">
            {lang === 'cas' ? 'Vulnerabilidad por barrio' : 'Vulnerabilitat per barri'}
          </h2>
          <p style="color: #666; margin-bottom: 1.25rem; max-width: 42rem; line-height: 1.6; font-size: 0.9rem;">
            {lang === 'cas'
              ? 'Índice de vulnerabilidad urbana del Ayuntamiento (2021). Combina tres dimensiones — equipamientos públicos, perfil demográfico y nivel socioeconómico — en un indicador global de 1 (máxima vulnerabilidad) a 5 (mínima). Los barrios en rojo son los que concentran más carencias; los verdes, los mejor dotados. 70 barrios urbanos; las pedanías no tienen este índice calculado.'
              : 'Índex de vulnerabilitat urbana de l\'Ajuntament (2021). Combina tres dimensions — equipaments públics, perfil demogràfic i nivell socioeconòmic — en un indicador global d\'1 (màxima vulnerabilitat) a 5 (mínima). Els barris en roig són els que concentren més carències; els verds, els millor dotats. 70 barris urbans; les pedanies no tenen este índex calculat.'}
          </p>

          {/* Mode selector */}
          <div style="display: flex; gap: 0.25rem; margin-bottom: 1rem; flex-wrap: wrap;">
            {(['global', 'equipamientos', 'demografico', 'socioeconomico'] as const).map(m => (
              <button
                key={m}
                onClick={() => setVulnMode(m)}
                style={{
                  fontSize: '0.75rem',
                  fontWeight: vulnMode === m ? '600' : '400',
                  color: vulnMode === m ? '#fff' : '#666',
                  background: vulnMode === m ? '#6366f1' : 'none',
                  border: vulnMode === m ? 'none' : '1px solid #ddd',
                  borderRadius: '100px', padding: '5px 12px', cursor: 'pointer',
                }}
              >
                {vulnModeLabels[m]}
              </button>
            ))}
          </div>

          {/* Obras toggle */}
          {obras.length > 0 && (
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem;">
              <button
                onClick={() => setShowObras(!showObras)}
                style={{
                  fontSize: '0.75rem',
                  fontWeight: showObras ? '600' : '400',
                  color: showObras ? '#fff' : '#666',
                  background: showObras ? '#e8562a' : 'none',
                  border: showObras ? 'none' : '1px solid #ddd',
                  borderRadius: '100px', padding: '5px 12px', cursor: 'pointer',
                }}
              >
                {lang === 'cas' ? 'Obras ejecutadas' : 'Obres executades'} ({obras.length})
              </button>
              {showObras && (
                <span style="font-size: 0.7rem; color: #666;">
                  <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #e8562a; margin-right: 3px;" />
                  {lang === 'cas' ? 'Participación Ciudadana' : 'Participació Ciutadana'}
                  <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #6366f1; margin: 0 3px 0 10px;" />
                  {lang === 'cas' ? 'Otras' : 'Altres'}
                </span>
              )}
            </div>
          )}

          {/* Color legend */}
          <div style="display: flex; gap: 0.75rem; margin-bottom: 1rem; font-size: 0.75rem; color: #666; flex-wrap: wrap;">
            {[
              { color: '#dc2626', label: lang === 'cas' ? '≤2.0 Alta' : '≤2.0 Alta' },
              { color: '#f97316', label: '2.1-2.4' },
              { color: '#facc15', label: '2.5-2.6' },
              { color: '#86efac', label: '2.7-3.0' },
              { color: '#22c55e', label: lang === 'cas' ? '>3.0 Baja' : '>3.0 Baixa' },
              { color: '#e5e5e5', label: lang === 'cas' ? 'Sin datos' : 'Sense dades' },
            ].map(l => (
              <div key={l.color} style="display: flex; align-items: center; gap: 0.3rem;">
                <span style={`display: inline-block; width: 14px; height: 14px; border-radius: 3px; background: ${l.color}; border: 1px solid #ddd;`} />
                <span>{l.label}</span>
              </div>
            ))}
          </div>

          <div ref={mapRef} style="width: 100%; height: 480px; border-radius: 16px; overflow: hidden; background: #f5f5f5; position: relative; z-index: 0;" />
        </div>
      </section>

      {/* ─── Ranking table ─── */}
      <section style="padding: 2rem 1rem; background: #fafafa; border-top: 1px solid #eee;">
        <div class="max-w-5xl mx-auto">
          <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.2rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.5rem;">
            {lang === 'cas' ? 'Ranking de vulnerabilidad' : 'Rànquing de vulnerabilitat'}
          </h3>
          <p style="color: #666; margin-bottom: 1rem; max-width: 42rem; font-size: 0.85rem; line-height: 1.5;">
            {lang === 'cas'
              ? 'Ordenado de más vulnerable (arriba) a menos. Las últimas columnas muestran el número de intervenciones al pleno (2019-2026) que mencionan cada barrio y la población residente (2025).'
              : 'Ordenat de més vulnerable (dalt) a menys. Les últimes columnes mostren el nombre d\'intervencions al ple (2019-2026) que esmenten cada barri i la població resident (2025).'}
          </p>

          <div style="max-height: 500px; overflow-y: auto; border: 1px solid #eee; border-radius: 12px; background: #fff;">
            <div style="display: grid; grid-template-columns: minmax(9rem, 1.5fr) 3.5rem 3.5rem 3.5rem 3.5rem 3.5rem 4rem; gap: 0; padding: 0.5rem 0.4rem; background: #fafafa; border-bottom: 1px solid #eee; font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: #666; position: sticky; top: 0;">
              <span style="padding: 0 0.5rem;">{lang === 'cas' ? 'Barrio' : 'Barri'}</span>
              <span style="text-align: center;">Glob.</span>
              <span style="text-align: center;">{lang === 'cas' ? 'Equip.' : 'Equip.'}</span>
              <span style="text-align: center;">{lang === 'cas' ? 'Demo.' : 'Demo.'}</span>
              <span style="text-align: center;">{lang === 'cas' ? 'Econ.' : 'Econ.'}</span>
              <span style="text-align: center;">{lang === 'cas' ? 'Interv.' : 'Interv.'}</span>
              <span style="text-align: right; padding: 0 0.5rem;">{lang === 'cas' ? 'Pob.' : 'Pob.'}</span>
            </div>
            {vulnRanking.map(d => (
              <div
                key={d.name}
                onClick={() => setSelectedBarri(d.name)}
                style={`display: grid; grid-template-columns: minmax(9rem, 1.5fr) 3.5rem 3.5rem 3.5rem 3.5rem 3.5rem 4rem; gap: 0; align-items: center; padding: 0.45rem 0.4rem; border-bottom: 1px solid #f5f5f5; font-size: 0.8rem; cursor: pointer; ${selectedBarri === d.name ? 'background: #eef2ff;' : ''}`}
              >
                <div style="padding: 0 0.5rem; min-width: 0;">
                  <div style="font-weight: 500; line-height: 1.2;">{d.name}</div>
                  <div style="font-size: 0.6rem; color: #aaa; margin-top: 1px;">{d.district}</div>
                </div>
                <span style={`text-align: center; font-family: 'Sora', system-ui, sans-serif; font-weight: 700; color: ${vulnColor(d.ind_global)};`}>{d.ind_global.toFixed(1)}</span>
                <span style={`text-align: center; font-family: 'Sora', system-ui, sans-serif; font-weight: 600; font-size: 0.75rem; color: ${vulnColor(d.ind_equipamientos)};`}>{d.ind_equipamientos.toFixed(1)}</span>
                <span style={`text-align: center; font-family: 'Sora', system-ui, sans-serif; font-weight: 600; font-size: 0.75rem; color: ${vulnColor(d.ind_demografico)};`}>{d.ind_demografico.toFixed(1)}</span>
                <span style={`text-align: center; font-family: 'Sora', system-ui, sans-serif; font-weight: 600; font-size: 0.75rem; color: ${vulnColor(d.ind_socioeconomico)};`}>{d.ind_socioeconomico.toFixed(1)}</span>
                <span style="text-align: center; font-family: 'Sora', system-ui, sans-serif; font-weight: 600; font-size: 0.75rem; color: #1e1e1e;">
                  {d.intervenciones || '—'}
                </span>
                <span style="text-align: right; padding: 0 0.5rem; font-size: 0.75rem; color: #666;">
                  {d.pob2025 ? fmt(d.pob2025) : '—'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Bloque 2: Presupuesto municipal ─── */}
      <section style="padding: 2rem 1rem; background: #fff; border-top: 1px solid #eee;">
        <div class="max-w-5xl mx-auto">
          <h2 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.5rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 0.5rem;">
            {lang === 'cas' ? 'Presupuesto municipal' : 'Pressupost municipal'}
          </h2>
          <p style="color: #666; margin-bottom: 1.5rem; max-width: 42rem; line-height: 1.6; font-size: 0.9rem;">
            {lang === 'cas'
              ? 'Gasto ejecutado del Ayuntamiento de València (obligaciones reconocidas netas), agrupado por áreas temáticas equivalentes a las categorías de las intervenciones ciudadanas. Solo se incluyen partidas con impacto directo en servicios — quedan fuera la deuda pública y la administración general.'
              : 'Despesa executada de l\'Ajuntament de València (obligacions reconegudes netes), agrupada per àrees temàtiques equivalents a les categories de les intervencions ciutadanes. Només s\'inclouen partides amb impacte directe en serveis — queden fora el deute públic i l\'administració general.'}
          </p>
          <PresupuestoChart presupuesto={presupuesto} lang={lang} />
        </div>
      </section>

      {/* ─── Bloque 2b: Presupuesto vs intervenciones ─── */}
      <section style="padding: 2rem 1rem; background: #fafafa; border-top: 1px solid #eee;">
        <div class="max-w-5xl mx-auto">
          <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.2rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.5rem;">
            {lang === 'cas' ? '¿Se habla de lo que se gasta?' : 'Es parla del que es gasta?'}
          </h3>
          <p style="color: #666; margin-bottom: 1.5rem; max-width: 42rem; font-size: 0.85rem; line-height: 1.5;">
            {lang === 'cas'
              ? 'Comparativa entre el peso de cada área en el presupuesto ejecutado (2021-2025) y el porcentaje de intervenciones ciudadanas que tratan ese tema. Las diferencias revelan qué temas generan más preocupación vecinal respecto a su dotación presupuestaria.'
              : 'Comparativa entre el pes de cada àrea en el pressupost executat (2021-2025) i el percentatge d\'intervencions ciutadanes que tracten eixe tema. Les diferències revelen quins temes generen més preocupació veïnal respecte a la seua dotació pressupostària.'}
          </p>
          <BudgetVsInterventions presupuesto={presupuesto} intervencions={intervencions} lang={lang} />
        </div>
      </section>

      {/* ─── Bloque 3: Cruce por distrito ─── */}
      <section style="padding: 2rem 1rem; background: #fff; border-top: 1px solid #eee;">
        <div class="max-w-5xl mx-auto">
          <h2 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.5rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 0.5rem;">
            {lang === 'cas' ? '¿Habla quien más lo necesita?' : 'Parla qui més ho necessita?'}
          </h2>
          <p style="color: #666; margin-bottom: 1.5rem; max-width: 42rem; line-height: 1.6; font-size: 0.9rem;">
            {lang === 'cas'
              ? 'Cada burbuja es un distrito. El eje horizontal mide la vulnerabilidad media de sus barrios (más a la izquierda = más vulnerable); el vertical, la tasa de intervenciones por cada 10.000 habitantes. El tamaño de la burbuja refleja la población. Si la participación fuera proporcional a la necesidad, los puntos de la izquierda estarían arriba.'
              : 'Cada bombolla és un districte. L\'eix horitzontal mesura la vulnerabilitat mitjana dels seus barris (més a l\'esquerra = més vulnerable); el vertical, la taxa d\'intervencions per cada 10.000 habitants. La grandària de la bombolla reflecteix la població. Si la participació fora proporcional a la necessitat, els punts de l\'esquerra estarien dalt.'}
          </p>

          <DistrictCrossScatter
            vulnerabilidad={vulnerabilidad}
            barriToDistrict={barriToDistrict}
            barriPoblacion={barriPoblacion}
            intervencions={intervencions}
            lang={lang}
          />
        </div>
      </section>

      {/* ─── Bloque 3b: Cruce por barrio (scatter detallado) ─── */}
      <section style="padding: 2rem 1rem; background: #fafafa; border-top: 1px solid #eee;">
        <div class="max-w-5xl mx-auto">
          <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.2rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.5rem;">
            {lang === 'cas' ? 'Detalle por barrio' : 'Detall per barri'}
          </h3>
          <p style="color: #666; margin-bottom: 1.5rem; max-width: 42rem; font-size: 0.85rem; line-height: 1.5;">
            {lang === 'cas'
              ? 'La misma pregunta a escala de barrio. Los puntos rojos (más vulnerables) tienden a quedarse abajo — poca presencia en el pleno.'
              : 'La mateixa pregunta a escala de barri. Els punts rojos (més vulnerables) tendeixen a quedar-se avall — poca presència al ple.'}
          </p>

          <VulnIntervencionesScatter data={vulnRanking} lang={lang} />
        </div>
      </section>
    </div>
  );
}

// ================================================================
// Stacked bar chart: budget by year × category
// ================================================================
function PresupuestoChart({ presupuesto, lang }: { presupuesto: PresupuestoData; lang: 'cas' | 'val' }) {
  const years = presupuesto.years.filter(y => y !== '2026'); // exclude incomplete year
  const cats = presupuesto.categories;
  if (!years.length || !cats.length) return null;

  const maxTotal = Math.max(...years.map(y => presupuesto.totals_by_year[y] || 0));
  const W = 600, H = 340;
  const padL = 55, padR = 20, padT = 20, padB = 40;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const barW = Math.min(60, (plotW / years.length) * 0.7);
  const gap = (plotW - barW * years.length) / (years.length + 1);

  return (
    <div style="background: #fff; border-radius: 12px; padding: 1rem; border: 1px solid #eee;">
      <svg viewBox={`0 0 ${W} ${H}`} style="width: 100%; height: auto; display: block; font-family: 'Outfit', system-ui, sans-serif;">
        {/* Y axis */}
        <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke="#eee" stroke-width="1" />
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map(frac => {
          const yy = padT + plotH - frac * plotH;
          const val = (maxTotal * frac / 1e6).toFixed(0);
          return (
            <g key={frac}>
              <line x1={padL} y1={yy} x2={padL + plotW} y2={yy} stroke="#f0f0f0" stroke-width="1" />
              <text x={padL - 6} y={yy + 4} text-anchor="end" font-size="9" fill="#999">{val} M</text>
            </g>
          );
        })}

        {/* Bars */}
        {years.map((year, i) => {
          const xBase = padL + gap + i * (barW + gap);
          const yearData = presupuesto.by_year[year] || {};
          const total = presupuesto.totals_by_year[year] || 0;
          let cumY = 0;
          return (
            <g key={year}>
              {cats.map(cat => {
                const val = yearData[cat] || 0;
                const h = (val / maxTotal) * plotH;
                const yy = padT + plotH - cumY - h;
                cumY += h;
                return h > 0.5 ? (
                  <rect key={cat} x={xBase} y={yy} width={barW} height={h}
                        fill={CAT_COLORS[cat] || '#ccc'} rx="1">
                    <title>{CAT_LABELS[cat]?.[lang] || cat}: {(val / 1e6).toFixed(1)} M€ ({(val / total * 100).toFixed(0)}%)</title>
                  </rect>
                ) : null;
              })}
              <text x={xBase + barW / 2} y={padT + plotH + 16} text-anchor="middle" font-size="11" fill="#666" font-weight="500">{year}</text>
              <text x={xBase + barW / 2} y={padT + plotH - cumY - 5} text-anchor="middle" font-size="9" fill="#666">{(total / 1e6).toFixed(0)} M</text>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div style="display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; margin-top: 0.75rem; padding: 0 0.25rem;">
        {cats.map(cat => (
          <div key={cat} style="display: flex; align-items: center; gap: 0.3rem; font-size: 0.72rem; color: #666;">
            <span style={`display: inline-block; width: 10px; height: 10px; border-radius: 2px; background: ${CAT_COLORS[cat] || '#ccc'};`} />
            {CAT_LABELS[cat]?.[lang] || cat}
          </div>
        ))}
      </div>
    </div>
  );
}

// ================================================================
// Side-by-side: budget % vs interventions %
// ================================================================
function BudgetVsInterventions({
  presupuesto, intervencions, lang,
}: {
  presupuesto: PresupuestoData;
  intervencions: SlimIv[];
  lang: 'cas' | 'val';
}) {
  const data = useMemo(() => {
    // Budget totals across all complete years
    const years = presupuesto.years.filter(y => y !== '2026');
    const budgetByCat: Record<string, number> = {};
    let budgetTotal = 0;
    for (const y of years) {
      const yd = presupuesto.by_year[y] || {};
      for (const [cat, val] of Object.entries(yd)) {
        budgetByCat[cat] = (budgetByCat[cat] || 0) + val;
        budgetTotal += val;
      }
    }

    // Intervention counts by category
    const ivByCat: Record<string, number> = {};
    let ivTotal = 0;
    for (const iv of intervencions) {
      for (const cat of iv.temes || []) {
        ivByCat[cat] = (ivByCat[cat] || 0) + 1;
        ivTotal += 1;
      }
    }

    // All categories from both sources
    const allCats = [...new Set([...Object.keys(budgetByCat), ...Object.keys(ivByCat)])].sort();

    return allCats.map(cat => ({
      cat,
      budgetPct: budgetTotal > 0 ? (budgetByCat[cat] || 0) / budgetTotal * 100 : 0,
      ivPct: ivTotal > 0 ? (ivByCat[cat] || 0) / ivTotal * 100 : 0,
      budgetM: (budgetByCat[cat] || 0) / 1e6,
      ivCount: ivByCat[cat] || 0,
    }));
  }, [presupuesto, intervencions]);

  const maxPct = Math.max(...data.map(d => Math.max(d.budgetPct, d.ivPct)), 1);

  const W = 600, rowH = 38;
  const padL = 120, padR = 70;
  const H = data.length * rowH + 40;
  const barW = W - padL - padR;
  const barH = 12;

  return (
    <div style="background: #fff; border-radius: 12px; padding: 1rem; border: 1px solid #eee;">
      {/* Legend */}
      <div style="display: flex; gap: 1.5rem; margin-bottom: 0.75rem; font-size: 0.78rem; color: #666;">
        <div style="display: flex; align-items: center; gap: 0.4rem;">
          <span style="display: inline-block; width: 14px; height: 8px; border-radius: 2px; background: #6366f1;" />
          {lang === 'cas' ? 'Presupuesto ejecutado' : 'Pressupost executat'}
        </div>
        <div style="display: flex; align-items: center; gap: 0.4rem;">
          <span style="display: inline-block; width: 14px; height: 8px; border-radius: 2px; background: #e8562a;" />
          {lang === 'cas' ? 'Intervenciones ciudadanas' : 'Intervencions ciutadanes'}
        </div>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} style="width: 100%; height: auto; display: block; font-family: 'Outfit', system-ui, sans-serif;">
        {data.map((d, i) => {
          const y = i * rowH + 10;
          const bW = (d.budgetPct / maxPct) * barW;
          const iW = (d.ivPct / maxPct) * barW;
          const label = CAT_LABELS[d.cat]?.[lang] || d.cat;
          const color = CAT_COLORS[d.cat] || '#666';
          return (
            <g key={d.cat}>
              {/* Category label */}
              <text x={padL - 8} y={y + rowH / 2 + 1} text-anchor="end" font-size="11" fill="#444" font-weight="500">
                {label}
              </text>
              {/* Color dot */}
              <circle cx={padL - label.length * 5.5 - 18} cy={y + rowH / 2 - 1} r="4" fill={color} />
              {/* Budget bar */}
              <rect x={padL} y={y + 4} width={Math.max(bW, 1)} height={barH} rx="3" fill="#6366f1" opacity="0.85">
                <title>{label}: {d.budgetPct.toFixed(1)}% — {d.budgetM.toFixed(0)} M€</title>
              </rect>
              <text x={padL + bW + 5} y={y + 4 + barH / 2 + 3.5} font-size="9" fill="#6366f1" font-weight="600">
                {d.budgetPct.toFixed(1)}%
              </text>
              {/* Interventions bar */}
              <rect x={padL} y={y + 4 + barH + 3} width={Math.max(iW, 1)} height={barH} rx="3" fill="#e8562a" opacity="0.85">
                <title>{label}: {d.ivPct.toFixed(1)}% — {d.ivCount} intervenciones</title>
              </rect>
              <text x={padL + iW + 5} y={y + 4 + barH + 3 + barH / 2 + 3.5} font-size="9" fill="#e8562a" font-weight="600">
                {d.ivPct.toFixed(1)}%
              </text>
            </g>
          );
        })}
      </svg>

      <p style="color: #666; font-size: 0.78rem; margin-top: 0.75rem; line-height: 1.5; max-width: 42rem;">
        {lang === 'cas'
          ? <>Las mayores discrepancias revelan las tensiones entre inversión municipal y preocupación vecinal. <strong>Urbanismo</strong> y <strong>movilidad</strong> concentran mucha más voz ciudadana de lo que representan en el presupuesto, mientras que <strong>medio ambiente</strong> y <strong>servicios públicos</strong> absorben la mayor parte del gasto pero generan menos debate en los plenos.</>
          : <>Les majors discrepàncies revelen les tensions entre inversió municipal i preocupació veïnal. <strong>Urbanisme</strong> i <strong>mobilitat</strong> concentren molta més veu ciutadana del que representen en el pressupost, mentre que <strong>medi ambient</strong> i <strong>serveis públics</strong> absorbeixen la major part de la despesa però generen menys debat als plens.</>}
      </p>
    </div>
  );
}

// ================================================================
// District bubble scatter: vulnerability × intervention rate
// ================================================================
function DistrictCrossScatter({
  vulnerabilidad, barriToDistrict, barriPoblacion, intervencions, lang,
}: {
  vulnerabilidad: Record<string, VulnEntry>;
  barriToDistrict: Record<string, string>;
  barriPoblacion: Record<string, BarriPob>;
  intervencions: SlimIv[];
  lang: 'cas' | 'val';
}) {
  const [popup, setPopup] = useState<string | null>(null);

  const districts = useMemo(() => {
    // Aggregate vulnerability by district
    const distVuln: Record<string, number[]> = {};
    for (const [barri, v] of Object.entries(vulnerabilidad)) {
      const dist = barriToDistrict[barri] || v.distrito;
      if (!dist) continue;
      if (!distVuln[dist]) distVuln[dist] = [];
      distVuln[dist].push(v.ind_global);
    }

    // Population by district
    const distPop: Record<string, number> = {};
    for (const [barri, bp] of Object.entries(barriPoblacion)) {
      const dist = barriToDistrict[barri] || '';
      if (dist) distPop[dist] = (distPop[dist] || 0) + (bp.poblacion_por_anyo?.['2025'] || 0);
    }

    // Interventions by district
    const distIvs: Record<string, number> = {};
    for (const iv of intervencions) {
      for (const d of iv.districtes || []) distIvs[d] = (distIvs[d] || 0) + 1;
    }

    // Build array — exclude districts without vulnerability data (pedanías)
    return Object.keys(distVuln)
      .filter(d => distVuln[d].length > 0)
      .map(d => {
        const avgVuln = distVuln[d].reduce((a, b) => a + b, 0) / distVuln[d].length;
        const pop = distPop[d] || 0;
        const ivs = distIvs[d] || 0;
        const rate = pop > 0 ? ivs / pop * 10000 : 0;
        return { name: d, vuln: avgVuln, ivs, pop, rate };
      })
      .sort((a, b) => a.vuln - b.vuln);
  }, [vulnerabilidad, barriToDistrict, barriPoblacion, intervencions]);

  if (districts.length === 0) return null;

  // Key findings
  const findings = useMemo(() => {
    const sorted = [...districts].sort((a, b) => a.vuln - b.vuln);
    const top5 = sorted.slice(0, 5);
    const bot5 = sorted.slice(-5);
    const totalPop = districts.reduce((s, d) => s + d.pop, 0);
    const totalIvs = districts.reduce((s, d) => s + d.ivs, 0);
    const top5Pop = top5.reduce((s, d) => s + d.pop, 0);
    const top5Ivs = top5.reduce((s, d) => s + d.ivs, 0);
    const bot5Pop = bot5.reduce((s, d) => s + d.pop, 0);
    const bot5Ivs = bot5.reduce((s, d) => s + d.ivs, 0);
    return {
      top5PopPct: totalPop > 0 ? (top5Pop / totalPop * 100).toFixed(0) : '0',
      top5IvsPct: totalIvs > 0 ? (top5Ivs / totalIvs * 100).toFixed(0) : '0',
      bot5PopPct: totalPop > 0 ? (bot5Pop / totalPop * 100).toFixed(0) : '0',
      bot5IvsPct: totalIvs > 0 ? (bot5Ivs / totalIvs * 100).toFixed(0) : '0',
      top5Names: top5.map(d => d.name),
      bot5Names: bot5.map(d => d.name),
      mostActive: [...districts].sort((a, b) => b.rate - a.rate)[0],
      leastActive: [...districts].filter(d => d.pop > 10000).sort((a, b) => a.rate - b.rate)[0],
    };
  }, [districts]);

  const minX = Math.min(...districts.map(d => d.vuln));
  const maxX = Math.max(...districts.map(d => d.vuln));
  const maxY = Math.max(...districts.map(d => d.rate));
  const maxPop = Math.max(...districts.map(d => d.pop));

  const W = 640, H = 440;
  const padL = 52, padR = 30, padT = 30, padB = 55;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const x = (v: number) => padL + ((v - minX) / Math.max(0.01, maxX - minX)) * plotW;
  const y = (v: number) => padT + plotH - (v / maxY) * plotH;
  const r = (pop: number) => 8 + (pop / maxPop) * 22;

  return (
    <div style="background: #fff; border-radius: 12px; padding: 1rem; border: 1px solid #eee;">
      <svg viewBox={`0 0 ${W} ${H}`} style="width: 100%; height: auto; display: block; font-family: 'Outfit', system-ui, sans-serif;"
           onClick={() => setPopup(null)}>
        {/* Grid */}
        <line x1={padL} y1={padT + plotH} x2={padL + plotW} y2={padT + plotH} stroke="#ddd" stroke-width="1" />
        <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke="#ddd" stroke-width="1" />

        {/* Axis labels */}
        <text x={padL + plotW / 2} y={H - 10} text-anchor="middle" font-size="11" fill="#666">
          {lang === 'cas' ? '← más vulnerable · vulnerabilidad media del distrito · menos vulnerable →' : '← més vulnerable · vulnerabilitat mitjana del districte · menys vulnerable →'}
        </text>
        <text x="14" y={padT + plotH / 2} text-anchor="middle" font-size="11" fill="#666"
              transform={`rotate(-90 14 ${padT + plotH / 2})`}>
          {lang === 'cas' ? '→ intervenciones / 10.000 hab.' : '→ intervencions / 10.000 hab.'}
        </text>

        {/* Ticks */}
        <text x={padL} y={padT + plotH + 16} text-anchor="start" font-size="10" fill="#999">{minX.toFixed(1)}</text>
        <text x={padL + plotW} y={padT + plotH + 16} text-anchor="end" font-size="10" fill="#999">{maxX.toFixed(1)}</text>
        <text x={padL - 6} y={padT + plotH + 3} text-anchor="end" font-size="10" fill="#999">0</text>
        <text x={padL - 6} y={padT + 4} text-anchor="end" font-size="10" fill="#999">{maxY.toFixed(0)}</text>

        {/* Bubbles */}
        {districts.map(d => {
          const cx = x(d.vuln);
          const cy = y(d.rate);
          const radius = r(d.pop);
          const isSel = popup === d.name;
          return (
            <g key={d.name} style="cursor: pointer;"
               onClick={(e: any) => { e.stopPropagation(); setPopup(prev => prev === d.name ? null : d.name); }}>
              <circle cx={cx} cy={cy} r={radius}
                      fill={vulnColor(d.vuln)} stroke={isSel ? '#1e1e1e' : '#fff'}
                      stroke-width={isSel ? 2.5 : 1.5} opacity={0.75} />
              <text x={cx} y={cy + 3} text-anchor="middle" font-size="8" font-weight="600" fill="#1e1e1e"
                    style="pointer-events: none;">
                {d.name.length > 12 ? d.name.slice(0, 10) + '…' : d.name}
              </text>
            </g>
          );
        })}

        {/* Popup */}
        {(() => {
          if (!popup) return null;
          const sd = districts.find(d => d.name === popup);
          if (!sd) return null;
          const cx = x(sd.vuln);
          const cy = y(sd.rate);
          const tipW = 210, tipH = 80;
          const tipX = cx + tipW + 14 > W - 10 ? cx - tipW - 10 : cx + 12;
          const tipY = cy - tipH - 10 < 5 ? cy + 12 : cy - tipH - 8;
          return (
            <g style="pointer-events: none;">
              <rect x={tipX} y={tipY} width={tipW} height={tipH} rx="6" fill="#1e1e1e" opacity="0.95" />
              <text x={tipX + 10} y={tipY + 18} font-size="12" font-weight="700" fill="#fff">{sd.name}</text>
              <text x={tipX + 10} y={tipY + 36} font-size="10" fill="#ddd">
                {lang === 'cas' ? 'Vulnerabilidad' : 'Vulnerabilitat'}: {sd.vuln.toFixed(2)}
              </text>
              <text x={tipX + 10} y={tipY + 52} font-size="10" fill="#ddd">
                {sd.ivs} {lang === 'cas' ? 'intervenciones' : 'intervencions'} ({sd.rate.toFixed(1)}/10k hab.)
              </text>
              <text x={tipX + 10} y={tipY + 68} font-size="10" fill="#ddd">
                {lang === 'cas' ? 'Población' : 'Població'}: {sd.pop.toLocaleString('es-ES')}
              </text>
            </g>
          );
        })()}

        {/* Size legend */}
        <circle cx={W - 60} cy={padT + 20} r={8} fill="none" stroke="#ccc" stroke-width="1" />
        <text x={W - 60} y={padT + 24} text-anchor="middle" font-size="7" fill="#aaa">30k</text>
        <circle cx={W - 60} cy={padT + 50} r={16} fill="none" stroke="#ccc" stroke-width="1" />
        <text x={W - 60} y={padT + 54} text-anchor="middle" font-size="7" fill="#aaa">80k</text>
      </svg>

      {/* Key findings */}
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1rem;">
        <div style="background: #fef2f2; border-radius: 10px; padding: 1rem;">
          <p style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.75rem; font-weight: 700; color: #dc2626; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.3rem;">
            {lang === 'cas' ? '5 más vulnerables' : '5 més vulnerables'}
          </p>
          <p style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.6rem; font-weight: 800; color: #1e1e1e; line-height: 1.1;">
            {findings.top5PopPct}% <span style="font-size: 0.8rem; font-weight: 400; color: #666;">{lang === 'cas' ? 'población' : 'població'}</span>
          </p>
          <p style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.6rem; font-weight: 800; color: #dc2626; line-height: 1.1;">
            {findings.top5IvsPct}% <span style="font-size: 0.8rem; font-weight: 400; color: #666;">{lang === 'cas' ? 'intervenciones' : 'intervencions'}</span>
          </p>
        </div>
        <div style="background: #f0fdf4; border-radius: 10px; padding: 1rem;">
          <p style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.75rem; font-weight: 700; color: #22c55e; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.3rem;">
            {lang === 'cas' ? '5 menos vulnerables' : '5 menys vulnerables'}
          </p>
          <p style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.6rem; font-weight: 800; color: #1e1e1e; line-height: 1.1;">
            {findings.bot5PopPct}% <span style="font-size: 0.8rem; font-weight: 400; color: #666;">{lang === 'cas' ? 'población' : 'població'}</span>
          </p>
          <p style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.6rem; font-weight: 800; color: #22c55e; line-height: 1.1;">
            {findings.bot5IvsPct}% <span style="font-size: 0.8rem; font-weight: 400; color: #666;">{lang === 'cas' ? 'intervenciones' : 'intervencions'}</span>
          </p>
        </div>
      </div>

      <p style="color: #666; font-size: 0.78rem; margin-top: 0.75rem; line-height: 1.5; max-width: 42rem;">
        {lang === 'cas'
          ? <>El distrito más activo per cápita es <strong>{findings.mostActive?.name}</strong> ({findings.mostActive?.rate.toFixed(1)}/10k hab.), seguido de <strong>Poblats Marítims</strong>. En cambio, <strong>{findings.leastActive?.name}</strong> ({findings.leastActive?.rate.toFixed(1)}/10k) es el que menos interviene pese a tener más de 10.000 habitantes. La participación ciudadana en los plenos no refleja las necesidades territoriales: depende más del tejido asociativo y la proximidad al centro que de la vulnerabilidad real del barrio.</>
          : <>El districte més actiu per càpita és <strong>{findings.mostActive?.name}</strong> ({findings.mostActive?.rate.toFixed(1)}/10k hab.), seguit de <strong>Poblats Marítims</strong>. En canvi, <strong>{findings.leastActive?.name}</strong> ({findings.leastActive?.rate.toFixed(1)}/10k) és el que menys intervé malgrat tindre més de 10.000 habitants. La participació ciutadana als plens no reflecteix les necessitats territorials: depén més del teixit associatiu i la proximitat al centre que de la vulnerabilitat real del barri.</>}
      </p>
    </div>
  );
}

// ================================================================
// Scatter: vulnerability × interventions (barri level)
// ================================================================
function VulnIntervencionesScatter({
  data, lang,
}: {
  data: { name: string; district: string; ind_global: number; intervenciones: number }[];
  lang: 'cas' | 'val';
}) {
  const [popup, setPopup] = useState<string | null>(null);

  // Only include barris with vulnerability data and some interventions potential
  const withData = data.filter(d => d.ind_global > 0);

  const minX = Math.min(...withData.map(d => d.ind_global));
  const maxX = Math.max(...withData.map(d => d.ind_global));
  const maxY = Math.max(...withData.map(d => d.intervenciones), 1);

  const W = 600, H = 400;
  const padL = 50, padR = 20, padT = 30, padB = 52;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const x = (v: number) => padL + ((v - minX) / Math.max(0.01, maxX - minX)) * plotW;
  const y = (v: number) => padT + plotH - (v / maxY) * plotH;

  return (
    <div style="background: #fff; border-radius: 12px; padding: 1rem; border: 1px solid #eee;">
      <svg viewBox={`0 0 ${W} ${H}`} style="width: 100%; height: auto; display: block; font-family: 'Outfit', system-ui, sans-serif;"
           onClick={() => setPopup(null)}>
        {/* axes */}
        <line x1={padL} y1={padT + plotH} x2={padL + plotW} y2={padT + plotH} stroke="#ccc" stroke-width="1" />
        <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke="#ccc" stroke-width="1" />

        {/* axis labels */}
        <text x={padL + plotW / 2} y={H - 12} text-anchor="middle" font-size="11" fill="#666">
          {lang === 'cas' ? '← más vulnerable · índice global · menos vulnerable →' : '← més vulnerable · índex global · menys vulnerable →'}
        </text>
        <text x="14" y={padT + plotH / 2} text-anchor="middle" font-size="11" fill="#666"
              transform={`rotate(-90 14 ${padT + plotH / 2})`}>
          {lang === 'cas' ? '→ intervenciones al pleno' : '→ intervencions al ple'}
        </text>

        {/* ticks */}
        <text x={padL}      y={padT + plotH + 14} text-anchor="start" font-size="10" fill="#999">{minX.toFixed(1)}</text>
        <text x={padL + plotW} y={padT + plotH + 14} text-anchor="end" font-size="10" fill="#999">{maxX.toFixed(1)}</text>
        <text x={padL - 6} y={padT + plotH + 3} text-anchor="end" font-size="10" fill="#999">0</text>
        <text x={padL - 6} y={padT + 4} text-anchor="end" font-size="10" fill="#999">{maxY}</text>

        {/* interesting-region annotation */}
        <text x={padL + 6} y={padT + 14} text-anchor="start" font-size="9.5" fill="#dc2626" font-weight="600">
          {lang === 'cas' ? '↑ vulnerable y activo' : '↑ vulnerable i actiu'}
        </text>
        <text x={padL + 6} y={padT + plotH - 6} text-anchor="start" font-size="9.5" fill="#999" font-weight="600">
          {lang === 'cas' ? '↓ vulnerable y silencioso' : '↓ vulnerable i silenciós'}
        </text>

        {/* points */}
        {withData.map(d => {
          const cx = x(d.ind_global);
          const cy = y(d.intervenciones);
          const isSel = popup === d.name;
          return (
            <g key={d.name} style="cursor: pointer;"
               onClick={(e: any) => { e.stopPropagation(); setPopup(prev => prev === d.name ? null : d.name); }}>
              <circle cx={cx} cy={cy} r={isSel ? 7 : 5}
                      fill={vulnColor(d.ind_global)} stroke={isSel ? '#1e1e1e' : '#fff'}
                      stroke-width={isSel ? 2 : 1} />
              {d.intervenciones >= 5 && (
                <text x={cx + 8} y={cy + 3} font-size="9" fill="#555" style="pointer-events: none;">
                  {d.name}
                </text>
              )}
            </g>
          );
        })}

        {/* popup */}
        {(() => {
          if (!popup) return null;
          const sd = withData.find(d => d.name === popup);
          if (!sd) return null;
          const cx = x(sd.ind_global);
          const cy = y(sd.intervenciones);
          const tipW = 190, tipH = 66;
          const tipX = cx + tipW + 14 > W - 10 ? cx - tipW - 10 : cx + 12;
          const tipY = cy - tipH - 10 < 5 ? cy + 12 : cy - tipH - 8;
          return (
            <g style="pointer-events: none;">
              <rect x={tipX} y={tipY} width={tipW} height={tipH} rx="6" fill="#1e1e1e" opacity="0.95" />
              <text x={tipX + 10} y={tipY + 18} font-size="11" font-weight="700" fill="#fff">{sd.name}</text>
              <text x={tipX + 10} y={tipY + 36} font-size="10" fill="#ddd">
                {lang === 'cas' ? 'Vulnerabilidad' : 'Vulnerabilitat'}: {sd.ind_global.toFixed(1)}
              </text>
              <text x={tipX + 10} y={tipY + 52} font-size="10" fill="#ddd">
                {sd.intervenciones} {lang === 'cas' ? 'intervenciones' : 'intervencions'}
              </text>
            </g>
          );
        })()}
      </svg>

      <p style="color: #666; font-size: 0.78rem; margin-top: 0.75rem; line-height: 1.5; max-width: 42rem;">
        {lang === 'cas'
          ? <>Los puntos <span style="color: #dc2626; font-weight: 700;">rojos</span> (más vulnerables) tienden a quedarse abajo — poca presencia en el pleno. Barrios como <strong>El Calvari</strong> (1.9), <strong>Soternes</strong> (2.2) o <strong>Els Orriols</strong> (2.3) apenas intervienen. En cambio, barrios menos vulnerables como <strong>Arrancapins</strong> (3.2) o <strong>Russafa</strong> (3.3) son mucho más activos. La capacidad de llegar al pleno correlaciona más con el tejido asociativo que con la necesidad.</>
          : <>Els punts <span style="color: #dc2626; font-weight: 700;">rojos</span> (més vulnerables) tendeixen a quedar-se avall — poca presència al ple. Barris com <strong>El Calvari</strong> (1.9), <strong>Soternes</strong> (2.2) o <strong>Els Orriols</strong> (2.3) a penes intervenen. En canvi, barris menys vulnerables com <strong>Arrancapins</strong> (3.2) o <strong>Russafa</strong> (3.3) són molt més actius. La capacitat d'arribar al ple correlaciona més amb el teixit associatiu que amb la necessitat.</>}
      </p>
    </div>
  );
}
