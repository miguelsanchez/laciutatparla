import { useEffect, useRef, useState, useMemo } from 'preact/hooks';

// =====================================================================
// Types mirroring data/presupuestos_oficial.json
// =====================================================================

interface PhaseBuckets {
  total: number;
  particulares: number;
  grupos: number;
  ayuntamiento: number;
}

interface FunnelByEdition {
  presentadas: PhaseBuckets;
  desest_apoyo: PhaseBuckets | null;
  desest_viabilidad: PhaseBuckets;
  votadas: PhaseBuckets;
  seleccionadas: PhaseBuckets;
}

interface ParticipantesByEdicion {
  participantes: number;
  presentado: number | null;
  apoyado: number | null;
  votado: number | null;
}

interface DistrictSeries {
  por_edicion: Record<string, number>;
  total_ediciones: number;
  pct_pob_16: number | null;
}

interface BarriSeries {
  por_edicion: Record<string, number>;
  total_ediciones: number;
  pct_pob_16: number | null;
}

interface BudgetDistrict {
  pob_total: number;
  pob_16: number;
  renta_media: number;
  asignacion_inicial: number;
  por_poblacion: number | null;
  por_renta: number | null;
  inversion_total: number;
  eur_habitante: number;
}

interface Edicion8BarriVotes {
  votos_totales: number;
  votantes: number;
  votos_positivos: number;
  votantes_pos: number;
  votos_negativos: number;
  votantes_neg: number;
}

interface Headline {
  total_personas_unicas: number;
  pct_pob_16_mas: number;
  por_sexo: { mujer: number; hombre: number; pct_mujer: number; pct_hombre: number };
  por_edad: Record<string, number>;
  por_nacionalidad: { espanola: number; extranjera: number; pct_espanola: number; pct_extranjera: number };
}

export interface PresupuestosData {
  _meta: { ediciones: Record<string, string> };
  headline: Headline;
  participantes_por_edicion: Record<string, ParticipantesByEdicion>;
  participantes_por_distrito: Record<string, DistrictSeries>;
  participantes_por_barri: Record<string, BarriSeries>;
  funnel_propuestas: Record<string, FunnelByEdition>;
  edicion8_seleccion_por_distrito: Record<string, { votadas: { total: number; particulares: number; grupos: number }; seleccionadas: { total: number; particulares: number; grupos: number } }>;
  edicion8_votos_por_barri: Record<string, Edicion8BarriVotes>;
  distribucion_presupuestaria_2025: {
    presupuesto_total_euros: number;
    por_distrito: Record<string, BudgetDistrict>;
  };
}

interface PropostesLeaf {
  presentadas: number;
  pasa_apoyo: number;
  pasa_viabilidad: number;
  seleccionadas: number;
  apoyos_total: number;
  votos_total: number;
  presupuesto_seleccionadas: number;
}

export interface PropostesData {
  total: PropostesLeaf;
  editions: Record<string, { label: string; totals: PropostesLeaf; by_district: Record<string, PropostesLeaf>; by_barri: Record<string, PropostesLeaf>; by_tipo: Record<string, PropostesLeaf> }>;
  by_district: Record<string, PropostesLeaf>;
  by_barri: Record<string, PropostesLeaf>;
  barri_to_district: Record<string, string>;
}

export interface BarriPoblacion {
  district: string;
  poblacion_por_anyo: Record<string, number>;
}

interface Props {
  data: PresupuestosData;
  propostes: PropostesData;
  barriPoblacion: Record<string, BarriPoblacion>;
  barriToDistrict: Record<string, string>;
  lang: 'cas' | 'val';
}

// Edition → reference year for population normalisation
const EDITION_YEAR: Record<string, string> = {
  '1': '2015', '2': '2016', '3': '2017', '4': '2018',
  '5': '2019', '6': '2020', '7': '2022', '8': '2025',
};

type GeoMode = 'distrito' | 'barri';
type MapMode = 'participacion' | 'presentadas' | 'aceptadas' | 'seleccionadas' | 'eur_hab';

// =====================================================================
// Helpers
// =====================================================================

const DIST_NAMES: Record<string, string> = {
  '1': 'Ciutat Vella', '2': "L'Eixample", '3': 'Extramurs',
  '4': 'Campanar', '5': 'La Saïdia', '6': 'El Pla del Real',
  '7': "L'Olivereta", '8': 'Patraix', '9': 'Jesús',
  '10': 'Quatre Carreres', '11': 'Poblats Marítims',
  '12': 'Camins al Grau', '13': 'Algirós', '14': 'Benimaclet',
  '15': 'Rascanya', '16': 'Benicalap', '17': 'Poblats del Nord',
  '18': "Poblats de l'Oest", '19': 'Poblats del Sud',
};

const EDITIONS = ['1', '2', '3', '4', '5', '6', '7', '8'];

const MAP_LEGEND_COLORS = ['#fef3c7', '#fbbf24', '#f59e0b', '#d97706', '#c2410c'];
const MAP_LEGEND_BREAKS = [0, 0.1, 0.3, 0.5, 0.7]; // lower bound ratios for each bucket

// Orange ramp used for all choropleth modes (data is single-variable).
function colorByRatio(v: number, max: number): string {
  if (v === 0 || max === 0) return '#f5f5f5';
  const r = v / max;
  if (r > 0.7) return '#c2410c';
  if (r > 0.5) return '#d97706';
  if (r > 0.3) return '#f59e0b';
  if (r > 0.1) return '#fbbf24';
  return '#fef3c7';
}

function fmt(n: number): string {
  return n.toLocaleString('es-ES');
}

function eur(n: number): string {
  return n.toLocaleString('es-ES') + '€';
}

function fmtLegendVal(v: number, isPct: boolean, isEur: boolean): string {
  if (isPct) return v.toFixed(1) + '%';
  if (isEur) return v.toFixed(1) + '€/hab';
  if (v >= 10000) return (v / 1000).toFixed(0) + 'k';
  if (v >= 1000) return (v / 1000).toFixed(1) + 'k';
  return Math.round(v).toString();
}

// =====================================================================
// Component
// =====================================================================

