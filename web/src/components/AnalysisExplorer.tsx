import { useEffect, useRef, useState, useMemo } from 'preact/hooks';

interface Intervention {
  id: string;
  fecha: string;
  entitat: string;
  entitat_id: string;
  tipus_entitat: string;
  temes_v2: Record<string, string[]>;
  districtes: string[];
  zones: string[];
}

interface Mandat {
  id: string;
  legislatura: string;
  inici: string;
  fi: string | null;
  alcalde: string;
}

interface QuejasTipoData {
  total: number;
  total_sin_barri?: number;
  total_sin_districte?: number;
  districts: Record<string, { total: number; by_year: Record<string, number> }>;
  barris?: Record<string, { total: number; by_year: Record<string, number> }>;
  temas: Record<string, { total: number; by_year: Record<string, number> }>;
  by_year_district_tema: Record<string, Record<string, Record<string, number>>>;
}

interface QuejasData {
  total: number;
  years: string[];
  by_tipo: { queja: QuejasTipoData; sugerencia: QuejasTipoData };
}

interface EntityLookup {
  [id: string]: { nom_cas: string; nom_val: string };
}

interface Props {
  intervencions: Intervention[];
  quejas: QuejasData;
  mandats: Mandat[];
  entityNames: EntityLookup;
  lang: 'cas' | 'val';
  cat_labels: Record<string, string>;
  entitats_path: string;
  barriToDistrict: Record<string, string>;
  // When true, render a quejas-only narrative: hide intervention columns,
  // scatter, organization index, and cross-channel "Lecturas".
  hideIntervenciones?: boolean;
  // When true, restrict the time range to years where quejas data exists (overlap
  // period) without hiding interventions from the visualisation. Use in cross-
  // channel views where showing pre-quejas years would be misleading.
  clampToQuejas?: boolean;
}

const DIST_NAMES: Record<string, string> = {
  '1': 'Ciutat Vella', '2': "L'Eixample", '3': 'Extramurs',
  '4': 'Campanar', '5': 'La Saïdia', '6': 'El Pla del Real',
  '7': "L'Olivereta", '8': 'Patraix', '9': 'Jesús',
  '10': 'Quatre Carreres', '11': 'Poblats Marítims',
  '12': 'Camins al Grau', '13': 'Algirós', '14': 'Benimaclet',
  '15': 'Rascanya', '16': 'Benicalap', '17': 'Poblats del Nord',
  '18': "Poblats de l'Oest", '19': 'Poblats del Sud',
};

// Color scales
function quejasColor(v: number, max: number): string {
  if (v === 0) return '#f5f5f5';
  const r = v / max;
  if (r > 0.7) return '#c2410c';
  if (r > 0.5) return '#e8562a';
  if (r > 0.3) return '#f59e0b';
  if (r > 0.1) return '#fbbf24';
  return '#fef3c7';
}

function ivColor(v: number, max: number): string {
  if (v === 0) return '#f5f5f5';
  const r = v / max;
  if (r > 0.7) return '#1e1e1e';
  if (r > 0.5) return '#3a3a3a';
  if (r > 0.3) return '#5a5a5a';
  if (r > 0.1) return '#666';
  return '#ddd';
}

function ratioColor(v: number, max: number): string {
  if (v === 0) return '#f5f5f5';
  const r = v / max;
  if (r > 0.7) return '#6b21a8';
  if (r > 0.5) return '#8b5cf6';
  if (r > 0.3) return '#a78bfa';
  if (r > 0.1) return '#c4b5fd';
  return '#ede9fe';
}

const EXCLUDE_TEMAS = new Set([
  'Agradecimientos', 'Otros', 'No consta', 'Distinto ámbito competencial',
]);

type MapMode = 'quejas' | 'intervencions' | 'ratio';
type TipoFilter = 'todas' | 'queja' | 'sugerencia';

const LEGEND_COLORS: Record<MapMode, string[]> = {
  quejas:        ['#fef3c7', '#fbbf24', '#f59e0b', '#e8562a', '#c2410c'],
  intervencions: ['#ddd',    '#aaa',    '#777',    '#444',    '#1e1e1e'],
  ratio:         ['#ede9fe', '#c4b5fd', '#a78bfa', '#8b5cf6', '#6b21a8'],
};

function fmtLegendVal(v: number, mode: MapMode): string {
  if (mode === 'ratio') return v.toFixed(1) + '‰';
  if (v >= 10000) return (v / 1000).toFixed(0) + 'k';
  if (v >= 1000) return (v / 1000).toFixed(1) + 'k';
  return Math.round(v).toString();
}

