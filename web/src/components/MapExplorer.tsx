import { useEffect, useRef, useState, useMemo } from 'preact/hooks';
import { TextModal } from './InterventionCard.tsx';

interface Intervention {
  id: string;
  pleno_id: string;
  fecha: string;
  mandat_id: string;
  intervinient: string;
  entitat: string;
  entitat_id: string;
  tipus_entitat: string;
  temes_v2: Record<string, string[]>;
  ambit: string;
  zones: string[];
  districtes: string[];
  resum_cas: string;
  resum_val: string;
}

interface Mandat {
  id: string;
  legislatura: string;
  inici: string;
  fi: string | null;
  alcalde: string;
}

interface Props {
  intervencions: Intervention[];
  mandats: Mandat[];
  lang: 'cas' | 'val';
  cat_labels: Record<string, string>;
  sub_labels: Record<string, string>;
  tipus_labels: Record<string, string>;
  temes_labels: Record<string, string>;
  modal_labels: {
    idioma_valenciano: string;
    idioma_castellano: string;
    ver_texto: string;
    ocultar_texto: string;
    traduccion: string;
    original: string;
    punts: string;
    en_representacio: string;
    en_nom_de: string;
    ambit_labels: Record<string, string>;
  };
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

function getColor(count: number, max: number): string {
  if (count === 0) return '#f0eeea';
  const ratio = count / max;
  if (ratio > 0.7) return '#c2410c';
  if (ratio > 0.5) return '#e8562a';
  if (ratio > 0.3) return '#f59e0b';
  if (ratio > 0.1) return '#fbbf24';
  return '#fef3c7';
}

function getFeatureName(feature: any, mode: string): string {
  const props = feature?.properties || {};
  if (mode === 'districte') {
    return DIST_NAMES[props.coddistrit] || props.nombre || '';
  }
  // `nom` is the name in barris_referencia.json (`nombre` is the portal's, upper case, no accents)
  return props.nom || props.nombre || '';
}

const selectStyle: Record<string, string> = {
  appearance: 'none',
  WebkitAppearance: 'none',
  fontFamily: "'Outfit', system-ui, sans-serif",
  fontSize: '0.8rem',
  fontWeight: '500',
  color: '#444',
  background: '#fff',
  border: '1px solid #ddd',
  borderRadius: '8px',
  padding: '7px 12px',
  width: '100%',
  cursor: 'pointer',
};

const selectActiveStyle: Record<string, string> = {
  ...selectStyle,
  color: '#1e1e1e',
  borderColor: '#e8562a',
  background: '#fef8f5',
};

export function MapExplorer({ intervencions, mandats, lang, cat_labels, sub_labels, tipus_labels, temes_labels, modal_labels }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const layerRef = useRef<any>(null);
  const [leaflet, setLeaflet] = useState<any>(null);

  // Filters
  const [mapMode, setMapMode] = useState<'districte' | 'barri'>('districte');
  const [categoria, setCategoria] = useState('');
  const [subcategoria, setSubcategoria] = useState('');
  const [tipus, setTipus] = useState('');
  const [selectedZone, setSelectedZone] = useState('');
  const [subZones, setSubZones] = useState<string[]>([]);
  const [zoneScope, setZoneScope] = useState<'totes' | 'compartides' | 'nomes'>('totes');
  const [sharedExpanded, setSharedExpanded] = useState(false);
  // A new zone (or map mode) starts without sub-filters
  useEffect(() => { setSubZones([]); setZoneScope('totes'); setSharedExpanded(false); setSheet('half'); }, [selectedZone, mapMode]);
  // Phone: the filters fold under a «Filtres (N)» button, and the zone panel is a bottom sheet
  // with three heights (header only, half the map, the whole map) that is dragged or tapped
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sheet, setSheet] = useState<'min' | 'half' | 'full'>('half');
  const sheetRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ y: number; h: number; moved: boolean } | null>(null);
  const [dragH, setDragH] = useState<number | null>(null);
  const [hoveredZone, setHoveredZone] = useState('');
  const [yearRange, setYearRange] = useState<[number, number]>([2019, 2026]);
  const [activeMandat, setActiveMandat] = useState<string | null>(null);
  const [modalIv, setModalIv] = useState<Intervention | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const animTimerRef = useRef<any>(null);

  // Derived data
  const allYears = useMemo(() => {
    const set = new Set<number>();
    for (const iv of intervencions) set.add(parseInt(iv.fecha.slice(0, 4)));
    return [...set].sort();
  }, [intervencions]);

  const minYear = allYears[0] || 2011;
  const maxYear = allYears[allYears.length - 1] || 2026;

  const allCategories = useMemo(() => {
    const set = new Set<string>();
    for (const iv of intervencions) {
      for (const cat of Object.keys(iv.temes_v2 || {})) set.add(cat);
    }
    return [...set].sort();
  }, [intervencions]);

  const allSubcategories = useMemo(() => {
    if (!categoria) return [];
    const set = new Set<string>();
    for (const iv of intervencions) {
      for (const s of (iv.temes_v2 || {})[categoria] || []) set.add(s);
    }
    return [...set].sort();
  }, [intervencions, categoria]);

  const allTipus = useMemo(() => {
    const set = new Set<string>();
    for (const iv of intervencions) set.add(iv.tipus_entitat);
    return [...set].sort();
  }, [intervencions]);

  // Filtered interventions: every filter except the selected zone, which only opens its panel.
  // The map always shows each zone's own count, so its colours and tooltips mean the same
  // with or without a selection (it used to recolour by interventions shared with the selection).
  const filtered = useMemo(() => {
    const am = activeMandat ? mandats.find(m => m.id === activeMandat) : null;
    return intervencions.filter((iv) => {
      if (am) {
        if (iv.fecha < am.inici) return false;
        if (am.fi && iv.fecha > am.fi) return false;
      } else {
        const year = parseInt(iv.fecha.slice(0, 4));
        if (year < yearRange[0] || year > yearRange[1]) return false;
      }
      if (categoria) {
        const tv2 = iv.temes_v2 || {};
        if (!(categoria in tv2)) return false;
        if (subcategoria && !(tv2[categoria] || []).includes(subcategoria)) return false;
      }
      if (tipus && iv.tipus_entitat !== tipus) return false;
      return true;
    });
  }, [intervencions, yearRange, activeMandat, categoria, subcategoria, tipus]);

  // Counts for map
  const geoCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const iv of filtered) {
      const arr = mapMode === 'districte' ? iv.districtes : iv.zones;
      for (const z of arr || []) {
        counts[z] = (counts[z] || 0) + 1;
      }
    }
    return counts;
  }, [filtered, mapMode]);

  const maxCount = useMemo(() => Math.max(...Object.values(geoCounts), 1), [geoCounts]);

  // Per-zone rich data: top entities and dominant theme
  const zoneData = useMemo(() => {
    type ZD = { topEntitats: string[]; topTema: string | null };
    const entitCounts: Record<string, Record<string, number>> = {};
    const temaCounts: Record<string, Record<string, number>> = {};
    // Same set as the counts, so a tooltip's entities and topic match its number
    for (const iv of filtered) {
      const arr = mapMode === 'districte' ? iv.districtes : iv.zones;
      for (const z of arr || []) {
        if (!entitCounts[z]) entitCounts[z] = {};
        entitCounts[z][iv.entitat] = (entitCounts[z][iv.entitat] || 0) + 1;
        for (const cat of Object.keys(iv.temes_v2 || {})) {
          if (!temaCounts[z]) temaCounts[z] = {};
          temaCounts[z][cat] = (temaCounts[z][cat] || 0) + 1;
        }
      }
    }
    const result: Record<string, ZD> = {};
    const allZones = new Set([...Object.keys(entitCounts), ...Object.keys(temaCounts)]);
    for (const z of allZones) {
      const ec = entitCounts[z] || {};
      const tc = temaCounts[z] || {};
      const topTemaEntry = Object.entries(tc).sort((a, b) => b[1] - a[1])[0];
      result[z] = {
        topEntitats: Object.entries(ec).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([n]) => n),
        topTema: topTemaEntry ? topTemaEntry[0] : null,
      };
    }
    return result;
  }, [filtered, mapMode]);

  // Ref for zoneData so Leaflet handlers always get fresh values without re-creating layers
  const zoneDataRef = useRef(zoneData);
  useEffect(() => { zoneDataRef.current = zoneData; }, [zoneData]);

  // Legend items based on current max
  const legendItems = useMemo(() => {
    const m = maxCount;
    const f = Math.floor;
    const items = [
      { color: '#f0eeea', label: '0' },
      { color: '#fef3c7', label: `1–${Math.max(1, f(0.1 * m))}` },
      { color: '#fbbf24', label: `${f(0.1 * m) + 1}–${f(0.3 * m)}` },
      { color: '#f59e0b', label: `${f(0.3 * m) + 1}–${f(0.5 * m)}` },
      { color: '#e8562a', label: `${f(0.5 * m) + 1}–${f(0.7 * m)}` },
      { color: '#c2410c', label: `${f(0.7 * m) + 1}+` },
    ];
    // Remove degenerate ranges (from > to)
    return items.filter((item, i) => {
      if (i < 2) return true;
      const parts = item.label.split('–');
      const from = parseInt(parts[0]);
      const to = parts[1] ? parseInt(parts[1]) : Infinity;
      return from <= m && from <= to;
    });
  }, [maxCount]);

  // The selected zone's interventions, before the "amb" sub-filters and the scope
  const zoneOf = (iv: Intervention) => (mapMode === 'districte' ? iv.districtes : iv.zones) || [];
  const zoneAll = useMemo(
    () => (selectedZone ? filtered.filter((iv) => zoneOf(iv).includes(selectedZone)) : []),
    [filtered, selectedZone, mapMode],
  );

  // Under the selected zone A: "amb B" sub-filters (A together with any of them) and a scope:
  // all of A, only shared with another zone, or only A. The data has no zone of origin, so
  // "amb B" is symmetric: the interventions that name both A and B.
  const zoneInterventions = useMemo(() => zoneAll.filter((iv) => {
    const zs = zoneOf(iv);
    if (subZones.length) return subZones.some((z) => zs.includes(z));
    if (zoneScope === 'compartides') return zs.length > 1;
    if (zoneScope === 'nomes') return zs.length === 1;
    return true;
  }), [zoneAll, subZones, zoneScope, mapMode]);

  // Other zones named by the selected zone's interventions, most shared first: each one can be
  // added as an "amb" sub-filter
  const sharedZones = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const iv of zoneAll) {
      for (const z of zoneOf(iv)) {
        if (z !== selectedZone) counts[z] = (counts[z] || 0) + 1;
      }
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [zoneAll, selectedZone, mapMode]);

  const toggleSubZone = (z: string) => {
    setZoneScope('totes');
    setSubZones((s) => (s.includes(z) ? s.filter((x) => x !== z) : [...s, z]));
  };

  const hasFilters = categoria || tipus || selectedZone || activeMandat || yearRange[0] !== minYear || yearRange[1] !== maxYear;

  // Animation play/stop
  function handlePlay() {
    if (isPlaying) {
      clearInterval(animTimerRef.current);
      setIsPlaying(false);
      return;
    }
    setIsPlaying(true);
    setActiveMandat(null);
    let current = minYear;
    setYearRange([current, current]);
    animTimerRef.current = setInterval(() => {
      current++;
      if (current > maxYear) {
        clearInterval(animTimerRef.current);
        setIsPlaying(false);
        setYearRange([minYear, maxYear]);
        return;
      }
      setYearRange([current, current]);
    }, 900);
  }

  // Clean up animation on unmount
  useEffect(() => {
    return () => { if (animTimerRef.current) clearInterval(animTimerRef.current); };
  }, []);

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
        zoomControl: true,
        attributionControl: false,
        dragging: true,
        scrollWheelZoom: true,
        doubleClickZoom: true,
        touchZoom: true,
      });
      map.setView([39.47, -0.377], 13);
      // The map's box changes size when the phone filters open or close
      new ResizeObserver(() => map.invalidateSize()).observe(mapRef.current!);
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

  // Update map layer
  useEffect(() => {
    if (!leaflet || !mapInstanceRef.current) return;
    const map = mapInstanceRef.current;
    const L = leaflet;
    if (layerRef.current) { map.removeLayer(layerRef.current); layerRef.current = null; }

    const file = mapMode === 'districte' ? '/districtes.geojson' : '/barris.geojson';
    const label = lang === 'cas' ? 'intervenciones' : 'intervencions';

    // A newer run (selecting a zone also resets its sub-filters: two runs in a row) supersedes
    // this one; without the check both fetches would add their layer
    let stale = false;
    fetch(file).then(r => r.json()).then(geojson => {
      if (stale) return;
      const geoLayer = L.geoJSON(geojson, {
        style: (feature: any) => {
          const name = getFeatureName(feature, mapMode);
          const count = geoCounts[name] || 0;
          const isSelected = name === selectedZone;
          const isSub = subZones.includes(name);   // an "amb" sub-filter: dashed outline
          return {
            fillColor: getColor(count, maxCount),
            weight: isSelected ? 3 : isSub ? 2.5 : (mapMode === 'districte' ? 1.5 : 1),
            color: isSelected ? '#e8562a' : isSub ? '#b83a14' : '#fff',
            dashArray: isSub ? '6 4' : undefined,
            fillOpacity: 0.85,
          };
        },
        onEachFeature: (feature: any, layer: any) => {
          const name = getFeatureName(feature, mapMode);
          const count = geoCounts[name] || 0;

          // Build enriched tooltip using ref (always fresh data)
          function buildTooltip() {
            const data = zoneDataRef.current[name];
            const topEntitats = data?.topEntitats?.slice(0, 2) ?? [];
            const topTema = data?.topTema ? (cat_labels[data.topTema] ?? data.topTema) : null;
            return `<div style="font-family: 'Sora', system-ui, sans-serif; text-align: center; min-width: 120px;">
              <strong style="font-size: 0.85rem;">${name}</strong><br/>
              <span style="font-size: 1.1rem; font-weight: 800; color: #e8562a;">${count}</span>
              <span style="font-size: 0.7rem; color: #666;"> ${label}</span>
              ${topEntitats.length ? `<div style="margin-top: 5px; font-size: 0.68rem; color: #555; text-align: left; line-height: 1.4;">${topEntitats.join('<br/>')}</div>` : ''}
              ${topTema ? `<div style="margin-top: 3px; font-size: 0.68rem; color: #999; text-align: left;">${topTema}</div>` : ''}
            </div>`;
          }

          layer.bindTooltip(buildTooltip(), { direction: 'top', className: 'district-tooltip' });

          layer.on('mouseover', function(this: any) {
            setHoveredZone(name);
            if (name !== selectedZone) this.setStyle({ weight: 2.5, color: '#e8562a', fillOpacity: 0.95 });
            this.setTooltipContent(buildTooltip());
          });
          layer.on('mouseout', function(this: any) {
            setHoveredZone('');
            geoLayer.resetStyle(this);
          });
          layer.on('click', (e: any) => {
            setSelectedZone(name === selectedZone ? '' : name);
            // Phone: keep the tapped spot in sight above the half-height sheet that opens (not the
            // zone's centre: Poblats del Sud's lies in the Albufera, far off the city)
            if (name !== selectedZone && window.matchMedia('(max-width: 767px)').matches) {
              map.panInside(e.latlng, { paddingTopLeft: [0, 24], paddingBottomRight: [0, map.getSize().y * 0.5 + 24] });
            }
          });
        },
      }).addTo(map);
      layerRef.current = geoLayer;
    });
    return () => { stale = true; };
  }, [mapMode, geoCounts, maxCount, leaflet, selectedZone, subZones]);

  // Zone hover info for sidebar (uses zoneData directly — fine since it's JSX render)
  // Hover wins: with a zone selected, hovering another shows that one without losing the selection
  const activeInfo = hoveredZone || selectedZone;
  const activeCount = activeInfo ? (geoCounts[activeInfo] || 0) : null;
  const activeZoneData = activeInfo ? zoneData[activeInfo] : null;
  const activeTema = activeZoneData?.topTema ? (cat_labels[activeZoneData.topTema] ?? activeZoneData.topTema) : null;

  // «També l'esmenten: L'Eixample 10 · …» in the zone panel; each name adds (or removes) an
  // "amb" sub-filter, so the list narrows to the interventions that name both zones
  const sharedLine = (max: number) => sharedZones.length > 0 && zoneScope !== 'nomes' && (
    <p style="font-size: 0.72rem; color: #666; line-height: 1.9; margin-bottom: 0.6rem;">
      <span style="color: #999;">{lang === 'cas' ? 'También la mencionan: ' : "També l'esmenten: "}</span>
      {(sharedExpanded ? sharedZones : sharedZones.slice(0, max)).map(([z, n], i) => {
        const on = subZones.includes(z);
        return (
          <>
            {i > 0 && <span style="color: #ccc;"> · </span>}
            <button
              onClick={() => toggleSubZone(z)}
              aria-pressed={on}
              style={on
                ? 'background: #e8562a; color: #fff; border: none; border-radius: 100px; padding: 1px 8px; cursor: pointer; font: inherit; font-weight: 600;'
                : 'background: none; border: none; padding: 0; cursor: pointer; color: #b83a14; font: inherit; text-decoration: underline; text-decoration-color: #f5c0a8; text-underline-offset: 2px;'}
            >{z}</button>
            <span style="color: #999;"> {n}</span>
          </>
        );
      })}
      {!sharedExpanded && sharedZones.length > max && (
        <button
          onClick={() => setSharedExpanded(true)}
          style="background: none; border: none; padding: 0; cursor: pointer; color: #999; font: inherit; text-decoration: underline;"
        > · +{sharedZones.length - max}</button>
      )}
    </p>
  );

  // What the panel's count is restricted to: « amb Patraix, L'Eixample», « compartides»…
  const zoneQualifier = subZones.length
    ? ` ${lang === 'cas' ? 'con' : 'amb'} ${subZones.join(', ')}`
    : zoneScope === 'compartides' ? ` ${lang === 'cas' ? 'compartidas con otras zonas' : 'compartides amb altres zones'}`
    : zoneScope === 'nomes' ? ` ${lang === 'cas' ? 'solo de' : 'només de'} ${selectedZone}`
    : '';

  // Under the zone chip: one chip per "amb" sub-filter, and the scope when there is none
  const scopeLabels = {
    totes: lang === 'cas' ? 'Todas' : 'Totes',
    compartides: lang === 'cas' ? 'Compartidas' : 'Compartides',
    nomes: lang === 'cas' ? `Solo ${selectedZone}` : `Només ${selectedZone}`,
  };
  const zoneSubFilters = selectedZone && (
    <div style="display: flex; flex-direction: column; gap: 0.35rem; margin-top: -0.4rem;">
      {subZones.map((z) => (
        <span style="font-size: 0.72rem; background: #fff; border: 1px dashed #e8a58a; color: #b83a14; padding: 3px 10px; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; margin-left: 0.9rem;">
          <span>↳ {lang === 'cas' ? 'con' : 'amb'} {z}</span>
          <button
            onClick={() => toggleSubZone(z)}
            style="background: none; border: none; cursor: pointer; color: #b83a14; font-size: 0.8rem; padding: 0 2px;"
            aria-label={lang === 'cas' ? `Quitar filtro con ${z}` : `Llevar filtre amb ${z}`}
          >✕</button>
        </span>
      ))}
      {subZones.length === 0 && (
        <div role="group" aria-label={lang === 'cas' ? 'Alcance de la zona' : 'Abast de la zona'} style="display: flex; gap: 0.25rem; margin-left: 0.9rem;">
          {(['totes', 'compartides', 'nomes'] as const).map((s) => (
            <button
              onClick={() => setZoneScope(s)}
              aria-pressed={zoneScope === s}
              style={{
                flex: '1', fontSize: '0.68rem', padding: '3px 6px', borderRadius: '100px', cursor: 'pointer',
                fontFamily: "'Outfit', system-ui, sans-serif",
                background: zoneScope === s ? '#fef1ec' : 'none',
                color: zoneScope === s ? '#b83a14' : '#888',
                border: zoneScope === s ? '1px solid #f5c0a8' : '1px solid #eee',
                fontWeight: zoneScope === s ? '600' : '400',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: '0',
              }}
            >{scopeLabels[s]}</button>
          ))}
        </div>
      )}
    </div>
  );

  const modeToggle = (
      <div style="display: flex; gap: 0.25rem; flex: 1;">
        {(['districte', 'barri'] as const).map(m => (
          <button
            key={m}
            onClick={() => { setMapMode(m); setSelectedZone(''); setHoveredZone(''); }}
            style={{
              fontFamily: "'Outfit', system-ui, sans-serif",
              fontSize: '0.75rem',
              fontWeight: mapMode === m ? '600' : '400',
              color: mapMode === m ? '#fff' : '#666',
              background: mapMode === m ? '#1e1e1e' : 'none',
              border: mapMode === m ? 'none' : '1px solid #ddd',
              borderRadius: '100px',
              padding: '5px 12px',
              cursor: 'pointer',
              flex: '1',
            }}
          >
            {m === 'districte' ? (lang === 'cas' ? 'Distritos' : 'Districtes') : (lang === 'cas' ? 'Barrios' : 'Barris')}
          </button>
        ))}
      </div>
  );

  const filterSelects = (
    <>
      {/* Category */}
      <select
        value={categoria}
        onChange={(e) => { setCategoria((e.target as HTMLSelectElement).value); setSubcategoria(''); }}
        style={categoria ? selectActiveStyle : selectStyle}
        aria-label={lang === 'cas' ? 'Tema' : 'Tema'}
      >
        <option value="">{lang === 'cas' ? 'Tema' : 'Tema'}</option>
        {allCategories.map(c => <option key={c} value={c}>{cat_labels[c] ?? c}</option>)}
      </select>

      {/* Subcategory */}
      {categoria && allSubcategories.length > 0 && (
        <select
          value={subcategoria}
          onChange={(e) => setSubcategoria((e.target as HTMLSelectElement).value)}
          style={subcategoria ? selectActiveStyle : selectStyle}
          aria-label="Subtema"
        >
          <option value="">{lang === 'cas' ? 'Subtema' : 'Subtema'}</option>
          {allSubcategories.map(s => <option key={s} value={s}>{sub_labels[s] ?? s}</option>)}
        </select>
      )}

      {/* Entity type */}
      <select
        value={tipus}
        onChange={(e) => setTipus((e.target as HTMLSelectElement).value)}
        style={tipus ? selectActiveStyle : selectStyle}
        aria-label={lang === 'cas' ? 'Tipo' : 'Tipus'}
      >
        <option value="">{lang === 'cas' ? 'Tipo entidad' : 'Tipus entitat'}</option>
        {allTipus.map(tp => <option key={tp} value={tp}>{tipus_labels[tp] ?? tp}</option>)}
      </select>
    </>
  );

  const resetButton = hasFilters && (
    <button
      onClick={() => { setCategoria(''); setSubcategoria(''); setTipus(''); setSelectedZone(''); setYearRange([minYear, maxYear]); setActiveMandat(null); }}
      style="background: none; border: 1px solid #e8562a; color: #e8562a; font-size: 0.75rem; font-weight: 500; padding: 6px 12px; border-radius: 100px; cursor: pointer; font-family: 'Outfit', system-ui, sans-serif; width: 100%;"
    >
      ✕ Reset
    </button>
  );

  const sidebar = (
    <div style="display: flex; flex-direction: column; gap: 0.75rem;">
      {modeToggle}
      {filterSelects}

      {/* Selected zone chip */}
      {selectedZone && (
        <span style="font-size: 0.75rem; background: #fef1ec; color: #b83a14; padding: 5px 12px; border-radius: 8px; font-weight: 600; display: flex; align-items: center; justify-content: space-between;">
          <span>📍 {selectedZone}</span>
          <button
            onClick={() => setSelectedZone('')}
            style="background: none; border: none; cursor: pointer; color: #b83a14; font-size: 0.85rem; padding: 0 2px;"
            aria-label={lang === 'cas' ? 'Quitar filtro de zona' : 'Llevar filtre de zona'}
          >✕</button>
        </span>
      )}
      {zoneSubFilters}

      {/* Hover/selection info panel */}
      {activeInfo && (
        <div style="background: #fef8f5; border: 1px solid #fde0d0; border-radius: 8px; padding: 8px 10px;">
          <div style="font-size: 0.8rem; font-weight: 700; color: #1e1e1e; margin-bottom: 2px;">{activeInfo}</div>
          <div style="font-size: 1rem; font-weight: 800; color: #e8562a; line-height: 1;">
            {activeCount}
            <span style="font-size: 0.7rem; font-weight: 400; color: #999; margin-left: 3px;">
              {lang === 'cas' ? 'intervenciones' : 'intervencions'}
            </span>
          </div>
          {activeTema && (
            <div style="font-size: 0.7rem; color: #666; margin-top: 3px;">{activeTema}</div>
          )}
          {activeZoneData?.topEntitats && activeZoneData.topEntitats.length > 0 && (
            <div style="font-size: 0.68rem; color: #999; margin-top: 3px; line-height: 1.4;">
              {activeZoneData.topEntitats.slice(0, 2).join(' · ')}
            </div>
          )}
          {activeInfo !== selectedZone && (activeCount ?? 0) > 0 && (
            <button
              onClick={() => setSelectedZone(activeInfo)}
              style="margin-top: 6px; font-size: 0.7rem; color: #e8562a; background: none; border: none; cursor: pointer; padding: 0; font-family: 'Outfit', system-ui, sans-serif; font-weight: 600;"
            >
              → {lang === 'cas' ? 'Ver intervenciones' : 'Veure intervencions'}
            </button>
          )}
        </div>
      )}

      {/* Count */}
      <div style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.85rem; font-weight: 700; color: #1e1e1e; text-align: center; padding: 0.5rem 0; border-top: 1px solid #f0f0f0;">
        {filtered.length}<span style="color: #aaa; font-weight: 400;"> / {intervencions.length}</span>
      </div>

      {resetButton}
    </div>
  );

  // Phone sheet: tap the header to step up (header → half → whole map → half), or drag it
  const sheetHeights = { min: null, half: '50%', full: '100%' } as const;
  const onSheetDown = (e: PointerEvent) => {
    if ((e.target as HTMLElement).closest('button')) return;
    dragRef.current = { y: e.clientY, h: sheetRef.current?.offsetHeight ?? 0, moved: false };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onSheetMove = (e: PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const dy = e.clientY - d.y;
    if (Math.abs(dy) > 6) d.moved = true;
    if (!d.moved) return;
    const max = sheetRef.current?.parentElement?.offsetHeight ?? 600;
    setDragH(Math.max(56, Math.min(max, d.h - dy)));
  };
  const onSheetUp = (e: PointerEvent) => {
    const d = dragRef.current;
    dragRef.current = null;
    if (!d) return;
    if (!d.moved) {
      setSheet(sheet === 'min' ? 'half' : sheet === 'half' ? 'full' : 'half');
    } else {
      // snap to the nearest of the three heights
      const max = sheetRef.current?.parentElement?.offsetHeight ?? 600;
      const h = d.h - (e.clientY - d.y);
      setSheet(h < max * 0.28 ? 'min' : h < max * 0.75 ? 'half' : 'full');
    }
    setDragH(null);
  };
  const nFilters = [categoria, subcategoria, tipus].filter(Boolean).length;

  return (
    <div style="display: flex; flex-direction: column; height: calc(100vh - 60px); height: calc(100dvh - 60px); font-family: 'Outfit', system-ui, sans-serif; position: relative; z-index: 0;">

      {/* Mobile: one row (map mode · Filtres (N) · count); the filters unfold under it */}
      <div class="md:hidden" style="padding: 0.5rem 1rem; border-bottom: 1px solid #eee; background: #fff;">
        <div style="display: flex; gap: 0.5rem; align-items: center;">
          {modeToggle}
          <button
            onClick={() => setFiltersOpen(!filtersOpen)}
            aria-expanded={filtersOpen}
            aria-controls="map-filters"
            style={{
              fontFamily: "'Outfit', system-ui, sans-serif", fontSize: '0.75rem', padding: '5px 12px', borderRadius: '100px', cursor: 'pointer',
              whiteSpace: 'nowrap', fontWeight: nFilters ? '600' : '400',
              background: nFilters ? '#fef1ec' : 'none', color: nFilters ? '#b83a14' : '#666',
              border: nFilters ? '1px solid #f5c0a8' : '1px solid #ddd',
            }}
          >
            {lang === 'cas' ? 'Filtros' : 'Filtres'}{nFilters ? ` (${nFilters})` : ''} {filtersOpen ? '▴' : '▾'}
          </button>
          <span style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.75rem; font-weight: 700; color: #1e1e1e; white-space: nowrap;">
            {filtered.length}<span style="color: #aaa; font-weight: 400;">/{intervencions.length}</span>
          </span>
        </div>
        {filtersOpen && (
          <div id="map-filters" style="display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.5rem;">
            {filterSelects}
            {resetButton}
          </div>
        )}
      </div>

      {/* Middle: sidebar (desktop) + map */}
      <div style="flex: 1; display: flex; overflow: hidden;">
        {/* Desktop sidebar */}
        <div class="hidden md:block" style="width: 260px; flex-shrink: 0; padding: 1rem; border-right: 1px solid #eee; background: #fff; overflow-y: auto;">
          {sidebar}
        </div>

        {/* Map */}
        <div style="flex: 1; position: relative;">
          <div ref={mapRef} style="width: 100%; height: 100%;" />

          {/* Color legend — bottom left */}
          <div class="map-legend" style="position: absolute; bottom: 24px; left: 8px; background: rgba(255,255,255,0.93); border: 1px solid #e5e5e5; border-radius: 8px; padding: 8px 10px; z-index: 400; font-family: 'Outfit', system-ui, sans-serif; box-shadow: 0 1px 4px rgba(0,0,0,0.08);">
            <div style="font-size: 0.6rem; font-weight: 600; color: #999; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 5px;">
              {lang === 'cas' ? 'Intervenciones' : 'Intervencions'}
            </div>
            {legendItems.map(({ color, label }) => (
              <div key={label} style="display: flex; align-items: center; gap: 6px; margin-bottom: 3px;">
                <div style={`width: 11px; height: 11px; border-radius: 2px; background: ${color}; border: 1px solid rgba(0,0,0,0.1); flex-shrink: 0;`} />
                <span style="font-size: 0.68rem; color: #555;">{label}</span>
              </div>
            ))}
          </div>

          {/* Zone detail panel — desktop: right overlay, mobile: bottom sheet */}
          {selectedZone && zoneAll.length > 0 && (
            <>
              {/* Desktop */}
              <div class="hidden md:block" style="position: absolute; top: 0; right: 0; width: 340px; max-height: 100%; overflow-y: auto; background: #fff; border-left: 1px solid #eee; box-shadow: -2px 0 8px rgba(0,0,0,0.08); z-index: 500; padding: 1rem;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem;">
                  <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1rem; font-weight: 700; color: #1e1e1e;">
                    📍 {selectedZone}
                  </h3>
                  <button onClick={() => setSelectedZone('')} aria-label={lang === 'cas' ? 'Cerrar panel' : 'Tancar panel'} style="background: none; border: none; cursor: pointer; color: #999; font-size: 1rem;">✕</button>
                </div>
                <p style="font-size: 0.75rem; color: #666; margin-bottom: 0.75rem;">
                  {zoneInterventions.length} {lang === 'cas' ? 'intervenciones' : 'intervencions'}{zoneQualifier}
                </p>
                {sharedLine(8)}
                {zoneInterventions.map(iv => (
                  <div
                    key={iv.id}
                    onClick={() => setModalIv(iv)}
                    style="padding: 0.5rem 0; border-bottom: 1px solid #f5f5f5; cursor: pointer; transition: background 0.1s;"
                    class="hover:bg-stone-50"
                  >
                    <div style="font-size: 0.7rem; color: #c94420; font-weight: 600; margin-bottom: 0.15rem;">{iv.fecha}</div>
                    <div style="font-size: 0.85rem; font-weight: 500; color: #1e1e1e; margin-bottom: 0.1rem;">{iv.entitat}</div>
                    <div style="font-size: 0.75rem; color: #666;">{iv.intervinient}</div>
                    <p style="font-size: 0.75rem; color: #666; margin-top: 0.25rem; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                      {lang === 'cas' ? iv.resum_cas : iv.resum_val}
                    </p>
                  </div>
                ))}
              </div>
              {/* Mobile */}
              <div
                ref={sheetRef}
                class="md:hidden"
                style={{
                  position: 'absolute', bottom: '0', left: '0', right: '0', zIndex: '1001',   // over Leaflet's zoom buttons (1000)
                  display: 'flex', flexDirection: 'column',
                  height: dragH !== null ? `${dragH}px` : (sheetHeights[sheet] ?? 'auto'),
                  transition: dragH !== null ? 'none' : 'height 0.2s ease',
                  background: '#fff', borderTop: '1px solid #eee', borderRadius: '14px 14px 0 0',
                  boxShadow: '0 -2px 10px rgba(0,0,0,0.1)',
                }}
              >
                {/* Header: the drag handle */}
                <div
                  onPointerDown={onSheetDown}
                  onPointerMove={onSheetMove}
                  onPointerUp={onSheetUp}
                  onPointerCancel={() => { dragRef.current = null; setDragH(null); }}
                  data-sheet-handle
                  style="touch-action: none; cursor: grab; padding: 0.4rem 1rem 0.5rem; flex-shrink: 0;"
                >
                  <div aria-hidden="true" style="width: 36px; height: 4px; border-radius: 100px; background: #ddd; margin: 0 auto 0.4rem;" />
                  <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;">
                    <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.9rem; font-weight: 700; min-width: 0;">
                      📍 {selectedZone} <span style="font-size: 0.7rem; font-weight: 400; color: #666;">· {zoneInterventions.length}{zoneQualifier}</span>
                    </h3>
                    <div style="display: flex; gap: 0.25rem; flex-shrink: 0;">
                      <button
                        onClick={() => setSheet(sheet === 'full' ? 'half' : 'full')}
                        aria-label={sheet === 'full' ? (lang === 'cas' ? 'Reducir panel' : 'Reduir panel') : (lang === 'cas' ? 'Ampliar panel' : 'Ampliar panel')}
                        style="background: none; border: none; cursor: pointer; color: #666; font-size: 1.1rem; padding: 2px 8px;"
                      >{sheet === 'full' ? '▾' : '▴'}</button>
                      <button onClick={() => setSelectedZone('')} aria-label={lang === 'cas' ? 'Cerrar panel' : 'Tancar panel'} style="background: none; border: none; cursor: pointer; color: #999; padding: 2px 6px;">✕</button>
                    </div>
                  </div>
                </div>
                {(sheet !== 'min' || dragH !== null) && (
                  <div style="flex: 1; min-height: 0; overflow-y: auto; padding: 0 1rem 0.75rem; overscroll-behavior: contain;">
                    <div style="margin: 0.4rem 0 0.6rem;">{zoneSubFilters}</div>
                    {sharedLine(4)}
                    {zoneInterventions.map(iv => (
                      <div key={iv.id} onClick={() => setModalIv(iv)} style="padding: 0.45rem 0; border-bottom: 1px solid #f5f5f5; cursor: pointer;">
                        <div style="font-size: 0.65rem; color: #c94420; font-weight: 600;">{iv.fecha}</div>
                        <div style="font-size: 0.8rem; font-weight: 500; color: #1e1e1e;">{iv.entitat}</div>
                        <p style="font-size: 0.72rem; color: #666; margin-top: 0.15rem; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                          {lang === 'cas' ? iv.resum_cas : iv.resum_val}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Year slider + play button */}
      <div style="padding: 0.75rem 1rem 1rem; background: #fff; border-top: 1px solid #eee;">
        <div style="display: flex; align-items: center; gap: 0.75rem; max-width: 640px; margin: 0 auto;">

          {/* Play button */}
          <button
            onClick={handlePlay}
            aria-label={isPlaying ? (lang === 'cas' ? 'Detener animación' : 'Aturar animació') : (lang === 'cas' ? 'Animar por año' : 'Animar per any')}
            style={{
              flexShrink: '0',
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              border: 'none',
              background: isPlaying ? '#1e1e1e' : '#e8562a',
              color: '#fff',
              cursor: 'pointer',
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background 0.15s',
            }}
          >
            {isPlaying ? '■' : '▶'}
          </button>

          <span style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.85rem; font-weight: 700; color: #1e1e1e; min-width: 2.5rem;">{yearRange[0]}</span>
          <div style="flex: 1; min-width: 0; position: relative;">
            {/* From slider */}
            <input
              type="range"
              min={minYear}
              max={maxYear}
              value={yearRange[0]}
              onInput={(e) => {
                const v = parseInt((e.target as HTMLInputElement).value);
                setYearRange([Math.min(v, yearRange[1]), yearRange[1]]);
                setActiveMandat(null);
                if (isPlaying) { clearInterval(animTimerRef.current); setIsPlaying(false); }
              }}
              style="width: 100%; position: absolute; top: 0; pointer-events: none; appearance: none; -webkit-appearance: none; background: transparent; height: 20px; z-index: 2;"
              class="range-thumb"
            />
            {/* To slider */}
            <input
              type="range"
              min={minYear}
              max={maxYear}
              value={yearRange[1]}
              onInput={(e) => {
                const v = parseInt((e.target as HTMLInputElement).value);
                setYearRange([yearRange[0], Math.max(v, yearRange[0])]);
                setActiveMandat(null);
                if (isPlaying) { clearInterval(animTimerRef.current); setIsPlaying(false); }
              }}
              style="width: 100%; position: absolute; top: 0; pointer-events: none; appearance: none; -webkit-appearance: none; background: transparent; height: 20px; z-index: 2;"
              class="range-thumb"
            />
            {/* Track */}
            <div style="height: 4px; background: #eee; border-radius: 100px; position: relative; top: 8px;">
              <div style={`position: absolute; height: 100%; background: #e8562a; border-radius: 100px; left: ${((yearRange[0] - minYear) / (maxYear - minYear)) * 100}%; right: ${100 - ((yearRange[1] - minYear) / (maxYear - minYear)) * 100}%;`} />
            </div>
            {/* Year marks: placed by percentage (as justify-content: space-between would), so 16 labels
                do not add up to a minimum width; on a phone only every fifth year shows (.year-minor) */}
            <div style="position: relative; height: 1rem; margin: 16px 2px 0;">
              {allYears.map((y, i) => {
                const p = allYears.length > 1 ? (i / (allYears.length - 1)) * 100 : 0;
                const minor = (y - minYear) % 5 !== 0 && y !== maxYear;
                return (
                  <span
                    key={y}
                    class={minor ? 'year-minor' : undefined}
                    style={`position: absolute; left: ${p}%; transform: translateX(-${p}%); font-size: 0.65rem; color: ${y >= yearRange[0] && y <= yearRange[1] ? '#1e1e1e' : '#ccc'}; font-weight: ${y >= yearRange[0] && y <= yearRange[1] ? '600' : '400'}; cursor: pointer;`}
                    onClick={() => { setYearRange([y, y]); setActiveMandat(null); if (isPlaying) { clearInterval(animTimerRef.current); setIsPlaying(false); } }}
                  >
                    {y}
                  </span>
                );
              })}
            </div>
          </div>
          <span style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.85rem; font-weight: 700; color: #1e1e1e; min-width: 2.5rem; text-align: right;">{yearRange[1]}</span>
        </div>
        {/* Mandate marks: their own row, which scrolls sideways on a phone */}
        <div class="mandate-row" style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.5rem auto 0; max-width: 640px; justify-content: center;">
          {[...mandats].sort((a, b) => a.inici.localeCompare(b.inici)).map(m => {
            const isActive = activeMandat === m.id;
            return (
              <button
                key={m.id}
                onClick={() => {
                  if (isPlaying) { clearInterval(animTimerRef.current); setIsPlaying(false); }
                  if (isActive) {
                    setActiveMandat(null);
                  } else {
                    setActiveMandat(m.id);
                    const from = parseInt(m.inici.slice(0, 4));
                    const to = m.fi ? parseInt(m.fi.slice(0, 4)) : maxYear;
                    setYearRange([from, to]);
                  }
                }}
                style={{
                  fontSize: '0.7rem',
                  color: isActive ? '#fff' : '#666',
                  background: isActive ? '#e8562a' : 'none',
                  border: isActive ? 'none' : '1px solid #ddd',
                  borderRadius: '100px',
                  padding: '4px 12px',
                  cursor: 'pointer',
                  fontFamily: "'Outfit', system-ui, sans-serif",
                  fontWeight: isActive ? '600' : '400',
                  transition: 'all 0.15s',
                  opacity: isPlaying ? '0.5' : '1',
                }}
              >
                {m.legislatura} · {m.alcalde.split(' ').slice(0, -1).join(' ')}
              </button>
            );
          })}
        </div>
      </div>

      <style>{`
        @media (max-width: 639px) { .year-minor { display: none; } }
        @media (max-width: 767px) {
          .map-legend { top: 8px; right: 8px; bottom: auto !important; left: auto !important; }
          .mandate-row { flex-wrap: nowrap !important; justify-content: flex-start !important; overflow-x: auto; scrollbar-width: none; }
          .mandate-row button { flex-shrink: 0; white-space: nowrap; }
        }
        .district-tooltip {
          background: #fff;
          border: 1px solid #eee;
          border-radius: 8px;
          padding: 8px 12px;
          box-shadow: 0 2px 10px rgba(0,0,0,0.12);
        }
        .district-tooltip .leaflet-tooltip-tip { display: none; }
        .range-thumb::-webkit-slider-thumb {
          -webkit-appearance: none;
          pointer-events: all;
          width: 18px;
          height: 18px;
          background: #e8562a;
          border-radius: 50%;
          border: 2px solid #fff;
          box-shadow: 0 1px 4px rgba(0,0,0,0.2);
          cursor: pointer;
        }
        .range-thumb::-moz-range-thumb {
          pointer-events: all;
          width: 14px;
          height: 14px;
          background: #e8562a;
          border-radius: 50%;
          border: 2px solid #fff;
          box-shadow: 0 1px 4px rgba(0,0,0,0.2);
          cursor: pointer;
        }
      `}</style>

      {/* Intervention text modal */}
      {modalIv && (
        <TextModal
          iv={modalIv}
          lang={lang}
          labels={modal_labels}
          temes_labels={temes_labels}
          onClose={() => setModalIv(null)}
        />
      )}
    </div>
  );
}