export function PresupuestosExplorer({ data, propostes, barriPoblacion, barriToDistrict, lang }: Props) {
  const [geoMode, setGeoMode] = useState<GeoMode>('distrito');
  const [mapMode, setMapMode] = useState<MapMode>('participacion');
  const [mapEdition, setMapEdition] = useState<string>('todas'); // 'todas' | '1'..'8'
  const [barriNormalise, setBarriNormalise] = useState<boolean>(false); // only when geoMode=barri + participacion
  const [selectedItem, setSelectedItem] = useState<string | null>(null);

  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const layerRef = useRef<any>(null);
  const roRef = useRef<ResizeObserver | null>(null);
  const [leaflet, setLeaflet] = useState<any>(null);

  // =========================================================
  // Derived data
  // =========================================================
  const districtList = Object.keys(data.participantes_por_distrito).sort();

  // Force distrito mode when current metric has no barri-level data
  const metricAllowsBarri = mapMode === 'participacion';
  useEffect(() => {
    if (!metricAllowsBarri && geoMode === 'barri') setGeoMode('distrito');
  }, [metricAllowsBarri, geoMode]);

  // Force 'todas' when current metric doesn't support edition drilldown
  const metricAllowsEdition = mapMode !== 'eur_hab';
  useEffect(() => {
    if (!metricAllowsEdition && mapEdition !== 'todas') setMapEdition('todas');
  }, [metricAllowsEdition, mapEdition]);

  // Values per-feature for the current map mode + edition
  const { valuesByName, maxVal, unit, note } = useMemo(() => {
    const out: Record<string, number> = {};
    let unitLabel = '';
    let missingNote = '';

    const aggregateBarriToDistrict = (barriMap: Record<string, number>) => {
      const dOut: Record<string, number> = {};
      for (const d of districtList) dOut[d] = 0;
      for (const [b, val] of Object.entries(barriMap)) {
        const d = barriToDistrict[b];
        if (d) dOut[d] = (dOut[d] || 0) + val;
      }
      return dOut;
    };

    if (mapMode === 'participacion') {
      const useNormalise = geoMode === 'barri' && barriNormalise;
      if (mapEdition === 'todas') {
        // Aggregate across all editions — use the official pct_pob_16 as the
        // canonical "unique people / pob ≥16" figure; when not normalising in
        // barri mode, show total_ediciones (unique people count).
        if (geoMode === 'distrito') {
          for (const [d, v] of Object.entries(data.participantes_por_distrito)) {
            out[d] = v.pct_pob_16 || 0;
          }
          unitLabel = lang === 'cas' ? '% pob. ≥16 años (total)' : '% pob. ≥16 anys (total)';
        } else if (useNormalise) {
          for (const [b, v] of Object.entries(data.participantes_por_barri)) {
            out[b] = v.pct_pob_16 || 0;
          }
          unitLabel = lang === 'cas' ? '% pob. ≥16 años (total)' : '% pob. ≥16 anys (total)';
        } else {
          for (const [b, v] of Object.entries(data.participantes_por_barri)) {
            out[b] = v.total_ediciones || 0;
          }
          unitLabel = lang === 'cas' ? 'participantes únicos (total)' : 'participants únics (total)';
        }
      } else {
        // Specific edition
        if (geoMode === 'distrito') {
          for (const [d, v] of Object.entries(data.participantes_por_distrito)) {
            out[d] = v.por_edicion[mapEdition] || 0;
          }
          unitLabel = lang === 'cas' ? 'participantes' : 'participants';
        } else if (useNormalise) {
          const refYear = EDITION_YEAR[mapEdition];
          for (const [b, v] of Object.entries(data.participantes_por_barri)) {
            const n = v.por_edicion[mapEdition] || 0;
            const pop = barriPoblacion?.[b]?.poblacion_por_anyo?.[refYear] || 0;
            out[b] = pop > 0 ? (n / pop) * 100 : 0;
          }
          unitLabel = lang === 'cas'
            ? `% sobre habitantes (${refYear})`
            : `% sobre habitants (${refYear})`;
        } else {
          for (const [b, v] of Object.entries(data.participantes_por_barri)) {
            out[b] = v.por_edicion[mapEdition] || 0;
          }
          unitLabel = lang === 'cas' ? 'participantes' : 'participants';
        }
      }
    } else if (mapMode === 'presentadas' || mapMode === 'aceptadas') {
      // Proposals — only from CSV (editions 1-7). Edition 8 not available.
      const key: keyof PropostesLeaf = mapMode === 'presentadas' ? 'presentadas' : 'pasa_viabilidad';
      if (mapEdition === 'todas') {
        for (const [d, v] of Object.entries(propostes.by_district)) {
          out[d] = v[key] || 0;
        }
      } else if (mapEdition === '8') {
        missingNote = lang === 'cas'
          ? 'Sin datos por distrito para la 8ª edición (2025/26): el dataset abierto de propuestas todavía no incluye esta edición.'
          : 'Sense dades per districte per a la 8a edició (2025/26): el dataset obert de propostes encara no inclou aquesta edició.';
      } else {
        const ed = propostes.editions[mapEdition];
        if (ed) {
          for (const [d, v] of Object.entries(ed.by_district)) {
            out[d] = v[key] || 0;
          }
        }
      }
      unitLabel = mapMode === 'presentadas'
        ? (lang === 'cas' ? 'propuestas presentadas' : 'propostes presentades')
        : (lang === 'cas' ? 'pasan viabilidad' : 'passen viabilitat');
    } else if (mapMode === 'seleccionadas') {
      // Selected proposals. Ed 1-7 from CSV, Ed 8 from PDF report.
      if (mapEdition === 'todas') {
        for (const [d, v] of Object.entries(propostes.by_district)) {
          out[d] = v.seleccionadas || 0;
        }
        // Add Edition 8 seleccionadas from PDF
        for (const [d, v] of Object.entries(data.edicion8_seleccion_por_distrito)) {
          out[d] = (out[d] || 0) + (v.seleccionadas?.total || 0);
        }
      } else if (mapEdition === '8') {
        for (const [d, v] of Object.entries(data.edicion8_seleccion_por_distrito)) {
          out[d] = v.seleccionadas?.total || 0;
        }
      } else {
        const ed = propostes.editions[mapEdition];
        if (ed) {
          for (const [d, v] of Object.entries(ed.by_district)) {
            out[d] = v.seleccionadas || 0;
          }
        }
      }
      unitLabel = lang === 'cas' ? 'propuestas seleccionadas' : 'propostes seleccionades';
    } else {
      // eur_hab (budget) — only per distrito, only 2025
      for (const [d, v] of Object.entries(data.distribucion_presupuestaria_2025.por_distrito)) {
        out[d] = v.eur_habitante;
      }
      unitLabel = '€/habitante · 2025';
    }

    const max = Math.max(...Object.values(out), 1);
    return { valuesByName: out, maxVal: max, unit: unitLabel, note: missingNote };
  }, [data, propostes, barriPoblacion, geoMode, mapMode, mapEdition, barriNormalise, barriToDistrict, districtList, lang]);

  // Whether the current view represents a percentage (affects tooltip format)
  const isPctView = mapMode === 'participacion' && (
    mapEdition === 'todas' || (geoMode === 'barri' && barriNormalise)
  ) && !(geoMode === 'distrito' && mapEdition !== 'todas');

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

      const container = mapRef.current!;
      const ro = new ResizeObserver(() => {
        if (container.offsetWidth > 0) map.invalidateSize();
      });
      ro.observe(container);
      roRef.current = ro;
    });
    return () => {
      roRef.current?.disconnect();
      roRef.current = null;
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  // =========================================================
  // Update map layer
  // =========================================================
  useEffect(() => {
    if (!leaflet || !mapInstanceRef.current) return;
    const map = mapInstanceRef.current;
    const L = leaflet;
    if (layerRef.current) { map.removeLayer(layerRef.current); layerRef.current = null; }

    const isBarri = geoMode === 'barri';
    const upperToCanon: Record<string, string> = {};
    if (isBarri) {
      for (const b of Object.keys(barriToDistrict)) upperToCanon[b.toUpperCase()] = b;
    }
    const resolveName = (f: any): string => {
      if (isBarri) {
        const raw = f?.properties?.nombre || '';
        return upperToCanon[raw.toUpperCase()] || raw;
      }
      return DIST_NAMES[f?.properties?.coddistrit] || f?.properties?.nombre;
    };

    fetch(isBarri ? '/barris.geojson' : '/districtes.geojson').then((r) => r.json()).then((geojson) => {
      const layer = L.geoJSON(geojson, {
        style: (f: any) => {
          const name = resolveName(f);
          const v = valuesByName[name] || 0;
          const isSelected = name === selectedItem;
          return {
            fillColor: colorByRatio(v, maxVal),
            weight: isSelected ? 3 : (isBarri ? 0.8 : 1.5),
            color: isSelected ? '#d97706' : '#fff',
            fillOpacity: 0.85,
          };
        },
        onEachFeature: (f: any, l: any) => {
          const name = resolveName(f);
          const v = valuesByName[name] || 0;
          const displayV = isPctView ? `${v.toFixed(2)}%`
                         : mapMode === 'eur_hab' ? `${v.toFixed(1)} €/hab`
                         : fmt(v);
          const subtitle = isBarri && barriToDistrict[name]
            ? `<span style="font-size: 0.7rem; color: #666;">${barriToDistrict[name]}</span><br/>`
            : '';
          l.bindTooltip(
            `<div style="font-family: 'Sora', system-ui, sans-serif; text-align: center;">
              <strong>${name}</strong><br/>${subtitle}
              <span style="font-size: 1.1rem; font-weight: 800; color: #d97706;">${displayV}</span>
              <span style="font-size: 0.7rem; color: #666;"> ${unit}</span>
            </div>`,
            { direction: 'top', className: 'district-tooltip' }
          );
          l.on('mouseover', function (this: any) {
            if (isBarri || name !== selectedItem) {
              this.setStyle({ weight: 2.5, color: '#d97706', fillOpacity: 0.95 });
            }
          });
          l.on('mouseout', function (this: any) { layer.resetStyle(this); });
          l.on('click', () => setSelectedItem(name));
        },
      }).addTo(map);
      layerRef.current = layer;
    });
  }, [leaflet, mapMode, mapEdition, geoMode, valuesByName, maxVal, unit, isPctView, selectedItem, barriToDistrict]);

  // =========================================================
  // Evolución temporal — line chart SVG
  // =========================================================
  const evolucionChart = useMemo(() => {
    const edData = EDITIONS.map((ed) => data.participantes_por_edicion[ed]);
    const maxY = Math.max(
      ...edData.map((d) => d.participantes),
      ...edData.map((d) => d.votado || 0),
      ...edData.map((d) => d.apoyado || 0),
      ...edData.map((d) => d.presentado || 0),
    );

    // chart dims
    const W = 600, H = 260;
    const padL = 50, padR = 20, padT = 20, padB = 40;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;
    const x = (i: number) => padL + (i / (EDITIONS.length - 1)) * plotW;
    const y = (v: number) => padT + plotH - (v / maxY) * plotH;

    const series: { key: keyof ParticipantesByEdicion; color: string; label: string }[] = [
      { key: 'participantes', color: '#1e1e1e', label: lang === 'cas' ? 'Total' : 'Total' },
      { key: 'votado',        color: '#d97706', label: lang === 'cas' ? 'Votan' : 'Voten' },
      { key: 'apoyado',       color: '#e8562a', label: lang === 'cas' ? 'Apoyan' : 'Recolzen' },
      { key: 'presentado',    color: '#fbbf24', label: lang === 'cas' ? 'Presentan' : 'Presenten' },
    ];

    const toPath = (key: keyof ParticipantesByEdicion) => {
      const pts: [number, number][] = [];
      edData.forEach((d, i) => {
        const v = d[key];
        if (v == null) return;
        pts.push([x(i), y(v as number)]);
      });
      return pts.map(([px, py], i) => (i === 0 ? `M${px},${py}` : `L${px},${py}`)).join(' ');
    };

    return { series, toPath, x, y, W, H, padL, padT, plotW, plotH, maxY, edData };
  }, [data, lang]);

  // =========================================================
  // Funnel: one edition or aggregated across all 8
  // =========================================================
  const [funnelEdition, setFunnelEdition] = useState<string>('todas');

  // Per-edition normalised funnel: {presentadas, pasa_apoyo, pasa_viab, seleccionadas}
  const funnelByEdNormalised = useMemo(() => {
    const out: Record<string, { presentadas: number; pasa_apoyo: number; pasa_viabilidad: number; seleccionadas: number }> = {};
    for (const ed of EDITIONS) {
      const f = data.funnel_propuestas[ed];
      if (!f) continue;
      const presentadas = f.presentadas.total;
      // Ed 1 has no support phase → pasa_apoyo = presentadas
      const apoyoDrop = f.desest_apoyo?.total || 0;
      const pasa_apoyo = presentadas - apoyoDrop;
      const pasa_viabilidad = pasa_apoyo - f.desest_viabilidad.total;
      out[ed] = {
        presentadas,
        pasa_apoyo,
        pasa_viabilidad,
        seleccionadas: f.seleccionadas.total,
      };
    }
    return out;
  }, [data]);

  // Funnel numbers for the current selection
  const funnelNumbers = useMemo(() => {
    if (funnelEdition === 'todas') {
      return EDITIONS.reduce(
        (acc, ed) => {
          const e = funnelByEdNormalised[ed];
          if (!e) return acc;
          acc.presentadas += e.presentadas;
          acc.pasa_apoyo += e.pasa_apoyo;
          acc.pasa_viabilidad += e.pasa_viabilidad;
          acc.seleccionadas += e.seleccionadas;
          return acc;
        },
        { presentadas: 0, pasa_apoyo: 0, pasa_viabilidad: 0, seleccionadas: 0 },
      );
    }
    return funnelByEdNormalised[funnelEdition] || { presentadas: 0, pasa_apoyo: 0, pasa_viabilidad: 0, seleccionadas: 0 };
  }, [funnelEdition, funnelByEdNormalised]);

  return (
    <div style="font-family: 'Outfit', system-ui, sans-serif;">

      {/* ─────────────── A. Evolución temporal ─────────────── */}
      <section style="padding: 2rem 1rem; background: #fff; border-top: 1px solid #eee;">
        <div class="max-w-5xl mx-auto">
          <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.4rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 0.5rem;">
            {lang === 'cas' ? 'Evolución en 8 ediciones' : 'Evolució en 8 edicions'}
          </h3>
          <p style="color: #666; margin-bottom: 1.5rem; max-width: 42rem; line-height: 1.6; font-size: 0.9rem;">
            {lang === 'cas'
              ? 'La participación no deja de crecer desde 2015: de 5.196 personas en la primera edición a 28.473 en la octava. Cada edición tiene tres fases en las que la gente puede participar: presentar una propuesta, apoyar las ajenas y votar las que pasan el filtro técnico.'
              : 'La participació no para de créixer des de 2015: de 5.196 persones en la primera edició a 28.473 en la huitena. Cada edició té tres fases en les quals la gent pot participar: presentar una proposta, recolzar les alienes i votar les que passen el filtre tècnic.'}
          </p>

          <div style="background: #fafafa; border-radius: 12px; padding: 1rem; border: 1px solid #eee;">
            <svg viewBox={`0 0 ${evolucionChart.W} ${evolucionChart.H}`} style="width: 100%; height: auto; display: block;">
              {/* axes */}
              <line x1={evolucionChart.padL} y1={evolucionChart.padT + evolucionChart.plotH}
                    x2={evolucionChart.padL + evolucionChart.plotW} y2={evolucionChart.padT + evolucionChart.plotH}
                    stroke="#ccc" stroke-width="1" />
              <line x1={evolucionChart.padL} y1={evolucionChart.padT}
                    x2={evolucionChart.padL} y2={evolucionChart.padT + evolucionChart.plotH}
                    stroke="#ccc" stroke-width="1" />

              {/* y-axis ticks */}
              {[0, 10000, 20000, 30000].filter((v) => v <= evolucionChart.maxY + 2000).map((v) => (
                <g key={`gy-${v}`}>
                  <line x1={evolucionChart.padL} y1={evolucionChart.y(v)}
                        x2={evolucionChart.padL + evolucionChart.plotW} y2={evolucionChart.y(v)}
                        stroke="#eee" stroke-width="0.5" />
                  <text x={evolucionChart.padL - 6} y={evolucionChart.y(v) + 3}
                        text-anchor="end" font-size="10" fill="#999">{v.toLocaleString('es-ES')}</text>
                </g>
              ))}

              {/* x-axis labels — edition */}
              {EDITIONS.map((ed, i) => (
                <text key={ed} x={evolucionChart.x(i)} y={evolucionChart.padT + evolucionChart.plotH + 16}
                      text-anchor="middle" font-size="10" fill="#666">
                  {data._meta.ediciones[ed]}
                </text>
              ))}

              {/* series paths */}
              {evolucionChart.series.map((s) => (
                <path key={s.key} d={evolucionChart.toPath(s.key)}
                      fill="none" stroke={s.color} stroke-width="2.5" />
              ))}

              {/* series points + values on top line (total) */}
              {evolucionChart.edData.map((d, i) => (
                <g key={`pts-${i}`}>
                  {evolucionChart.series.map((s) => {
                    const v = d[s.key];
                    if (v == null) return null;
                    return (
                      <circle
                        key={`${s.key}-${i}`}
                        cx={evolucionChart.x(i)}
                        cy={evolucionChart.y(v as number)}
                        r={3.5}
                        fill={s.color}
                        stroke="#fff"
                        stroke-width="1.5"
                      />
                    );
                  })}
                </g>
              ))}
            </svg>

            {/* legend */}
            <div style="display: flex; flex-wrap: wrap; gap: 1rem; justify-content: center; margin-top: 0.5rem; font-size: 0.8rem;">
              {evolucionChart.series.map((s) => (
                <div key={s.key} style="display: flex; align-items: center; gap: 0.35rem;">
                  <span style={`display: inline-block; width: 14px; height: 3px; background: ${s.color}; border-radius: 2px;`} />
                  <span style="color: #333;">{s.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ─────────────── B. Mapa por distrito / barri ─────────────── */}
      <section style="padding: 2rem 1rem; background: #fff; border-top: 1px solid #eee;">
        <div class="max-w-5xl mx-auto">
          <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.4rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin: 0 0 0.75rem 0;">
            {lang === 'cas' ? 'Mapa de participación y propuestas' : 'Mapa de participació i propostes'}
          </h3>

          {/* Metric selector (primary row) */}
          <div style="display: flex; gap: 0.25rem; margin-bottom: 0.5rem; flex-wrap: wrap;">
            {(['participacion', 'presentadas', 'aceptadas', 'seleccionadas', 'eur_hab'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMapMode(m)}
                style={{
                  fontSize: '0.75rem',
                  fontWeight: mapMode === m ? '600' : '400',
                  color: mapMode === m ? '#fff' : '#666',
                  background: mapMode === m ? '#d97706' : 'none',
                  border: mapMode === m ? 'none' : '1px solid #ddd',
                  borderRadius: '100px',
                  padding: '5px 12px',
                  cursor: 'pointer',
                }}
              >
                {m === 'participacion' ? (lang === 'cas' ? '% participación' : '% participació')
                 : m === 'presentadas'  ? (lang === 'cas' ? 'Presentadas'     : 'Presentades')
                 : m === 'aceptadas'    ? (lang === 'cas' ? 'Aceptadas'       : 'Acceptades')
                 : m === 'seleccionadas'? (lang === 'cas' ? 'Seleccionadas'   : 'Seleccionades')
                 : '€/hab 2025'}
              </button>
            ))}
          </div>

          {/* Distrito/barri sub-toggle — only for participación */}
          {mapMode === 'participacion' && (
            <div style="display: flex; gap: 0.3rem; margin-bottom: 0.5rem; flex-wrap: wrap; align-items: center;">
              <span style="font-size: 0.7rem; color: #666; text-transform: uppercase; letter-spacing: 0.05em; padding: 5px 4px 5px 0;">
                {lang === 'cas' ? 'Nivel' : 'Nivell'}
              </span>
              {(['distrito', 'barri'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setGeoMode(m)}
                  style={{
                    fontSize: '0.7rem',
                    fontWeight: geoMode === m ? '600' : '400',
                    color: geoMode === m ? '#1e1e1e' : '#666',
                    background: geoMode === m ? '#fef3c7' : '#fff',
                    border: geoMode === m ? '1px solid #d97706' : '1px solid #e5e5e5',
                    borderRadius: '100px',
                    padding: '4px 10px',
                    cursor: 'pointer',
                  }}
                >
                  {m === 'distrito'
                    ? (lang === 'cas' ? 'Distrito' : 'Districte')
                    : (lang === 'cas' ? 'Barrio' : 'Barri')}
                </button>
              ))}
              {/* Normalisation toggle — shown only when barri + participacion */}
              {geoMode === 'barri' && (
                <>
                  <span style="width: 1px; background: #e5e5e5; margin: 0 0.25rem; align-self: stretch;" />
                  {([false, true] as const).map((norm) => (
                    <button
                      key={String(norm)}
                      onClick={() => setBarriNormalise(norm)}
                      style={{
                        fontSize: '0.7rem',
                        fontWeight: barriNormalise === norm ? '600' : '400',
                        color: barriNormalise === norm ? '#1e1e1e' : '#666',
                        background: barriNormalise === norm ? '#fef3c7' : '#fff',
                        border: barriNormalise === norm ? '1px solid #d97706' : '1px solid #e5e5e5',
                        borderRadius: '100px',
                        padding: '4px 10px',
                        cursor: 'pointer',
                      }}
                    >
                      {norm
                        ? (lang === 'cas' ? '% s/ población' : '% s/ població')
                        : (lang === 'cas' ? 'Absolutos' : 'Absoluts')}
                    </button>
                  ))}
                </>
              )}
            </div>
          )}

          {/* Edition chips — shown for all modes except budget */}
          {metricAllowsEdition && (
            <div style="display: flex; gap: 0.3rem; margin-bottom: 1rem; flex-wrap: wrap; padding-top: 0.25rem;">
              <span style="font-size: 0.7rem; color: #666; text-transform: uppercase; letter-spacing: 0.05em; padding: 5px 4px 5px 0;">
                {lang === 'cas' ? 'Edición' : 'Edició'}
              </span>
              {['todas', ...EDITIONS].map((ed) => {
                const active = mapEdition === ed;
                const label = ed === 'todas'
                  ? (lang === 'cas' ? 'Todas' : 'Totes')
                  : data._meta.ediciones[ed];
                return (
                  <button
                    key={ed}
                    onClick={() => setMapEdition(ed)}
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: active ? '600' : '400',
                      color: active ? '#1e1e1e' : '#666',
                      background: active ? '#fef3c7' : '#fff',
                      border: active ? '1px solid #d97706' : '1px solid #e5e5e5',
                      borderRadius: '100px',
                      padding: '4px 10px',
                      cursor: 'pointer',
                    }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          )}

          <p style="color: #666; margin-bottom: 1rem; max-width: 48rem; line-height: 1.6; font-size: 0.9rem;">
            {mapMode === 'participacion' && mapEdition === 'todas' && (lang === 'cas'
              ? 'Porcentaje de población ≥16 años que ha participado al menos una vez en alguna de las 8 ediciones. Pobles del Nord lidera con 48% — las pedanías del norte tienen un tejido social compacto. La Fontsanta y Benicalap están entre los barrios urbanos con mayor participación; Natzaret y Rascanya, entre los más bajos.'
              : 'Percentatge de població ≥16 anys que ha participat almenys una vegada en alguna de les 8 edicions. Pobles del Nord encapçala amb 48% — les pedanies del nord tenen un teixit social compacte. La Fontsanta i Benicalap estan entre els barris urbans amb major participació; Natzaret i Rascanya, entre els més baixos.')}
            {mapMode === 'participacion' && mapEdition !== 'todas' && (lang === 'cas'
              ? `Participantes en la edición ${data._meta.ediciones[mapEdition]} por lugar de residencia.`
              : `Participants en l'edició ${data._meta.ediciones[mapEdition]} per lloc de residència.`)}
            {mapMode === 'presentadas' && (lang === 'cas'
              ? 'Número de propuestas presentadas por vecinos residentes en cada distrito. Fuente: dataset abierto DecidimVLC.'
              : 'Nombre de propostes presentades per veïns residents en cada districte. Font: dataset obert DecidimVLC.')}
            {mapMode === 'aceptadas' && (lang === 'cas'
              ? 'Propuestas que han pasado el análisis técnico y presupuestario del Ayuntamiento (fase de viabilidad). Son las que llegan a votación.'
              : 'Propostes que han passat l\'anàlisi tècnica i pressupostària de l\'Ajuntament (fase de viabilitat). Són les que arriben a votació.')}
            {mapMode === 'seleccionadas' && (lang === 'cas'
              ? 'Propuestas finalmente seleccionadas por votación ciudadana para ejecutarse con presupuesto municipal.'
              : 'Propostes finalment seleccionades per votació ciutadana per executar-se amb pressupost municipal.')}
            {mapMode === 'eur_hab' && (lang === 'cas'
              ? 'Presupuesto asignado por habitante en 2025. La fórmula mezcla suelo mínimo (160k€/distrito), 50% por población y 50% inversamente proporcional a la renta — así los distritos más pobres y las pedanías reciben más por habitante. Pobles del Nord 53€/hab vs. L\'Eixample 11€/hab.'
              : 'Pressupost assignat per habitant el 2025. La fórmula barreja sòl mínim (160k€/districte), 50% per població i 50% inversament proporcional a la renda — així els districtes més pobres i les pedanies reben més per habitant. Pobles del Nord 53€/hab vs. L\'Eixample 11€/hab.')}
          </p>

          {note && (
            <p style="background: #fef3c7; border-left: 3px solid #d97706; padding: 0.6rem 0.9rem; border-radius: 6px; color: #92400e; font-size: 0.82rem; line-height: 1.5; margin-bottom: 1rem;">
              {note}
            </p>
          )}

          <div style="position: relative;">
            <div ref={mapRef} style="width: 100%; height: 440px; border-radius: 16px; overflow: hidden; background: #f5f5f5; position: relative; z-index: 0;" />
            {/* Map legend overlay */}
            {(() => {
              const isEur = mapMode === 'eur_hab';
              const isPct = isPctView;
              const legendTitle = mapMode === 'participacion'
                ? (lang === 'cas' ? '% participación' : '% participació')
                : mapMode === 'presentadas'
                  ? (lang === 'cas' ? 'Presentadas' : 'Presentades')
                  : mapMode === 'aceptadas'
                    ? (lang === 'cas' ? 'Aceptadas' : 'Acceptades')
                    : mapMode === 'seleccionadas'
                      ? (lang === 'cas' ? 'Seleccionadas' : 'Seleccionades')
                      : '€/hab';
              return (
                <div style="position: absolute; bottom: 14px; left: 14px; z-index: 1; background: rgba(255,255,255,0.93); border-radius: 8px; padding: 8px 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.12); min-width: 110px; pointer-events: none;">
                  <div style="font-family: 'Outfit', system-ui, sans-serif; font-size: 0.65rem; font-weight: 600; color: #555; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 6px;">{legendTitle}</div>
                  {MAP_LEGEND_BREAKS.map((ratio, i) => {
                    const lo = ratio * maxVal;
                    const hi = i < MAP_LEGEND_BREAKS.length - 1 ? MAP_LEGEND_BREAKS[i + 1] * maxVal : null;
                    const label = hi == null
                      ? `> ${fmtLegendVal(lo, isPct, isEur)}`
                      : i === 0
                        ? `0 – ${fmtLegendVal(hi, isPct, isEur)}`
                        : `${fmtLegendVal(lo, isPct, isEur)} – ${fmtLegendVal(hi, isPct, isEur)}`;
                    return (
                      <div key={i} style="display: flex; align-items: center; gap: 6px; margin-bottom: 3px;">
                        <span style={`display: inline-block; width: 12px; height: 12px; border-radius: 3px; background: ${MAP_LEGEND_COLORS[i]}; flex-shrink: 0;`} />
                        <span style="font-family: 'Outfit', system-ui, sans-serif; font-size: 0.68rem; color: #444; white-space: nowrap;">{label}</span>
                      </div>
                    );
                  }).reverse()}
                </div>
              );
            })()}
          </div>
        </div>
      </section>

      {/* ─────────────── C. Funnel — interactive by edition ─────────────── */}
      <section style="padding: 2rem 1rem; background: #fafafa; border-top: 1px solid #eee;">
        <div class="max-w-5xl mx-auto">
          <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.4rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 0.5rem;">
            {lang === 'cas' ? 'El embudo de las propuestas' : "L'embut de les propostes"}
          </h3>
          <p style="color: #666; margin-bottom: 1.25rem; max-width: 42rem; line-height: 1.6; font-size: 0.9rem;">
            {lang === 'cas'
              ? 'Presentar una propuesta no garantiza que se vote. Dos filtros reducen la lista: el apoyo ciudadano mínimo (30 firmas por propuesta a partir de la 2ª edición) y el análisis técnico y presupuestario del Ayuntamiento. Elige una edición concreta o el agregado de todas para ver cómo ha evolucionado el embudo desde 2015.'
              : 'Presentar una proposta no garanteix que es vote. Dos filtres redueixen la llista: el suport ciutadà mínim (30 signatures per proposta a partir de la 2a edició) i l\'anàlisi tècnica i pressupostària de l\'Ajuntament. Tria una edició concreta o l\'agregat de totes per vore com ha evolucionat l\'embut des de 2015.'}
          </p>

          {/* Edition chips */}
          <div style="display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1.25rem;">
            {['todas', ...EDITIONS].map((ed) => {
              const active = funnelEdition === ed;
              const label = ed === 'todas'
                ? (lang === 'cas' ? 'Todas · 2015-2026' : 'Totes · 2015-2026')
                : data._meta.ediciones[ed];
              return (
                <button
                  key={ed}
                  onClick={() => setFunnelEdition(ed)}
                  style={{
                    fontFamily: "'Outfit', system-ui, sans-serif",
                    fontSize: '0.75rem',
                    fontWeight: active ? '600' : '400',
                    color: active ? '#fff' : '#666',
                    background: active ? '#d97706' : '#fff',
                    border: active ? 'none' : '1px solid #ddd',
                    borderRadius: '100px',
                    padding: '5px 12px',
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>

          <FunnelBars numbers={funnelNumbers} lang={lang} />

          {/* Evolution mini-chart: 4 metrics across 8 editions */}
          <div style="margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid #e5e5e5;">
            <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.95rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.5rem;">
              {lang === 'cas' ? 'Evolución de las 4 métricas por edición' : 'Evolució de les 4 mètriques per edició'}
            </h4>
            <p style="color: #666; font-size: 0.8rem; margin-bottom: 1rem; line-height: 1.5;">
              {lang === 'cas'
                ? 'El volumen de propuestas presentadas ha crecido 4.5× (619 → 2.776) y las seleccionadas 2.3× (109 → 248), pero la proporción que sobrevive ha caído del 18% al 9%.'
                : 'El volum de propostes presentades ha crescut 4.5× (619 → 2.776) i les seleccionades 2.3× (109 → 248), però la proporció que sobreviu ha caigut del 18% al 9%.'}
            </p>
            <FunnelEvolution data={funnelByEdNormalised} editions={data._meta.ediciones} lang={lang} selectedEdition={funnelEdition} onSelect={setFunnelEdition} />
          </div>
        </div>
      </section>

      {/* ─────────────── D. Sociodemografía ─────────────── */}
      <section style="padding: 2rem 1rem; background: #fff; border-top: 1px solid #eee;">
        <div class="max-w-5xl mx-auto">
          <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.4rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 0.5rem;">
            {lang === 'cas' ? '¿Quién participa?' : 'Qui participa?'}
          </h3>
          <p style="color: #666; margin-bottom: 1.5rem; max-width: 42rem; line-height: 1.6; font-size: 0.9rem;">
            {lang === 'cas'
              ? 'Perfil de las 80.091 personas únicas que han participado al menos una vez en alguna de las 8 ediciones. Las mujeres participan 7% más que los hombres; la franja 35-54 años multiplica por cinco la participación de los mayores de 75. La participación extranjera es cuatro veces menor que la española.'
              : 'Perfil de les 80.091 persones úniques que han participat almenys una vegada en alguna de les 8 edicions. Les dones participen un 7% més que els homes; la franja 35-54 anys multiplica per cinc la participació dels majors de 75. La participació estrangera és quatre vegades menor que l\'espanyola.'}
          </p>

          <Demografia headline={data.headline} lang={lang} />
        </div>
      </section>

      {/* ─────────────── E. Lecturas ─────────────── */}
      <section style="padding: 2rem 1rem; background: #fafafa; border-top: 1px solid #eee;">
        <div class="max-w-5xl mx-auto">
          <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.4rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 1rem;">
            {lang === 'cas' ? 'Lecturas destacadas' : 'Lectures destacades'}
          </h3>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ReadCard
              color="#d97706"
              title={lang === 'cas' ? 'Las pedanías del norte votan más que nadie' : 'Les pedanies del nord voten més que ningú'}
              body={lang === 'cas'
                ? 'Pobles del Nord tiene una participación acumulada del 48% de su población ≥16 años — el triple que la media de la ciudad (11.6%). Son 7 barrios pequeños donde el tejido vecinal y familiar pesa mucho. Pero en las intervenciones al pleno apenas aparecen: 1 sola intervención en 7 años.'
                : 'Pobles del Nord té una participació acumulada del 48% de la seua població ≥16 anys — el triple que la mitjana de la ciutat (11.6%). Són 7 barris xicotets on el teixit veïnal i familiar pesa molt. Però en les intervencions al ple a penes apareixen: 1 sola intervenció en 7 anys.'}
            />
            <ReadCard
              color="#e8562a"
              title={lang === 'cas' ? 'El 48% de las propuestas se caen por falta de apoyos' : 'El 48% de les propostes cauen per falta de suports'}
              body={lang === 'cas'
                ? 'En la 8ª edición, de las 2.776 propuestas presentadas, 1.335 (48%) se quedaron sin llegar a fase de viabilidad por no conseguir los 30 apoyos mínimos. La ciudadanía ejerce un filtro previo al técnico.'
                : 'En la 8a edició, de les 2.776 propostes presentades, 1.335 (48%) es van quedar sense arribar a la fase de viabilitat per no aconseguir els 30 suports mínims. La ciutadania exerceix un filtre previ al tècnic.'}
            />
            <ReadCard
              color="#1e1e1e"
              title={lang === 'cas' ? '16 millones redistribuidos por renta' : '16 milions redistribuïts per renda'}
              body={lang === 'cas'
                ? 'El presupuesto 2025 (16M€) se reparte con un sesgo redistributivo: L\'Olivereta (renta media 12.338€) recibe 1.18M€; L\'Eixample (renta 21.841€) recibe 486k€. Más del doble para el distrito con menos renta.'
                : 'El pressupost 2025 (16M€) es reparteix amb un biaix redistributiu: L\'Olivereta (renda mitjana 12.338€) rep 1.18M€; L\'Eixample (renda 21.841€) rep 486k€. Més del doble per al districte amb menys renda.'}
            />
            <ReadCard
              color="#1e1e1e"
              title={lang === 'cas' ? 'Ellas participan, ellos proponen' : 'Elles participen, ells proposen'}
              body={lang === 'cas'
                ? 'En la fase global de participación, las mujeres son el 54.7% y los hombres el 45.3%. Pero en la fase de PRESENTAR propuestas (la más exigente en tiempo y conocimiento), los hombres son el 55% y las mujeres el 45%. El sesgo se invierte.'
                : 'En la fase global de participació, les dones són el 54.7% i els homes el 45.3%. Però en la fase de PRESENTAR propostes (la més exigent en temps i coneixement), els homes són el 55% i les dones el 45%. El biaix s\'inverteix.'}
            />
          </div>
        </div>
      </section>

    </div>
  );
}

// =====================================================================
// Sub-components
// =====================================================================

interface FunnelNumbers {
  presentadas: number;
  pasa_apoyo: number;
  pasa_viabilidad: number;
  seleccionadas: number;
}

function FunnelBars({ numbers, lang }: { numbers: FunnelNumbers; lang: 'cas' | 'val' }) {
  const rows = [
    { key: 'presentadas',     color: '#1e1e1e', label: lang === 'cas' ? 'Presentadas'                : 'Presentades' },
    { key: 'pasa_apoyo',      color: '#d97706', label: lang === 'cas' ? 'Pasan fase de apoyo'        : 'Passen fase de suport' },
    { key: 'pasa_viabilidad', color: '#e8562a', label: lang === 'cas' ? 'Pasan viabilidad técnica'   : 'Passen viabilitat tècnica' },
    { key: 'seleccionadas',   color: '#c2410c', label: lang === 'cas' ? 'Seleccionadas para ejecutar': 'Seleccionades per executar' },
  ] as const;

  const presentadas = numbers.presentadas || 1;

  return (
    <div style="display: grid; gap: 0.5rem;">
      {rows.map((r, i) => {
        const c = (numbers as any)[r.key] as number;
        const prev: number = i === 0 ? c : (numbers as any)[rows[i - 1].key];
        const dropPct = i === 0 ? 0 : prev === 0 ? 0 : ((prev - c) / prev) * 100;
        const w = (c / presentadas) * 100;
        const pctOfTotal = (c / presentadas) * 100;
        return (
          <div key={r.key}>
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.25rem; gap: 0.5rem; flex-wrap: wrap;">
              <span style="font-size: 0.9rem; font-weight: 500; color: #1e1e1e;">{r.label}</span>
              <span style="font-family: 'Sora', system-ui, sans-serif; font-weight: 700; color: #1e1e1e;">
                {fmt(c)}
                <span style="font-size: 0.75rem; color: #666; font-weight: 400; margin-left: 0.5rem;">
                  {i === 0 ? '(100%)' : `(${pctOfTotal.toFixed(0)}% · −${dropPct.toFixed(0)}% vs anterior)`}
                </span>
              </span>
            </div>
            <div style="background: #eee; border-radius: 6px; height: 28px; overflow: hidden;">
              <div style={`background: ${r.color}; height: 100%; width: ${w}%; transition: width 0.4s ease;`} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FunnelEvolution({
  data, editions, lang, selectedEdition, onSelect,
}: {
  data: Record<string, FunnelNumbers>;
  editions: Record<string, string>;
  lang: 'cas' | 'val';
  selectedEdition: string;
  onSelect: (ed: string) => void;
}) {
  const EDS = Object.keys(editions);

  const series = [
    { key: 'presentadas' as const,     color: '#1e1e1e', label: lang === 'cas' ? 'Presentadas' : 'Presentades' },
    { key: 'pasa_apoyo' as const,      color: '#d97706', label: lang === 'cas' ? 'Pasan apoyo' : 'Passen suport' },
    { key: 'pasa_viabilidad' as const, color: '#e8562a', label: lang === 'cas' ? 'Pasan viabilidad' : 'Passen viabilitat' },
    { key: 'seleccionadas' as const,   color: '#c2410c', label: lang === 'cas' ? 'Seleccionadas' : 'Seleccionades' },
  ];

  const maxY = Math.max(
    ...EDS.flatMap((ed) => series.map((s) => data[ed]?.[s.key] || 0)),
  );

  const W = 640, H = 220;
  const padL = 40, padR = 16, padT = 16, padB = 36;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const x = (i: number) => padL + (i / (EDS.length - 1)) * plotW;
  const y = (v: number) => padT + plotH - (v / maxY) * plotH;

  const pathFor = (key: keyof FunnelNumbers) =>
    EDS.map((ed, i) => {
      const v = data[ed]?.[key] || 0;
      return `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`;
    }).join(' ');

  return (
    <div style="background: #fff; border-radius: 12px; padding: 1rem; border: 1px solid #eee;">
      <svg viewBox={`0 0 ${W} ${H}`} style="width: 100%; height: auto; display: block;">
        {/* axes */}
        <line x1={padL} y1={padT + plotH} x2={padL + plotW} y2={padT + plotH} stroke="#ccc" stroke-width="1" />
        <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke="#ccc" stroke-width="1" />
        {/* y ticks */}
        {[0, 1000, 2000, 3000].filter((v) => v <= maxY + 200).map((v) => (
          <g key={`gy-${v}`}>
            <line x1={padL} y1={y(v)} x2={padL + plotW} y2={y(v)} stroke="#eee" stroke-width="0.5" />
            <text x={padL - 6} y={y(v) + 3} text-anchor="end" font-size="10" fill="#999">{v.toLocaleString('es-ES')}</text>
          </g>
        ))}
        {/* x labels */}
        {EDS.map((ed, i) => (
          <text key={ed} x={x(i)} y={padT + plotH + 16} text-anchor="middle" font-size="9.5" fill="#666">
            {editions[ed]}
          </text>
        ))}
        {/* series paths */}
        {series.map((s) => (
          <path key={s.key} d={pathFor(s.key)} fill="none" stroke={s.color} stroke-width="2" />
        ))}
        {/* hover/click circles per edition */}
        {EDS.map((ed, i) => {
          const isSel = selectedEdition === ed;
          return (
            <g key={`pts-${ed}`} style="cursor: pointer;" onClick={() => onSelect(ed)}>
              {/* wide invisible hit area */}
              <rect x={x(i) - (plotW / EDS.length / 2)} y={padT}
                    width={plotW / EDS.length} height={plotH}
                    fill={isSel ? 'rgba(217, 119, 6, 0.08)' : 'transparent'}
                    stroke="none" />
              {series.map((s) => {
                const v = data[ed]?.[s.key] || 0;
                return (
                  <circle key={`${s.key}-${ed}`} cx={x(i)} cy={y(v)} r={isSel ? 4 : 3}
                          fill={s.color} stroke="#fff" stroke-width="1.5" />
                );
              })}
            </g>
          );
        })}
      </svg>
      <div style="display: flex; flex-wrap: wrap; gap: 1rem; justify-content: center; margin-top: 0.5rem; font-size: 0.78rem;">
        {series.map((s) => (
          <div key={s.key} style="display: flex; align-items: center; gap: 0.35rem;">
            <span style={`display: inline-block; width: 14px; height: 3px; background: ${s.color}; border-radius: 2px;`} />
            <span style="color: #333;">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Demografia({ headline, lang }: { headline: Headline; lang: 'cas' | 'val' }) {
  const ageOrder = ['16-24', '25-34', '35-44', '45-54', '55-64', '65-74', '75+'];
  const maxAge = Math.max(...ageOrder.map((k) => headline.por_edad[k] || 0));

  const sexLabels = lang === 'cas'
    ? { mujer: 'Mujeres', hombre: 'Hombres' }
    : { mujer: 'Dones', hombre: 'Homes' };
  const natLabels = lang === 'cas'
    ? { espanola: 'Española', extranjera: 'Extranjera' }
    : { espanola: 'Espanyola', extranjera: 'Estrangera' };

  return (
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Sexo */}
      <div style="background: #fafafa; border-radius: 12px; padding: 1.25rem; border: 1px solid #eee;">
        <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.85rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.75rem;">
          {lang === 'cas' ? 'Sexo' : 'Sexe'}
        </h4>
        <div style="display: grid; gap: 0.5rem;">
          {(['mujer', 'hombre'] as const).map((k) => {
            const n = headline.por_sexo[k];
            const pct = (k === 'mujer' ? headline.por_sexo.pct_mujer : headline.por_sexo.pct_hombre);
            return (
              <div key={k}>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.2rem; font-size: 0.8rem;">
                  <span>{sexLabels[k]}</span>
                  <span style="font-family: 'Sora', system-ui, sans-serif; font-weight: 700;">
                    {fmt(n)} <span style="color: #666; font-size: 0.7rem; font-weight: 400;">({pct}%)</span>
                  </span>
                </div>
                <div style="background: #fef1ec; height: 8px; border-radius: 4px; overflow: hidden;">
                  <div style={`height: 100%; width: ${pct}%; background: ${k === 'mujer' ? '#d97706' : '#fbbf24'};`} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Edad */}
      <div style="background: #fafafa; border-radius: 12px; padding: 1.25rem; border: 1px solid #eee;">
        <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.85rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.75rem;">
          {lang === 'cas' ? 'Edad' : 'Edat'}
        </h4>
        <div style="display: grid; gap: 0.3rem;">
          {ageOrder.map((age) => {
            const n = headline.por_edad[age] || 0;
            return (
              <div key={age}>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.15rem; font-size: 0.75rem;">
                  <span>{age}</span>
                  <span style="font-family: 'Sora', system-ui, sans-serif; font-weight: 700;">{fmt(n)}</span>
                </div>
                <div style="background: #fef3c7; height: 6px; border-radius: 3px; overflow: hidden;">
                  <div style={`height: 100%; width: ${(n / maxAge) * 100}%; background: #d97706;`} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Nacionalidad */}
      <div style="background: #fafafa; border-radius: 12px; padding: 1.25rem; border: 1px solid #eee;">
        <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.85rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.75rem;">
          {lang === 'cas' ? 'Nacionalidad' : 'Nacionalitat'}
        </h4>
        <div style="display: grid; gap: 0.5rem;">
          {(['espanola', 'extranjera'] as const).map((k) => {
            const n = headline.por_nacionalidad[k];
            const pct = k === 'espanola' ? headline.por_nacionalidad.pct_espanola : headline.por_nacionalidad.pct_extranjera;
            return (
              <div key={k}>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.2rem; font-size: 0.8rem;">
                  <span>{natLabels[k]}</span>
                  <span style="font-family: 'Sora', system-ui, sans-serif; font-weight: 700;">
                    {fmt(n)} <span style="color: #666; font-size: 0.7rem; font-weight: 400;">({pct}%)</span>
                  </span>
                </div>
                <div style="background: #fef1ec; height: 8px; border-radius: 4px; overflow: hidden;">
                  <div style={`height: 100%; width: ${pct}%; background: ${k === 'espanola' ? '#d97706' : '#fbbf24'};`} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ReadCard({ color, title, body }: { color: string; title: string; body: string }) {
  return (
    <div style={`background: #fff; border-left: 3px solid ${color}; border-radius: 8px; padding: 1rem 1.25rem; border-top: 1px solid #eee; border-right: 1px solid #eee; border-bottom: 1px solid #eee;`}>
      <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.95rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.5rem;">{title}</h4>
      <p style="margin: 0; color: #444; font-size: 0.85rem; line-height: 1.55;">{body}</p>
    </div>
  );
}