export function AnalysisExplorer({
  intervencions,
  quejas,
  mandats,
  entityNames,
  lang,
  cat_labels,
  entitats_path,
  barriToDistrict,
  hideIntervenciones = false,
  clampToQuejas = false,
}: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const layerRef = useRef<any>(null);
  const roRef = useRef<ResizeObserver | null>(null);
  const [leaflet, setLeaflet] = useState<any>(null);

  const allYears = useMemo(() => {
    const s = new Set<number>();
    for (const y of quejas.years) s.add(parseInt(y));
    if (!hideIntervenciones && !clampToQuejas) {
      for (const iv of intervencions) s.add(parseInt(iv.fecha.slice(0, 4)));
    }
    return [...s].sort();
  }, [quejas, intervencions, hideIntervenciones, clampToQuejas]);

  const minYear = allYears[0] || 2019;
  const maxYear = allYears[allYears.length - 1] || 2026;

  const [yearRange, setYearRange] = useState<[number, number]>([minYear, maxYear]);
  const [activeMandat, setActiveMandat] = useState<string | null>(null);
  const [mapMode, setMapMode] = useState<MapMode>('quejas');
  // If the component is running in quejas-only mode, lock mapMode to 'quejas'.
  useEffect(() => {
    if (hideIntervenciones && mapMode !== 'quejas') setMapMode('quejas');
  }, [hideIntervenciones, mapMode]);
  const [tipoFilter, setTipoFilter] = useState<TipoFilter>('todas');
  const [selectedDistrict, setSelectedDistrict] = useState<string>('Poblats del Sud');
  const [popupDistrict, setPopupDistrict] = useState<string | null>(null);
  // 'distrito' shows 19 districts; 'barri' unfolds to all barrios with data.
  // Only affects section A (volume comparison).
  const [geoMode, setGeoMode] = useState<'distrito' | 'barri'>('distrito');
  // Section A table sort: click-cycle unsorted → desc → asc → unsorted.
  const [sortCol, setSortCol] = useState<'name' | 'quejas' | 'intervencions' | 'ratio' | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Helper: combine queja + sugerencia counts based on tipoFilter
  function getTipoData(): { districts: Record<string, {by_year: Record<string, number>}>, barris: Record<string, {by_year: Record<string, number>}>, total_sin_barri: number, total_sin_districte: number, temas: Record<string, {by_year: Record<string, number>}>, by_year_district_tema: Record<string, Record<string, Record<string, number>>> } {
    if (tipoFilter !== 'todas') {
      const d = quejas.by_tipo[tipoFilter];
      return {
        districts: d.districts,
        barris: d.barris || {},
        total_sin_barri: d.total_sin_barri || 0,
        total_sin_districte: d.total_sin_districte || 0,
        temas: d.temas,
        by_year_district_tema: d.by_year_district_tema,
      };
    }
    // merge both
    const qjs = quejas.by_tipo.queja;
    const sug = quejas.by_tipo.sugerencia;
    const merged = {
      districts: {} as any,
      barris: {} as any,
      total_sin_barri: (qjs.total_sin_barri || 0) + (sug.total_sin_barri || 0),
      total_sin_districte: (qjs.total_sin_districte || 0) + (sug.total_sin_districte || 0),
      temas: {} as any,
      by_year_district_tema: {} as any,
    };
    const allDists = new Set([...Object.keys(qjs.districts), ...Object.keys(sug.districts)]);
    for (const d of allDists) {
      const merged_years: Record<string, number> = {};
      for (const y of [...Object.keys(qjs.districts[d]?.by_year || {}), ...Object.keys(sug.districts[d]?.by_year || {})]) {
        merged_years[y] = (qjs.districts[d]?.by_year[y] || 0) + (sug.districts[d]?.by_year[y] || 0);
      }
      merged.districts[d] = { by_year: merged_years };
    }
    const qBarris = qjs.barris || {};
    const sBarris = sug.barris || {};
    const allBarris = new Set([...Object.keys(qBarris), ...Object.keys(sBarris)]);
    for (const b of allBarris) {
      const merged_years: Record<string, number> = {};
      for (const y of [...Object.keys(qBarris[b]?.by_year || {}), ...Object.keys(sBarris[b]?.by_year || {})]) {
        merged_years[y] = (qBarris[b]?.by_year[y] || 0) + (sBarris[b]?.by_year[y] || 0);
      }
      merged.barris[b] = { by_year: merged_years };
    }
    const allTemas = new Set([...Object.keys(qjs.temas), ...Object.keys(sug.temas)]);
    for (const t of allTemas) {
      const merged_years: Record<string, number> = {};
      for (const y of [...Object.keys(qjs.temas[t]?.by_year || {}), ...Object.keys(sug.temas[t]?.by_year || {})]) {
        merged_years[y] = (qjs.temas[t]?.by_year[y] || 0) + (sug.temas[t]?.by_year[y] || 0);
      }
      merged.temas[t] = { by_year: merged_years };
    }
    const allYears = new Set([...Object.keys(qjs.by_year_district_tema), ...Object.keys(sug.by_year_district_tema)]);
    for (const y of allYears) {
      merged.by_year_district_tema[y] = {};
      const allDs = new Set([...Object.keys(qjs.by_year_district_tema[y] || {}), ...Object.keys(sug.by_year_district_tema[y] || {})]);
      for (const d of allDs) {
        merged.by_year_district_tema[y][d] = {};
        const qTemas = qjs.by_year_district_tema[y]?.[d] || {};
        const sTemas = sug.by_year_district_tema[y]?.[d] || {};
        for (const t of new Set([...Object.keys(qTemas), ...Object.keys(sTemas)])) {
          merged.by_year_district_tema[y][d][t] = (qTemas[t] || 0) + (sTemas[t] || 0);
        }
      }
    }
    return merged;
  }

  const tipoData = useMemo(() => getTipoData(), [tipoFilter, quejas]);

  // Filter interventions by year
  const filteredIvs = useMemo(() => {
    const am = activeMandat ? mandats.find(m => m.id === activeMandat) : null;
    return intervencions.filter((iv) => {
      if (am) {
        if (iv.fecha < am.inici) return false;
        if (am.fi && iv.fecha > am.fi) return false;
      } else {
        const y = parseInt(iv.fecha.slice(0, 4));
        if (y < yearRange[0] || y > yearRange[1]) return false;
      }
      return true;
    });
  }, [intervencions, yearRange, activeMandat, mandats]);

  // Years string array for queja filtering
  const yearsFiltered = useMemo(() => {
    const am = activeMandat ? mandats.find(m => m.id === activeMandat) : null;
    if (am) {
      const from = parseInt(am.inici.slice(0, 4));
      const to = am.fi ? parseInt(am.fi.slice(0, 4)) : maxYear;
      return allYears.filter(y => y >= from && y <= to).map(String);
    }
    return allYears.filter(y => y >= yearRange[0] && y <= yearRange[1]).map(String);
  }, [allYears, yearRange, activeMandat, mandats, maxYear]);

  // Quejas per district (filtered by year and tipo)
  const quejasByDistrict = useMemo(() => {
    const res: Record<string, number> = {};
    for (const [d, info] of Object.entries(tipoData.districts)) {
      let sum = 0;
      for (const y of yearsFiltered) {
        sum += info.by_year[y] || 0;
      }
      res[d] = sum;
    }
    return res;
  }, [tipoData, yearsFiltered]);

  // Helper: effective districts for an intervention = explicit districtes
  // ∪ districts derived from zones (barris) via barriToDistrict map.
  // Deduplicated so one intervention counts once per district.
  function effectiveDistricts(iv: Intervention): Set<string> {
    const s = new Set<string>();
    for (const d of iv.districtes || []) s.add(d);
    for (const z of iv.zones || []) {
      const d = barriToDistrict[z];
      if (d) s.add(d);
    }
    return s;
  }

  // Interventions per district (filtered)
  const ivsByDistrict = useMemo(() => {
    const res: Record<string, number> = {};
    for (const iv of filteredIvs) {
      for (const d of effectiveDistricts(iv)) {
        res[d] = (res[d] || 0) + 1;
      }
    }
    return res;
  }, [filteredIvs, barriToDistrict]);

  // Queja temas (filtered by year and tipo)
  const quejaTemasFiltered = useMemo(() => {
    const res: Record<string, number> = {};
    for (const [t, info] of Object.entries(tipoData.temas)) {
      if (EXCLUDE_TEMAS.has(t)) continue;
      let sum = 0;
      for (const y of yearsFiltered) {
        sum += info.by_year[y] || 0;
      }
      if (sum > 0) res[t] = sum;
    }
    return res;
  }, [tipoData, yearsFiltered]);

  // Intervention categories (filtered)
  const ivCategoriesFiltered = useMemo(() => {
    const res: Record<string, number> = {};
    for (const iv of filteredIvs) {
      for (const cat of Object.keys(iv.temes_v2 || {})) {
        res[cat] = (res[cat] || 0) + 1;
      }
    }
    return res;
  }, [filteredIvs]);

  // District data combined
  const districtData = useMemo(() => {
    const allDistricts = new Set([...Object.keys(tipoData.districts), ...Object.keys(ivsByDistrict)]);
    return [...allDistricts].map(d => {
      const q = quejasByDistrict[d] || 0;
      const i = ivsByDistrict[d] || 0;
      const ratio = q ? i / q * 1000 : 0;
      return { name: d, quejas: q, intervencions: i, ratio };
    }).sort((a, b) => b.ratio - a.ratio);
  }, [tipoData, quejasByDistrict, ivsByDistrict]);

  // Quejas per barri (filtered by year and tipo)
  const quejasByBarri = useMemo(() => {
    const res: Record<string, number> = {};
    for (const [b, info] of Object.entries(tipoData.barris || {})) {
      let sum = 0;
      for (const y of yearsFiltered) sum += info.by_year[y] || 0;
      if (sum > 0) res[b] = sum;
    }
    return res;
  }, [tipoData, yearsFiltered]);

  // Interventions per barri (filtered). Count each intervention once per zone.
  const ivsByBarri = useMemo(() => {
    const res: Record<string, number> = {};
    for (const iv of filteredIvs) {
      const seen = new Set<string>();
      for (const z of iv.zones || []) {
        if (seen.has(z)) continue;
        seen.add(z);
        res[z] = (res[z] || 0) + 1;
      }
    }
    return res;
  }, [filteredIvs]);

  // Combined barri data (same shape as districtData, sorted by quejas desc)
  const barriData = useMemo(() => {
    const allBarris = new Set([...Object.keys(quejasByBarri), ...Object.keys(ivsByBarri)]);
    return [...allBarris].map(b => {
      const q = quejasByBarri[b] || 0;
      const i = ivsByBarri[b] || 0;
      const ratio = q ? i / q * 1000 : 0;
      return { name: b, district: barriToDistrict[b] || '', quejas: q, intervencions: i, ratio };
    }).sort((a, b) => b.quejas - a.quejas);
  }, [quejasByBarri, ivsByBarri, barriToDistrict]);

  // Selected district profile (filtered)
  const selectedProfile = useMemo(() => {
    if (!selectedDistrict) return null;
    // Quejas top for this district, filtered by year and tipo
    const quejaTemas: Record<string, number> = {};
    for (const y of yearsFiltered) {
      const data = tipoData.by_year_district_tema[y];
      if (!data) continue;
      const dd = data[selectedDistrict];
      if (!dd) continue;
      for (const [t, c] of Object.entries(dd)) {
        if (EXCLUDE_TEMAS.has(t)) continue;
        quejaTemas[t] = (quejaTemas[t] || 0) + c;
      }
    }
    const topQuejas = Object.entries(quejaTemas)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([name, count]) => ({ name, count }));

    // Intervention categories + entities for this district
    const catCounts: Record<string, number> = {};
    const entCounts: Record<string, number> = {};
    for (const iv of filteredIvs) {
      if (!effectiveDistricts(iv).has(selectedDistrict)) continue;
      for (const cat of Object.keys(iv.temes_v2 || {})) {
        catCounts[cat] = (catCounts[cat] || 0) + 1;
      }
      if (iv.entitat_id) {
        entCounts[iv.entitat_id] = (entCounts[iv.entitat_id] || 0) + 1;
      }
    }
    const topCats = Object.entries(catCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([name, count]) => ({ name, count }));
    const topEnts = Object.entries(entCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([id, count]) => ({
        id, count,
        name: entityNames[id]?.[lang === 'cas' ? 'nom_cas' : 'nom_val'] || id,
      }));

    return {
      quejas: quejasByDistrict[selectedDistrict] || 0,
      intervencions: ivsByDistrict[selectedDistrict] || 0,
      ratio: districtData.find(d => d.name === selectedDistrict)?.ratio || 0,
      topQuejas, topCats, topEnts,
    };
  }, [selectedDistrict, yearsFiltered, filteredIvs, quejasByDistrict, ivsByDistrict, districtData, tipoData, entityNames, lang]);

  const topActive = districtData.filter(d => d.quejas > 100).slice(0, 5);
  const bottomActive = [...districtData].filter(d => d.quejas > 100).sort((a, b) => a.ratio - b.ratio).slice(0, 5);
  const eligibleDistricts = districtData.filter(d => d.quejas > 100);
  const cityMeanRatio = eligibleDistricts.length > 0
    ? eligibleDistricts.reduce((sum, d) => sum + d.ratio, 0) / eligibleDistricts.length
    : 0;

  // Init map
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

  // Update map layer
  useEffect(() => {
    if (!leaflet || !mapInstanceRef.current) return;
    const map = mapInstanceRef.current;
    const L = leaflet;
    if (layerRef.current) { map.removeLayer(layerRef.current); layerRef.current = null; }

    const isBarri = geoMode === 'barri';
    const sourceData = isBarri ? barriData : districtData;
    const valuesByName: Record<string, number> = {};
    for (const d of sourceData) {
      if (mapMode === 'quejas') valuesByName[d.name] = d.quejas;
      else if (mapMode === 'intervencions') valuesByName[d.name] = d.intervencions;
      else valuesByName[d.name] = d.ratio;
    }
    const maxVal = Math.max(...Object.values(valuesByName), 1);
    const label = mapMode === 'quejas'
      ? (tipoFilter === 'todas'
          ? (lang === 'cas' ? 'quejas y sugerencias' : 'queixes i suggeriments')
          : tipoFilter === 'queja'
          ? (lang === 'cas' ? 'quejas' : 'queixes')
          : (lang === 'cas' ? 'sugerencias' : 'suggeriments'))
      : mapMode === 'intervencions'
      ? (lang === 'cas' ? 'intervenciones' : 'intervencions')
      : 'ratio ‰';
    const colorFn = mapMode === 'quejas' ? quejasColor : mapMode === 'intervencions' ? ivColor : ratioColor;

    // For barris, the geojson feature.properties.nombre is uppercase
    // (e.g. "LA CREU COBERTA"); we keep a map to the canonical case.
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

    fetch(isBarri ? '/barris.geojson' : '/districtes.geojson').then(r => r.json()).then(geojson => {
      const layer = L.geoJSON(geojson, {
        style: (f: any) => {
          const name = resolveName(f);
          const v = valuesByName[name] || 0;
          const isSelected = !isBarri && name === selectedDistrict;
          return {
            fillColor: colorFn(v, maxVal),
            weight: isSelected ? 3 : (isBarri ? 0.8 : 1.5),
            color: isSelected ? '#e8562a' : '#fff',
            fillOpacity: 0.85,
          };
        },
        onEachFeature: (f: any, l: any) => {
          const name = resolveName(f);
          const v = valuesByName[name] || 0;
          const displayV = mapMode === 'ratio' ? `${v.toFixed(1)}‰` : v.toLocaleString('es-ES');
          const subtitle = isBarri && barriToDistrict[name]
            ? `<span style="font-size: 0.7rem; color: #666;">${barriToDistrict[name]}</span><br/>`
            : '';
          l.bindTooltip(
            `<div style="font-family: 'Sora', system-ui, sans-serif; text-align: center;">
              <strong>${name}</strong><br/>
              ${subtitle}
              <span style="font-size: 1.1rem; font-weight: 800; color: #e8562a;">${displayV}</span>
              <span style="font-size: 0.7rem; color: #666;"> ${label}</span>
            </div>`,
            { direction: 'top', className: 'district-tooltip' }
          );
          l.on('mouseover', function(this: any) {
            if (isBarri || name !== selectedDistrict) {
              this.setStyle({ weight: 2.5, color: '#e8562a', fillOpacity: 0.95 });
            }
          });
          l.on('mouseout', function(this: any) { layer.resetStyle(this); });
          l.on('click', () => {
            if (isBarri) {
              // Clicking a barri selects its containing district for the profile below.
              const d = barriToDistrict[name];
              if (d) setSelectedDistrict(d);
            } else {
              setSelectedDistrict(name);
            }
          });
        },
      }).addTo(map);
      layerRef.current = layer;
    });
  }, [leaflet, mapMode, geoMode, districtData, barriData, selectedDistrict, lang, barriToDistrict, tipoFilter]);

  const totalQuejasFiltered = Object.values(quejasByDistrict).reduce((a, b) => a + b, 0);
  const maxQuejaTemaCount = Math.max(...Object.values(quejaTemasFiltered), 1);
  const maxIvCatCount = Math.max(...Object.values(ivCategoriesFiltered), 1);
  const sortedQuejaTemas = Object.entries(quejaTemasFiltered).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const sortedIvCats = Object.entries(ivCategoriesFiltered).sort((a, b) => b[1] - a[1]);

  const yearLabel = activeMandat
    ? mandats.find(m => m.id === activeMandat)?.legislatura || ''
    : yearRange[0] === yearRange[1] ? `${yearRange[0]}` : `${yearRange[0]}–${yearRange[1]}`;

  const maxDistQuejas = Math.max(...districtData.map(d => d.quejas), 1);
  const maxDistIv = Math.max(...districtData.map(d => d.intervencions), 1);

  // Section A geo-mode helpers
  const geoData = geoMode === 'barri' ? barriData : districtData;
  const maxGeoQuejas = Math.max(...geoData.map(d => d.quejas), 1);
  const maxGeoIv = Math.max(...geoData.map(d => d.intervencions), 1);
  const totalSinBarri = tipoData.total_sin_barri || 0;
  const totalSinDistricte = tipoData.total_sin_districte || 0;

  // Applied sort; when sortCol is null, keep the default row order baked
  // into districtData/barriData (ratio desc / quejas desc respectively).
  const sortedGeoData = useMemo(() => {
    if (!sortCol) return geoData;
    const arr = [...geoData];
    arr.sort((a: any, b: any) => {
      if (sortCol === 'name') {
        return sortDir === 'asc' ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name);
      }
      const av = a[sortCol] as number;
      const bv = b[sortCol] as number;
      return sortDir === 'asc' ? av - bv : bv - av;
    });
    return arr;
  }, [geoData, sortCol, sortDir]);

  function toggleSort(col: 'name' | 'quejas' | 'intervencions' | 'ratio') {
    if (sortCol !== col) { setSortCol(col); setSortDir('desc'); return; }
    if (sortDir === 'desc') { setSortDir('asc'); return; }
    setSortCol(null);
    setSortDir('desc');
  }

  function sortArrow(col: 'name' | 'quejas' | 'intervencions' | 'ratio'): string {
    if (sortCol !== col) return '';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  const districtNamesList = Object.keys(quejas.by_tipo.queja.districts).sort();

  const tipoLabel = tipoFilter === 'todas'
    ? (lang === 'cas' ? 'quejas y sugerencias' : 'queixes i suggeriments')
    : tipoFilter === 'queja'
    ? (lang === 'cas' ? 'quejas' : 'queixes')
    : (lang === 'cas' ? 'sugerencias' : 'suggeriments');

  // True when period + tipo filters are at their default (full aggregate).
  // Used to show "Lecturas del cruce" boxes whose concrete findings only
  // hold for the 2020-2026 aggregate across quejas + sugerencias.
  const filtersAtDefault = !activeMandat
    && yearRange[0] === minYear
    && yearRange[1] === maxYear
    && tipoFilter === 'todas';

  const mapMaxForLegend = Math.max(
    ...geoData.map((d: any) =>
      mapMode === 'quejas' ? d.quejas : mapMode === 'intervencions' ? d.intervencions : d.ratio
    ),
    1
  );

  return (
    <div style="font-family: 'Outfit', system-ui, sans-serif; position: relative; z-index: 0;">

      {/* Year/mandat selector */}
      <div style="padding: 1.5rem 1rem; background: #fff; border-bottom: 1px solid #eee; position: sticky; top: 60px; z-index: 10;">
        <div class="max-w-5xl mx-auto">
          <div style="display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;">
            <span style="font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #666;">
              {lang === 'cas' ? 'Período' : 'Període'}
            </span>
            <span style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.2rem; font-weight: 700; color: #e8562a;">{yearLabel}</span>
            <span style="flex: 1; min-width: 200px; display: flex; gap: 0.4rem; flex-wrap: wrap;">
              {[...mandats].filter(m => !(hideIntervenciones || clampToQuejas) || !m.fi || parseInt(m.fi.slice(0, 4)) >= minYear).sort((a, b) => a.inici.localeCompare(b.inici)).map(m => {
                const isActive = activeMandat === m.id;
                return (
                  <button
                    key={m.id}
                    onClick={() => {
                      if (isActive) setActiveMandat(null);
                      else {
                        setActiveMandat(m.id);
                        setYearRange([parseInt(m.inici.slice(0, 4)), m.fi ? parseInt(m.fi.slice(0, 4)) : maxYear]);
                      }
                    }}
                    style={{
                      fontSize: '0.7rem', fontWeight: isActive ? '600' : '400',
                      color: isActive ? '#fff' : '#666',
                      background: isActive ? '#1e1e1e' : 'none',
                      border: isActive ? 'none' : '1px solid #ddd',
                      borderRadius: '100px', padding: '4px 10px', cursor: 'pointer',
                    }}
                  >
                    {m.legislatura} · {m.alcalde.split(' ').slice(0, -1).join(' ')}
                  </button>
                );
              })}
            </span>
          </div>
          {/* Year marks */}
          <div style="display: flex; gap: 0.25rem; margin-top: 0.75rem; flex-wrap: wrap;">
            {allYears.map(y => {
              const active = y >= yearRange[0] && y <= yearRange[1];
              return (
                <button
                  key={y}
                  onClick={() => { setYearRange([y, y]); setActiveMandat(null); }}
                  style={{
                    fontSize: '0.7rem', fontWeight: active ? '600' : '400',
                    color: active ? '#fff' : '#666',
                    background: active ? '#e8562a' : 'none',
                    border: active ? 'none' : '1px solid #ddd',
                    borderRadius: '6px', padding: '4px 10px', cursor: 'pointer',
                  }}
                >
                  {y}
                </button>
              );
            })}
            <button
              onClick={() => { setYearRange([minYear, maxYear]); setActiveMandat(null); }}
              style={{
                fontSize: '0.7rem', fontWeight: '500', color: '#666',
                background: 'none', border: '1px solid #ddd',
                borderRadius: '6px', padding: '4px 10px', cursor: 'pointer',
              }}
            >
              {lang === 'cas' ? 'Todos' : 'Tots'}
            </button>
          </div>

          {/* Tipo selector */}
          <div style="display: flex; align-items: center; gap: 0.75rem; margin-top: 0.75rem; flex-wrap: wrap;">
            <span style="font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #666;">
              {lang === 'cas' ? 'Tipo' : 'Tipus'}
            </span>
            {(['todas', 'queja', 'sugerencia'] as const).map(tp => {
              const active = tipoFilter === tp;
              const label = tp === 'todas' ? (lang === 'cas' ? 'Todas' : 'Totes')
                          : tp === 'queja' ? (lang === 'cas' ? 'Quejas' : 'Queixes')
                          : (lang === 'cas' ? 'Sugerencias' : 'Suggeriments');
              return (
                <button
                  key={tp}
                  onClick={() => setTipoFilter(tp)}
                  style={{
                    fontSize: '0.7rem', fontWeight: active ? '600' : '400',
                    color: active ? '#fff' : '#666',
                    background: active ? '#1e1e1e' : 'none',
                    border: active ? 'none' : '1px solid #ddd',
                    borderRadius: '100px', padding: '4px 12px', cursor: 'pointer',
                  }}
                >{label}</button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Map section */}
      <section style="padding: 2.5rem 1rem; background: #fff;">
        <div class="max-w-5xl mx-auto">
          <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; flex-wrap: wrap;">
            <h2 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.4rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin: 0;">
              {geoMode === 'barri'
                ? (lang === 'cas' ? 'Mapa por barrio' : 'Mapa per barri')
                : (lang === 'cas' ? 'Mapa por distrito' : 'Mapa per districte')}
            </h2>
            <div style="display: flex; gap: 0.25rem; margin-left: auto; flex-wrap: wrap;">
              {/* Geo mode toggle (shared with section A) */}
              {(['distrito', 'barri'] as const).map(m => (
                <button
                  key={`geo-${m}`}
                  onClick={() => { setGeoMode(m); setPopupDistrict(null); }}
                  style={{
                    fontSize: '0.75rem',
                    fontWeight: geoMode === m ? '600' : '400',
                    color: geoMode === m ? '#fff' : '#666',
                    background: geoMode === m ? '#1e1e1e' : 'none',
                    border: geoMode === m ? 'none' : '1px solid #ddd',
                    borderRadius: '100px', padding: '5px 12px', cursor: 'pointer',
                  }}
                >
                  {m === 'distrito'
                    ? (lang === 'cas' ? 'Por distrito' : 'Per districte')
                    : (lang === 'cas' ? 'Por barrio' : 'Per barri')}
                </button>
              ))}
              {!hideIntervenciones && (
                <>
                  <span style="width: 1px; background: #ddd; margin: 0 0.25rem;" />
                  {(['quejas', 'intervencions', 'ratio'] as const).map(m => (
                    <button
                      key={m}
                      onClick={() => setMapMode(m)}
                      style={{
                        fontSize: '0.75rem',
                        fontWeight: mapMode === m ? '600' : '400',
                        color: mapMode === m ? '#fff' : '#666',
                        background: mapMode === m ? '#1e1e1e' : 'none',
                        border: mapMode === m ? 'none' : '1px solid #ddd',
                        borderRadius: '100px', padding: '5px 12px', cursor: 'pointer',
                      }}
                    >
                      {m === 'quejas' ? (lang === 'cas' ? 'Quejas / Sugerencias' : 'Queixes / Suggeriments')
                       : m === 'intervencions' ? (lang === 'cas' ? 'Intervenciones' : 'Intervencions')
                       : 'Ratio'}
                    </button>
                  ))}
                </>
              )}
            </div>
          </div>
          <p style="color: #666; margin-bottom: 1.25rem; max-width: 42rem; line-height: 1.6; font-size: 0.9rem;">
            {!hideIntervenciones
              ? (lang === 'cas'
                  ? <>Empieza por Quejas, verás dónde se concentra el malestar individual. Cambia a Intervenciones para ver qué barrios además llegan al pleno. El Ratio es la vista más reveladora: muestra los barrios que hacen más o menos con sus quejas. Un barrio destacado en ratio pero discreto en quejas tiene pocas quejas pero un asociacionismo potente.</>
                  : <>Comença per Queixes, veuràs on es concentra el malestar individual. Canvia a Intervencions per veure quins barris a més arriben al ple. El Ratio és la vista més reveladora: mostra els barris que fan més o menys amb les seues queixes. Un barri destacat en ratio però discret en queixes té poques queixes però un associacionisme potent.</>)
              : (lang === 'cas'
                  ? <>Colorea cada {geoMode === 'barri' ? 'barrio' : 'distrito'} según el valor seleccionado. Haz clic en un {geoMode === 'barri' ? 'barrio para seleccionar su distrito' : 'distrito para ver su perfil detallado'} más abajo.</>
                  : <>Acoloreix cada {geoMode === 'barri' ? 'barri' : 'districte'} segons el valor seleccionat. Fes clic en un {geoMode === 'barri' ? 'barri per a seleccionar el seu districte' : 'districte per vore el seu perfil detallat'} davall.</>)}
          </p>
          <div style="position: relative;">
            <div ref={mapRef} style="width: 100%; height: 440px; border-radius: 16px; overflow: hidden; background: #f5f5f5; position: relative; z-index: 0;" />
            <div style="position: absolute; bottom: 16px; left: 12px; z-index: 1; background: rgba(255,255,255,0.93); border-radius: 8px; padding: 8px 10px 6px; font-family: 'Outfit', system-ui, sans-serif; box-shadow: 0 1px 4px rgba(0,0,0,0.15); min-width: 110px; pointer-events: none;">
              <div style="font-size: 0.6rem; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 5px;">
                {mapMode === 'quejas'
                  ? tipoLabel.charAt(0).toUpperCase() + tipoLabel.slice(1)
                  : mapMode === 'intervencions'
                  ? (lang === 'cas' ? 'Intervenciones' : 'Intervencions')
                  : 'Ratio (‰)'}
              </div>
              <div style="display: flex; gap: 2px; margin-bottom: 4px;">
                {LEGEND_COLORS[mapMode].map((c, i) => (
                  <div key={i} style={`flex: 1; height: 10px; background: ${c}; border-radius: 2px;`} />
                ))}
              </div>
              <div style="display: flex; justify-content: space-between; font-size: 0.62rem; color: #999;">
                <span>0</span>
                <span>{fmtLegendVal(mapMaxForLegend, mapMode)}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Sección A: tabla */}
      <section style="padding: 2rem 1rem; background: #fff; border-top: 1px solid #eee;">
        <div class="max-w-5xl mx-auto">
          <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; flex-wrap: wrap;">
            <h2 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.4rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin: 0;">
              {geoMode === 'barri'
                ? (lang === 'cas' ? 'Volumen por barrio' : 'Volum per barri')
                : (lang === 'cas' ? 'Volumen por distrito' : 'Volum per districte')}
            </h2>
            <div style="display: flex; gap: 0.25rem; margin-left: auto;">
              {(['distrito', 'barri'] as const).map(m => (
                <button
                  key={m}
                  onClick={() => { setGeoMode(m); setPopupDistrict(null); }}
                  style={{
                    fontSize: '0.75rem',
                    fontWeight: geoMode === m ? '600' : '400',
                    color: geoMode === m ? '#fff' : '#666',
                    background: geoMode === m ? '#1e1e1e' : 'none',
                    border: geoMode === m ? 'none' : '1px solid #ddd',
                    borderRadius: '100px', padding: '5px 12px', cursor: 'pointer',
                  }}
                >
                  {m === 'distrito'
                    ? (lang === 'cas' ? 'Por distrito' : 'Per districte')
                    : (lang === 'cas' ? 'Por barrio' : 'Per barri')}
                </button>
              ))}
            </div>
          </div>
          <p style="color: #666; margin-bottom: 0.75rem; max-width: 42rem; line-height: 1.6; font-size: 0.9rem;">
            {hideIntervenciones
              ? (lang === 'cas'
                  ? <>{totalQuejasFiltered.toLocaleString('es-ES')} {tipoLabel} presentadas al Ayuntamiento ({yearLabel}), desglosadas por {geoMode === 'barri' ? 'barrio' : 'distrito'} de localización del problema.</>
                  : <>{totalQuejasFiltered.toLocaleString('es-ES')} {tipoLabel} presentades a l'Ajuntament ({yearLabel}), desglossades per {geoMode === 'barri' ? 'barri' : 'districte'} de localització del problema.</>)
              : (lang === 'cas'
                  ? <>{totalQuejasFiltered.toLocaleString('es-ES')} {tipoLabel} presentadas al Ayuntamiento ({yearLabel}) frente a {filteredIvs.length} intervenciones ciudadanas en los plenos. Los {geoMode === 'barri' ? 'barrios' : 'distritos'} con más quejas no son necesariamente los que más intervienen.</>
                  : <>{totalQuejasFiltered.toLocaleString('es-ES')} {tipoLabel} presentades a l'Ajuntament ({yearLabel}) front a {filteredIvs.length} intervencions ciutadanes als plens. Els {geoMode === 'barri' ? 'barris' : 'districtes'} amb més queixes no són necessàriament els que més intervenen.</>)}
          </p>
          {(totalSinBarri > 0 || totalSinDistricte > 0) && (
            <p style="color: #666; margin-bottom: 1.25rem; max-width: 42rem; line-height: 1.5; font-size: 0.78rem; font-style: italic;">
              {lang === 'cas' ? (
                geoMode === 'barri' ? (
                  <>Además, <strong>{totalSinDistricte.toLocaleString('es-ES')} {tipoLabel}</strong> no tienen distrito declarado y <strong>{totalSinBarri.toLocaleString('es-ES')}</strong> tienen distrito pero no barrio — no aparecen en esta vista.</>
                ) : (
                  <>Además, <strong>{totalSinDistricte.toLocaleString('es-ES')} {tipoLabel}</strong> no tienen distrito declarado y no se pueden cruzar geográficamente con las intervenciones.</>
                )
              ) : (
                geoMode === 'barri' ? (
                  <>A més, <strong>{totalSinDistricte.toLocaleString('es-ES')} {tipoLabel}</strong> no tenen districte declarat i <strong>{totalSinBarri.toLocaleString('es-ES')}</strong> tenen districte però no barri — no apareixen en esta vista.</>
                ) : (
                  <>A més, <strong>{totalSinDistricte.toLocaleString('es-ES')} {tipoLabel}</strong> no tenen districte declarat i no es poden creuar geogràficament amb les intervencions.</>
                )
              )}
            </p>
          )}

          <div style={`display: grid; gap: 0.5rem; ${geoMode === 'barri' ? 'max-height: 480px; overflow-y: auto; padding-right: 6px;' : ''}`}>
            <div style={`display: grid; grid-template-columns: ${hideIntervenciones ? '11rem 1fr' : '11rem 1fr 1fr 3.5rem'}; gap: 0.8rem; padding: 0 0.4rem 0.4rem; border-bottom: 1px solid #eee; font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #666; position: sticky; top: 0; background: #fff;`}>
              <span
                onClick={() => toggleSort('name')}
                style={`cursor: pointer; user-select: none; ${sortCol === 'name' ? 'color: #1e1e1e;' : ''}`}
              >
                {geoMode === 'barri' ? (lang === 'cas' ? 'Barrio' : 'Barri') : (lang === 'cas' ? 'Distrito' : 'Districte')}{sortArrow('name')}
              </span>
              <span
                onClick={() => toggleSort('quejas')}
                style={`cursor: pointer; user-select: none; color: ${sortCol === 'quejas' ? '#c2410c' : '#e8562a'};`}
              >
                {tipoLabel.charAt(0).toUpperCase() + tipoLabel.slice(1)}{sortArrow('quejas')}
              </span>
              {!hideIntervenciones && (
                <span
                  onClick={() => toggleSort('intervencions')}
                  style={`cursor: pointer; user-select: none; color: #1e1e1e; ${sortCol === 'intervencions' ? 'font-weight: 700;' : ''}`}
                >
                  {lang === 'cas' ? 'Intervenciones' : 'Intervencions'}{sortArrow('intervencions')}
                </span>
              )}
              {!hideIntervenciones && (
                <span
                  onClick={() => toggleSort('ratio')}
                  style={`cursor: pointer; user-select: none; text-align: right; ${sortCol === 'ratio' ? 'color: #1e1e1e; font-weight: 700;' : ''}`}
                >
                  Ratio{sortArrow('ratio')}
                </span>
              )}
            </div>
            {sortedGeoData.map((d: any) => {
              const isHl = geoMode === 'distrito'
                ? selectedDistrict === d.name
                : popupDistrict === d.name;
              return (
                <div
                  key={d.name}
                  onClick={() => {
                    if (geoMode === 'distrito') {
                      setSelectedDistrict(d.name);
                      setPopupDistrict(prev => prev === d.name ? null : d.name);
                    } else {
                      setPopupDistrict(prev => prev === d.name ? null : d.name);
                    }
                  }}
                  style={`display: grid; grid-template-columns: ${hideIntervenciones ? '11rem 1fr' : '11rem 1fr 1fr 3.5rem'}; gap: 0.8rem; align-items: center; padding: 0.5rem 0.4rem; border-bottom: 1px solid #f5f5f5; cursor: pointer; ${isHl ? 'background: #fef8f5;' : ''}`}
                >
                  <div>
                    <div style="font-size: 0.8rem; font-weight: 500; line-height: 1.2;">{d.name}</div>
                    {geoMode === 'barri' && d.district && (
                      <div style="font-size: 0.65rem; color: #aaa; margin-top: 1px;">{d.district}</div>
                    )}
                  </div>
                  <div style="position: relative; height: 14px; background: #fef1ec; border-radius: 3px; overflow: hidden;">
                    <div style={`position: absolute; inset: 0; width: ${(d.quejas / maxGeoQuejas) * 100}%; background: #e8562a;`} />
                    <span style="position: absolute; right: 5px; top: 50%; transform: translateY(-50%); font-size: 0.65rem; font-weight: 600; color: #1e1e1e;">{d.quejas.toLocaleString('es-ES')}</span>
                  </div>
                  {!hideIntervenciones && (
                    <div style="position: relative; height: 14px; background: #f0f0f0; border-radius: 3px; overflow: hidden;">
                      <div style={`position: absolute; inset: 0; width: ${(d.intervencions / maxGeoIv) * 100}%; background: #1e1e1e;`} />
                      <span style="position: absolute; right: 5px; top: 50%; transform: translateY(-50%); font-size: 0.65rem; font-weight: 600; color: #fff; text-shadow: 0 0 2px rgba(0,0,0,0.5);">{d.intervencions}</span>
                    </div>
                  )}
                  {!hideIntervenciones && (
                    <span style={`text-align: right; font-family: 'Sora', system-ui, sans-serif; font-size: 0.8rem; font-weight: 700; color: ${d.ratio > 10 ? '#e8562a' : d.ratio > 3 ? '#1e1e1e' : '#aaa'};`}>
                      {d.ratio.toFixed(1)}‰
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {!hideIntervenciones && (() => {
            /* Scatter quejas × intervenciones — with broken axes when outliers skew the cluster */
            const PAD_L = 60, PAD_R = 15, PAD_T = 20, PAD_B = 60;
            const W = 600, H = 420;
            const plotW = W - PAD_L - PAD_R;
            const plotH = H - PAD_T - PAD_B;
            const MAIN_F = 0.78, GAP_F = 0.06;

            // Compute axis config: decide if a break is needed and where.
            const axisCfg = (vals: number[]): { mainMax: number; secMin: number; secMax: number; needsBreak: boolean } => {
              if (vals.length < 4) {
                const m = Math.max(...vals, 1);
                return { mainMax: m, secMin: m, secMax: m, needsBreak: false };
              }
              const sorted = [...vals].sort((a, b) => a - b);
              const max = sorted[sorted.length - 1] || 1;
              const p80 = sorted[Math.floor(sorted.length * 0.8)] || 1;
              if (max > p80 * 1.8) {
                const outliers = sorted.filter(v => v > p80 * 1.5);
                const mainMax = Math.max(p80, Math.ceil(p80 * 1.05));
                const secMin  = outliers[0] > mainMax * 1.05 ? Math.floor(outliers[0] * 0.95) : mainMax;
                return { mainMax, secMin, secMax: max, needsBreak: true };
              }
              return { mainMax: max, secMin: max, secMax: max, needsBreak: false };
            };

            const broken = (v: number, cfg: { mainMax: number; secMin: number; secMax: number; needsBreak: boolean }, plotStart: number, plotLen: number): number => {
              if (!cfg.needsBreak) return plotStart + (v / Math.max(1, cfg.secMax)) * plotLen;
              const mainLen = plotLen * MAIN_F;
              const gapLen = plotLen * GAP_F;
              const secLen = plotLen * (1 - MAIN_F - GAP_F);
              const mainEnd = plotStart + mainLen;
              const secStart = mainEnd + gapLen;
              if (v <= cfg.mainMax) return plotStart + (v / Math.max(1, cfg.mainMax)) * mainLen;
              if (v < cfg.secMin) return mainEnd;
              const f = Math.min(1, (v - cfg.secMin) / Math.max(1e-9, cfg.secMax - cfg.secMin));
              return secStart + f * secLen;
            };

            const cfgX = axisCfg(geoData.map((d: any) => d.intervencions));
            const cfgY = axisCfg(geoData.map((d: any) => d.quejas));

            const xScale = (v: number) => PAD_L + broken(v, cfgX, 0, plotW);
            const yInvScale = (v: number) => broken(v, cfgY, 0, plotH);
            const yScale = (v: number) => PAD_T + plotH - yInvScale(v);

            // Break mark positions
            const xGapStart = PAD_L + plotW * MAIN_F;
            const xGapEnd   = xGapStart + plotW * GAP_F;
            const yGapLow   = PAD_T + plotH - plotH * MAIN_F;                 // bottom edge of Y gap (screen Y)
            const yGapHigh  = PAD_T + plotH - plotH * (MAIN_F + GAP_F);       // top edge of Y gap
            const axisBottomY = PAD_T + plotH;

            return (
            <div style="margin-top: 2.5rem;">
              <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.5rem;">
                {lang === 'cas' ? 'Distribución por cuadrantes' : 'Distribució per quadrants'}
              </h3>
              <p style="color: #666; font-size: 0.85rem; line-height: 1.5; margin-bottom: 1rem; max-width: 42rem;">
                {lang === 'cas'
                  ? <>Cada punto es un {geoMode === 'barri' ? 'barrio' : 'distrito'}. Arriba-derecha, los más activos en ambos canales; abajo-izquierda, los más silenciosos. Haz clic en un punto para ver sus valores.{(cfgX.needsBreak || cfgY.needsBreak) ? ' Los ejes están rotos (//) para que los outliers no aplasten el resto del grupo.' : ''}</>
                  : <>Cada punt és un {geoMode === 'barri' ? 'barri' : 'districte'}. Dalt-dreta, els més actius en ambdós canals; baix-esquerra, els més silenciosos. Fes clic en un punt per a vore els seus valors.{(cfgX.needsBreak || cfgY.needsBreak) ? " Els eixos estan trencats (//) perquè els outliers no aixafen la resta del grup." : ''}</>}
              </p>
              <div style="background: #fafafa; border-radius: 12px; padding: 1rem; border: 1px solid #eee;">
                <svg
                  viewBox={`0 0 ${W} ${H}`}
                  style="width: 100%; height: auto; font-family: 'Outfit', system-ui, sans-serif; display: block;"
                  onClick={() => setPopupDistrict(null)}
                >
                  {/* X axis — drawn in two segments if broken */}
                  {cfgX.needsBreak ? (
                    <>
                      <line x1={PAD_L}    y1={axisBottomY} x2={xGapStart}     y2={axisBottomY} stroke="#ccc" stroke-width="1" />
                      <line x1={xGapEnd}  y1={axisBottomY} x2={PAD_L + plotW} y2={axisBottomY} stroke="#ccc" stroke-width="1" />
                      <g stroke="#999" stroke-width="1" fill="none">
                        <line x1={xGapStart - 2} y1={axisBottomY + 4} x2={xGapStart + 4} y2={axisBottomY - 4} />
                        <line x1={xGapEnd - 4}   y1={axisBottomY + 4} x2={xGapEnd + 2}   y2={axisBottomY - 4} />
                      </g>
                    </>
                  ) : (
                    <line x1={PAD_L} y1={axisBottomY} x2={PAD_L + plotW} y2={axisBottomY} stroke="#ccc" stroke-width="1" />
                  )}

                  {/* Y axis — drawn in two segments if broken */}
                  {cfgY.needsBreak ? (
                    <>
                      <line x1={PAD_L} y1={axisBottomY} x2={PAD_L} y2={yGapLow}  stroke="#ccc" stroke-width="1" />
                      <line x1={PAD_L} y1={yGapHigh}    x2={PAD_L} y2={PAD_T}    stroke="#ccc" stroke-width="1" />
                      <g stroke="#999" stroke-width="1" fill="none">
                        <line x1={PAD_L - 4} y1={yGapLow + 2}  x2={PAD_L + 4} y2={yGapLow - 4} />
                        <line x1={PAD_L - 4} y1={yGapHigh + 4} x2={PAD_L + 4} y2={yGapHigh - 2} />
                      </g>
                    </>
                  ) : (
                    <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={axisBottomY} stroke="#ccc" stroke-width="1" />
                  )}

                  {/* axis labels */}
                  <text x={PAD_L + plotW / 2} y={H - 14} text-anchor="middle" font-size="11" fill="#666">
                    {lang === 'cas' ? '→ intervenciones en el pleno' : '→ intervencions al ple'}
                  </text>
                  <text x="18" y={PAD_T + plotH / 2} text-anchor="middle" font-size="11" fill="#666"
                        transform={`rotate(-90 18 ${PAD_T + plotH / 2})`}>
                    → {tipoLabel}
                  </text>

                  {/* X ticks */}
                  <text x={PAD_L} y={axisBottomY + 14} text-anchor="start" font-size="10" fill="#999">0</text>
                  {cfgX.needsBreak && (
                    <>
                      <text x={xGapStart} y={axisBottomY + 14} text-anchor="middle" font-size="10" fill="#999">{cfgX.mainMax}</text>
                      <text x={xGapEnd}   y={axisBottomY + 14} text-anchor="middle" font-size="10" fill="#999">{cfgX.secMin}</text>
                    </>
                  )}
                  <text x={PAD_L + plotW} y={axisBottomY + 14} text-anchor="end" font-size="10" fill="#999">{cfgX.secMax}</text>

                  {/* Y ticks */}
                  <text x={PAD_L - 6} y={axisBottomY + 3} text-anchor="end" font-size="10" fill="#999">0</text>
                  {cfgY.needsBreak && (
                    <>
                      <text x={PAD_L - 6} y={yGapLow + 3}  text-anchor="end" font-size="10" fill="#999">{cfgY.mainMax.toLocaleString('es-ES')}</text>
                      <text x={PAD_L - 6} y={yGapHigh + 3} text-anchor="end" font-size="10" fill="#999">{cfgY.secMin.toLocaleString('es-ES')}</text>
                    </>
                  )}
                  <text x={PAD_L - 6} y={PAD_T + 4} text-anchor="end" font-size="10" fill="#999">{cfgY.secMax.toLocaleString('es-ES')}</text>

                  {/* gridlines at break thresholds for visual anchoring */}
                  {cfgX.needsBreak && (
                    <line x1={xGapStart} y1={PAD_T} x2={xGapStart} y2={axisBottomY} stroke="#eee" stroke-width="0.5" stroke-dasharray="2,3" />
                  )}
                  {cfgY.needsBreak && (
                    <line x1={PAD_L} y1={yGapLow} x2={PAD_L + plotW} y2={yGapLow} stroke="#eee" stroke-width="0.5" stroke-dasharray="2,3" />
                  )}

                  {/* quadrant hints */}
                  <text x={PAD_L + plotW - 6} y={PAD_T + 12} text-anchor="end" font-size="9" fill="#c2410c" font-weight="700" letter-spacing="0.05em">
                    {lang === 'cas' ? '↗ ASOCIACIONISMO FUERTE' : '↗ ASSOCIACIONISME FORT'}
                  </text>
                  <text x={PAD_L + plotW - 6} y={axisBottomY - 6} text-anchor="end" font-size="9" fill="#b45309" font-weight="700" letter-spacing="0.05em">
                    {lang === 'cas' ? '↘ VOZ ORGANIZADA' : '↘ VEU ORGANITZADA'}
                  </text>
                  <text x={PAD_L + 6} y={PAD_T + 12} text-anchor="start" font-size="9" fill="#999" font-weight="700" letter-spacing="0.05em">
                    {lang === 'cas' ? '↖ QUEJA SILENCIOSA' : '↖ QUEIXA SILENCIOSA'}
                  </text>
                  <text x={PAD_L + 6} y={axisBottomY - 6} text-anchor="start" font-size="9" fill="#bbb" font-weight="700" letter-spacing="0.05em">
                    {lang === 'cas' ? '↙ SILENCIO EN AMBOS' : '↙ SILENCI EN TOTS DOS'}
                  </text>

                  {/* points + labels */}
                  {geoData.map((d: any) => {
                    const cx = xScale(d.intervencions);
                    const cy = yScale(d.quejas);
                    const isSel = geoMode === 'distrito'
                      ? d.name === selectedDistrict
                      : d.name === popupDistrict;
                    const labelRight = cx < PAD_L + plotW * 0.7;
                    return (
                      <g
                        key={d.name}
                        style="cursor: pointer;"
                        onClick={(e: any) => {
                          e.stopPropagation();
                          if (geoMode === 'distrito') setSelectedDistrict(d.name);
                          setPopupDistrict(prev => prev === d.name ? null : d.name);
                        }}
                      >
                        <circle
                          cx={cx} cy={cy}
                          r={isSel ? 7 : (geoMode === 'barri' ? 4 : 5)}
                          fill={isSel ? '#e8562a' : 'rgba(232, 86, 42, 0.6)'}
                          stroke={isSel ? '#1e1e1e' : '#fff'}
                          stroke-width={isSel ? 2 : 1}
                        />
                        {geoMode === 'distrito' && (
                          <text
                            x={labelRight ? cx + 9 : cx - 9}
                            y={cy + 3}
                            text-anchor={labelRight ? 'start' : 'end'}
                            font-size="9.5"
                            fill={isSel ? '#1e1e1e' : '#555'}
                            font-weight={isSel ? '700' : '400'}
                            style="pointer-events: none;"
                          >
                            {d.name}
                          </text>
                        )}
                      </g>
                    );
                  })}

                  {/* popup tooltip for clicked district/barri */}
                  {(() => {
                    if (!popupDistrict) return null;
                    const sd = geoData.find((x: any) => x.name === popupDistrict);
                    if (!sd) return null;
                    const cx = xScale(sd.intervencions);
                    const cy = yScale(sd.quejas);
                    const hasDistrict = geoMode === 'barri' && sd.district;
                    const tipW = 195;
                    const tipH = hasDistrict ? 80 : 62;
                    const tipX = cx + tipW + 14 > W - 10 ? cx - tipW - 10 : cx + 12;
                    const tipY = cy - tipH - 10 < 5 ? cy + 12 : cy - tipH - 8;
                    return (
                      <g style="pointer-events: none;">
                        <rect x={tipX} y={tipY} width={tipW} height={tipH} rx="6" fill="#1e1e1e" opacity="0.95" />
                        <text x={tipX + 10} y={tipY + 18} font-size="11" font-weight="700" fill="#fff">{sd.name}</text>
                        {hasDistrict && (
                          <text x={tipX + 10} y={tipY + 33} font-size="9" fill="#aaa">{sd.district}</text>
                        )}
                        <text x={tipX + 10} y={tipY + (hasDistrict ? 53 : 36)} font-size="10" fill="#ddd">
                          {sd.intervencions} {lang === 'cas' ? 'intervenciones' : 'intervencions'}
                        </text>
                        <text x={tipX + 10} y={tipY + (hasDistrict ? 69 : 52)} font-size="10" fill="#ddd">
                          {sd.quejas.toLocaleString('es-ES')} {tipoLabel}
                        </text>
                      </g>
                    );
                  })()}
                </svg>
              </div>
            </div>
            );
          })()}

          {!hideIntervenciones && (
          <p style="color: #666; font-size: 0.78rem; margin-top: 1.5rem; line-height: 1.5; max-width: 42rem;">
            <strong>Ratio</strong>: {lang === 'cas'
              ? 'intervenciones ciudadanas por cada 1.000 quejas. Un ratio alto indica que el distrito tiene una voz organizada fuerte además de quejas individuales. Un ratio bajo indica que los vecinos se quejan mucho pero apenas llegan al pleno.'
              : 'intervencions ciutadanes per cada 1.000 queixes. Un ratio alt indica que el districte té una veu organitzada forta a més de queixes individuals. Un ratio baix indica que els veïns es queixen molt però a penes arriben al ple.'}
          </p>
          )}

          {!hideIntervenciones && filtersAtDefault && geoMode === 'distrito' && (
            <div style="margin-top: 1.5rem; padding: 1rem 1.25rem; background: #fef8f5; border-left: 3px solid #e8562a; border-radius: 8px; max-width: 42rem;">
              <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.9rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.5rem;">
                {lang === 'cas' ? 'Lecturas del cruce' : 'Lectures del creuament'}
              </h3>
              <ul style="margin: 0; padding-left: 1.2rem; color: #444; font-size: 0.85rem; line-height: 1.6;">
                {lang === 'cas' ? (
                  <>
                    <li><strong>Poblats del Sud</strong> (25.5‰): el distrito con más activismo organizado en los plenos. Efecto DANA + tejido asociativo de las pedanías.</li>
                    <li><strong>Extramurs, Ciutat Vella, Poblats Marítims</strong> (~4‰): asociacionismo vecinal fuerte — La Roqueta, Cabanyal, centro histórico.</li>
                    <li><strong>Benicalap</strong> (0.3‰): distrito con alto volumen de quejas individuales pero poca voz organizada en el pleno.</li>
                    <li><strong>Algirós, El Pla del Real, Campanar</strong> (~1‰): distritos relativamente "silenciosos" en ambos canales.</li>
                  </>
                ) : (
                  <>
                    <li><strong>Poblats del Sud</strong> (25.5‰): el districte amb més activisme organitzat als plens. Efecte DANA + teixit associatiu de les pedanies.</li>
                    <li><strong>Extramurs, Ciutat Vella, Poblats Marítims</strong> (~4‰): associacionisme veïnal fort — La Roqueta, Cabanyal, centre històric.</li>
                    <li><strong>Benicalap</strong> (0.3‰): districte amb alt volum de queixes individuals però poca veu organitzada al ple.</li>
                    <li><strong>Algirós, El Pla del Real, Campanar</strong> (~1‰): districtes relativament "silenciosos" en ambdós canals.</li>
                  </>
                )}
              </ul>
            </div>
          )}
        </div>
      </section>

      {/* Sección B: temas */}
      <section style="padding: 2rem 1rem; background: #fafafa;">
        <div class="max-w-5xl mx-auto">
          <h2 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.4rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 0.5rem;">
            {lang === 'cas' ? 'Temas dominantes' : 'Temes dominants'}
          </h2>
          <p style="color: #666; margin-bottom: 1.25rem; max-width: 42rem; line-height: 1.6; font-size: 0.9rem;">
            {hideIntervenciones
              ? (lang === 'cas'
                  ? '¿De qué se queja la gente? Top 10 de las categorías oficiales con más volumen en el período seleccionado.'
                  : 'De què es queixa la gent? Top 10 de les categories oficials amb més volum en el període seleccionat.')
              : (lang === 'cas'
                  ? '¿De qué se queja la gente individualmente y de qué habla la ciudadanía organizada en el pleno? Las taxonomías son distintas, las quejas siguen los códigos oficiales del Ayuntamiento y las intervenciones la nuestra propia clasificación, pero la comparación revela prioridades muy diferentes.'
                  : 'De què es queixa la gent individualment i de què parla la ciutadania organitzada al ple? Les taxonomies són diferents, les queixes seguixen els codis oficials de l\'Ajuntament i les intervencions la nostra pròpia classificació, però la comparació revela prioritats molt diferents.')}
          </p>
          {!hideIntervenciones && (
            <p style="color: #555; margin-bottom: 1.25rem; max-width: 42rem; line-height: 1.7; font-size: 0.875rem; border-left: 3px solid #ffd4bc; padding-left: 1rem;">
              {lang === 'cas'
                ? <>La distancia entre estas dos listas es el descubrimiento. La gente individual se queja de limpieza, jardines y señalización. La ciudadanía organizada lleva al pleno derechos, urbanismo y participación. Son dos idiomas del mismo malestar vecinal. Uno cotidiano y concreto, el otro estructural y político.</>
                : <>La distància entre aquestes dues llistes és el descobriment. La gent individual es queixa de neteja, jardins i senyalització. La ciutadania organitzada porta al ple drets, urbanisme i participació. Són dos idiomes del mateix malestar veïnal. Un de quotidià i concret, l'altre d'estructural i polític.</>}
            </p>
          )}
          <div class={hideIntervenciones ? 'grid grid-cols-1 gap-4' : 'grid grid-cols-1 md:grid-cols-2 gap-4'}>
            <div style="background: #fff; border-radius: 12px; padding: 1.25rem; border: 1px solid #eee;">
              <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.9rem; font-weight: 700; color: #e8562a; margin-bottom: 0.25rem;">⚠️ {tipoLabel.charAt(0).toUpperCase() + tipoLabel.slice(1)}</h3>
              <p style="font-size: 0.7rem; color: #666; margin-bottom: 1rem;">Top 10</p>
              <div style="display: grid; gap: 0.4rem;">
                {sortedQuejaTemas.length === 0 ? (
                  <p style="font-size: 0.8rem; color: #aaa; font-style: italic;">—</p>
                ) : sortedQuejaTemas.map(([name, count]) => (
                  <div key={name} style="display: grid; grid-template-columns: 1fr 3rem; gap: 0.5rem; align-items: center;">
                    <div>
                      <div style="font-size: 0.75rem; margin-bottom: 0.2rem;">{name}</div>
                      <div style="height: 3px; background: #fef1ec; border-radius: 100px; overflow: hidden;">
                        <div style={`height: 100%; width: ${(count / maxQuejaTemaCount) * 100}%; background: #e8562a; border-radius: 100px;`}></div>
                      </div>
                    </div>
                    <span style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.7rem; font-weight: 700; text-align: right; color: #666;">
                      {count.toLocaleString('es-ES')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            {!hideIntervenciones && (
            <div style="background: #fff; border-radius: 12px; padding: 1.25rem; border: 1px solid #eee;">
              <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.9rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.25rem;">📣 {lang === 'cas' ? 'Intervenciones' : 'Intervencions'}</h3>
              <p style="font-size: 0.7rem; color: #666; margin-bottom: 1rem;">{lang === 'cas' ? 'Categorías' : 'Categories'}</p>
              <div style="display: grid; gap: 0.4rem;">
                {sortedIvCats.length === 0 ? (
                  <p style="font-size: 0.8rem; color: #aaa; font-style: italic;">—</p>
                ) : sortedIvCats.map(([cat, count]) => (
                  <div key={cat} style="display: grid; grid-template-columns: 1fr 3rem; gap: 0.5rem; align-items: center;">
                    <div>
                      <div style="font-size: 0.75rem; margin-bottom: 0.2rem;">{cat_labels[cat] || cat}</div>
                      <div style="height: 3px; background: #f0f0f0; border-radius: 100px; overflow: hidden;">
                        <div style={`height: 100%; width: ${(count / maxIvCatCount) * 100}%; background: #1e1e1e; border-radius: 100px;`}></div>
                      </div>
                    </div>
                    <span style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.7rem; font-weight: 700; text-align: right; color: #666;">{count}</span>
                  </div>
                ))}
              </div>
            </div>
            )}
          </div>

          {!hideIntervenciones && filtersAtDefault && (
            <div style="margin-top: 1.5rem; padding: 1rem 1.25rem; background: #fff; border-left: 3px solid #e8562a; border-radius: 8px; max-width: 42rem;">
              <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.9rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.5rem;">
                {lang === 'cas' ? 'Lecturas del cruce' : 'Lectures del creuament'}
              </h3>
              <ul style="margin: 0; padding-left: 1.2rem; color: #444; font-size: 0.85rem; line-height: 1.6;">
                {lang === 'cas' ? (
                  <>
                    <li>Las <strong>quejas</strong> se concentran en problemas concretos y cotidianos del espacio público: limpieza, reparaciones, señalización, ruido.</li>
                    <li>Las <strong>intervenciones en el pleno</strong> tienen un alcance más estructural: urbanismo, servicios públicos, participación, derechos.</li>
                    <li>La <strong>contaminación acústica</strong> es el único tema donde coinciden ambos canales, la gente se queja mucho y además llega al pleno.</li>
                    <li>Temas como <strong>derechos e igualdad</strong> aparecen casi solo en el pleno, requieren voz organizada.</li>
                  </>
                ) : (
                  <>
                    <li>Les <strong>queixes</strong> es concentren en problemes concrets i quotidians de l'espai públic: neteja, reparacions, senyalització, soroll.</li>
                    <li>Les <strong>intervencions al ple</strong> tenen un abast més estructural: urbanisme, serveis públics, participació, drets.</li>
                    <li>La <strong>contaminació acústica</strong> és l'únic tema on coincidixen ambdós canals, la gent es queixa molt i també arriba al ple.</li>
                    <li>Temes com els <strong>drets i igualtat</strong> apareixen quasi només al ple, requerixen veu organitzada.</li>
                  </>
                )}
              </ul>
            </div>
          )}
        </div>
      </section>

      {!hideIntervenciones && (
      /* Sección C: ranking */
      <section style="padding: 2rem 1rem; background: #fff;">
        <div class="max-w-5xl mx-auto">
          <h2 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.4rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 0.5rem;">
            {lang === 'cas' ? 'Índice de organización ciudadana' : "Índex d'organització ciutadana"}
          </h2>
          <p style="color: #666; margin-bottom: 1.25rem; max-width: 42rem; line-height: 1.6; font-size: 0.9rem;">
            {lang === 'cas'
              ? 'El ratio de intervenciones por 1.000 quejas permite clasificar los distritos según si tienen tejido asociativo capaz de llevar las preocupaciones vecinales al pleno, o si sus vecinos se expresan principalmente por la vía individual de la queja. Solo se consideran distritos con más de 100 quejas en el período para evitar distorsiones.'
              : 'El ratio d\'intervencions per 1.000 queixes permet classificar els districtes segons si tenen teixit associatiu capaç de portar les preocupacions veïnals al ple, o si els seus veïns s\'expressen principalment per la via individual de la queixa. Només es consideren districtes amb més de 100 queixes en el període per a evitar distorsions.'}
          </p>
          <div style="margin-bottom: 1.25rem; padding: 1rem 1.25rem; background: #fff; border-left: 3px solid #e8562a; border-radius: 8px; max-width: 42rem;">
            <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.9rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.5rem;">
              {lang === 'cas' ? '¿Qué mide este ratio?' : 'Què mesura este ratio?'}
            </h3>
            <p style="margin: 0; color: #444; font-size: 0.85rem; line-height: 1.6;">
              {lang === 'cas'
                ? <>No es una métrica de activismo absoluto sino de <strong>capacidad de canalizar demandas individuales en voz organizada</strong>. Un distrito con ratio alto tiene entidades vecinales que llevan los problemas del vecindario al pleno. Un ratio bajo sugiere que los vecinos se quejan individualmente pero no articulan esas demandas colectivamente. {cityMeanRatio > 0 && <>La media de la ciudad en el período seleccionado es <strong>{cityMeanRatio.toFixed(1)}‰</strong>.</>}</>
                : <>No és una mètrica d'activisme absolut sinó de <strong>capacitat de canalitzar demandes individuals en veu organitzada</strong>. Un districte amb ratio alt té entitats veïnals que porten els problemes del veïnatge al ple. Un ratio baix suggerix que els veïns es queixen individualment però no articulen ixes demandes col·lectivament. {cityMeanRatio > 0 && <>La mitjana de la ciutat en el període seleccionat és <strong>{cityMeanRatio.toFixed(1)}‰</strong>.</>}</>}
            </p>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div style="background: #fef8f5; border: 1px solid #ffd4bc; border-radius: 12px; padding: 1.25rem;">
              <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.9rem; font-weight: 700; color: #c2410c; margin-bottom: 0.75rem;">💪 {lang === 'cas' ? 'Más organizados' : 'Més organitzats'}</h3>
              {topActive.length === 0 ? (
                <p style="font-size: 0.8rem; color: #aaa; font-style: italic;">
                  {lang === 'cas' ? "El filtro actual no tiene suficientes barrios con datos. Cambia a 'Todos' para ver el ránking completo." : "El filtre actual no té prou barris amb dades suficients. Canvia a 'Tots' per veure el rànquing complet."}
                </p>
              ) : (
                <ol style="margin: 0; padding-left: 1.2rem;">
                  {topActive.map(d => (
                    <li key={d.name} style="padding: 0.35rem 0; border-bottom: 1px solid #fff; font-size: 0.85rem;">
                      <strong>{d.name}</strong>
                      <span style="float: right; font-family: 'Sora', system-ui, sans-serif; font-weight: 700; color: #e8562a;">{d.ratio.toFixed(1)}‰</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
            <div style="background: #fafafa; border: 1px solid #e5e5e5; border-radius: 12px; padding: 1.25rem;">
              <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.9rem; font-weight: 700; color: #666; margin-bottom: 0.75rem;">😶 {lang === 'cas' ? 'Menos organizados' : 'Menys organitzats'}</h3>
              {bottomActive.length === 0 ? (
                <p style="font-size: 0.8rem; color: #aaa; font-style: italic;">
                  {lang === 'cas' ? "El filtro actual no tiene suficientes barrios con datos. Cambia a 'Todos' para ver el ránking completo." : "El filtre actual no té prou barris amb dades suficients. Canvia a 'Tots' per veure el rànquing complet."}
                </p>
              ) : (
                <ol style="margin: 0; padding-left: 1.2rem;">
                  {bottomActive.map(d => (
                    <li key={d.name} style="padding: 0.35rem 0; border-bottom: 1px solid #fff; font-size: 0.85rem;">
                      <strong>{d.name}</strong>
                      <span style="float: right; font-family: 'Sora', system-ui, sans-serif; font-weight: 700; color: #666;">{d.ratio.toFixed(1)}‰</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        </div>
      </section>
      )}

      {/* Sección D: perfil por distrito */}
      <section style="padding: 2rem 1rem; background: #fafafa;">
        <div class="max-w-5xl mx-auto">
          <h2 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.4rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 0.5rem;">
            {lang === 'cas' ? 'Perfil por distrito' : 'Perfil per districte'}
          </h2>
          <p style="color: #666; margin-bottom: 1.25rem; max-width: 42rem; line-height: 1.6; font-size: 0.9rem;">
            {hideIntervenciones
              ? (lang === 'cas'
                  ? 'Selecciona un distrito (o haz clic en el mapa) para ver las quejas más frecuentes de sus vecinos en el período seleccionado.'
                  : 'Selecciona un districte (o fes clic al mapa) per vore les queixes més freqüents dels seus veïns en el període seleccionat.')
              : (lang === 'cas'
                  ? 'Selecciona un distrito (o haz clic en el mapa) para ver sus quejas más frecuentes, los temas que sus entidades llevan al pleno, y qué entidades vecinales intervienen con más frecuencia en el período seleccionado.'
                  : 'Selecciona un districte (o fes clic al mapa) per vore les seues queixes més freqüents, els temes que les seues entitats porten al ple, i quines entitats veïnals intervenen amb més freqüència en el període seleccionat.')}
          </p>

          <div style="display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1.25rem;">
            {districtNamesList.map(d => {
              const isActive = d === selectedDistrict;
              return (
                <button
                  key={d}
                  onClick={() => setSelectedDistrict(d)}
                  style={{
                    fontSize: '0.7rem', fontWeight: isActive ? '600' : '400',
                    color: isActive ? '#fff' : '#666',
                    background: isActive ? '#1e1e1e' : '#fff',
                    border: isActive ? 'none' : '1px solid #ddd',
                    borderRadius: '100px', padding: '4px 10px', cursor: 'pointer',
                  }}
                >{d}</button>
              );
            })}
          </div>

          {selectedProfile && (
            <>
              <div style={`display: grid; grid-template-columns: ${hideIntervenciones ? '1fr' : 'repeat(3, 1fr)'}; gap: 0.5rem; margin-bottom: 1rem;`}>
                <div style="background: #fef1ec; border-radius: 10px; padding: 0.75rem 1rem;">
                  <span style="display: block; font-family: 'Sora', system-ui, sans-serif; font-size: 1.3rem; font-weight: 800; color: #e8562a; line-height: 1;">{selectedProfile.quejas.toLocaleString('es-ES')}</span>
                  <span style="display: block; font-size: 0.65rem; color: #666; margin-top: 2px;">{tipoLabel}</span>
                </div>
                {!hideIntervenciones && (
                <div style="background: #f5f5f5; border-radius: 10px; padding: 0.75rem 1rem;">
                  <span style="display: block; font-family: 'Sora', system-ui, sans-serif; font-size: 1.3rem; font-weight: 800; color: #1e1e1e; line-height: 1;">{selectedProfile.intervencions}</span>
                  <span style="display: block; font-size: 0.65rem; color: #666; margin-top: 2px;">{lang === 'cas' ? 'intervenciones' : 'intervencions'}</span>
                </div>
                )}
                {!hideIntervenciones && (
                <div style="background: #fff; border: 1px solid #eee; border-radius: 10px; padding: 0.75rem 1rem;">
                  <span style="display: block; font-family: 'Sora', system-ui, sans-serif; font-size: 1.3rem; font-weight: 800; color: #1e1e1e; line-height: 1;">{selectedProfile.ratio.toFixed(1)}‰</span>
                  <span style="display: block; font-size: 0.65rem; color: #666; margin-top: 2px;">ratio</span>
                  {cityMeanRatio > 0 && selectedProfile.quejas > 0 && (
                    <span style="display: block; font-size: 0.6rem; color: #888; margin-top: 4px; line-height: 1.4;">
                      {selectedProfile.ratio === 0
                        ? (lang === 'cas' ? 'Sin intervenciones en el pleno en el período seleccionado.' : 'Cap intervenció al ple en el període seleccionat.')
                        : selectedProfile.ratio > cityMeanRatio * 2
                          ? (lang === 'cas' ? `Muy por encima de la media (${cityMeanRatio.toFixed(1)}‰), asociacionismo excepcionalmente activo.` : `Molt per damunt de la mitjana (${cityMeanRatio.toFixed(1)}‰), associacionisme excepcionalment actiu.`)
                          : selectedProfile.ratio > cityMeanRatio
                            ? (lang === 'cas' ? `Por encima de la media (${cityMeanRatio.toFixed(1)}‰).` : `Per damunt de la mitjana (${cityMeanRatio.toFixed(1)}‰).`)
                            : (lang === 'cas' ? `Por debajo de la media (${cityMeanRatio.toFixed(1)}‰).` : `Per davall de la mitjana (${cityMeanRatio.toFixed(1)}‰).`)}
                    </span>
                  )}
                </div>
                )}
              </div>

              <div class={hideIntervenciones ? 'grid grid-cols-1' : 'grid grid-cols-1 md:grid-cols-3 gap-3'}>
                <div style="background: #fff; border: 1px solid #eee; border-radius: 10px; padding: 0.9rem;">
                  <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.8rem; font-weight: 700; color: #e8562a; margin-bottom: 0.6rem;">⚠️ {lang === 'cas' ? 'Top quejas' : 'Top queixes'}</h4>
                  {selectedProfile.topQuejas.length === 0 ? <p style="font-size: 0.75rem; color: #aaa; font-style: italic;">—</p> : (
                    <div style="display: grid; gap: 0.35rem;">
                      {selectedProfile.topQuejas.map(t => (
                        <div key={t.name} style="display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.75rem;">
                          <span style="line-height: 1.3;">{t.name}</span>
                          <span style="color: #666; font-weight: 600; font-family: 'Sora', system-ui, sans-serif; flex-shrink: 0;">{t.count.toLocaleString('es-ES')}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {!hideIntervenciones && (
                <div style="background: #fff; border: 1px solid #eee; border-radius: 10px; padding: 0.9rem;">
                  <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.8rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.6rem;">📣 {lang === 'cas' ? 'Temas del pleno' : 'Temes del ple'}</h4>
                  {selectedProfile.topCats.length === 0 ? <p style="font-size: 0.75rem; color: #aaa; font-style: italic;">{lang === 'cas' ? 'Sin intervenciones' : 'Sense intervencions'}</p> : (
                    <div style="display: grid; gap: 0.35rem;">
                      {selectedProfile.topCats.map(c => (
                        <div key={c.name} style="display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.75rem;">
                          <span style="line-height: 1.3;">{cat_labels[c.name] || c.name}</span>
                          <span style="color: #666; font-weight: 600; font-family: 'Sora', system-ui, sans-serif; flex-shrink: 0;">{c.count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                )}
                {!hideIntervenciones && (
                <div style="background: #fff; border: 1px solid #eee; border-radius: 10px; padding: 0.9rem;">
                  <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.8rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.6rem;">🏛️ {lang === 'cas' ? 'Entidades' : 'Entitats'}</h4>
                  {selectedProfile.topEnts.length === 0 ? <p style="font-size: 0.75rem; color: #aaa; font-style: italic;">—</p> : (
                    <div style="display: grid; gap: 0.35rem;">
                      {selectedProfile.topEnts.map(e => (
                        <a key={e.id} href={`${entitats_path}${e.id}/`} style="display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.75rem; text-decoration: none; color: inherit;">
                          <span style="line-height: 1.3;">{e.name}</span>
                          <span style="color: #666; font-weight: 600; font-family: 'Sora', system-ui, sans-serif; flex-shrink: 0;">{e.count}</span>
                        </a>
                      ))}
                    </div>
                  )}
                </div>
                )}
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
