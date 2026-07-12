import { useState, useMemo, useEffect } from 'preact/hooks';

/**
 * Blocks B and C of the "Cruces" section:
 *   B. Participación (presupuestos) × Intervenciones al pleno — scatter
 *   C. Los 3 canales juntos — per-district ranking table
 *
 * Block A (Quejas × Intervenciones) is handled by AnalysisExplorer itself.
 */

interface Intervention {
  id: string;
  districtes: string[];
  zones: string[];
}

interface DistrictSeries {
  total_ediciones: number;
  pct_pob_16: number | null;
}

interface BarriSeries {
  total_ediciones: number;
  pct_pob_16: number | null;
}

interface QuejasTipoData {
  districts: Record<string, { total: number }>;
  barris?: Record<string, { total: number }>;
}

interface QuejasData {
  by_tipo: { queja: QuejasTipoData; sugerencia: QuejasTipoData };
}

interface BarriPoblacion {
  district: string;
  poblacion_por_anyo: Record<string, number>;
}

interface Props {
  intervencions: Intervention[];
  barriToDistrict: Record<string, string>;
  participantes_por_distrito: Record<string, DistrictSeries>;
  participantes_por_barri: Record<string, BarriSeries>;
  barriPoblacion: Record<string, BarriPoblacion>;
  quejas: QuejasData;
  lang: 'cas' | 'val';
}

const ALL_DISTRICTS = [
  'Ciutat Vella', "L'Eixample", 'Extramurs', 'Campanar', 'La Saïdia',
  'El Pla del Real', "L'Olivereta", 'Patraix', 'Jesús', 'Quatre Carreres',
  'Poblats Marítims', 'Camins al Grau', 'Algirós', 'Benimaclet',
  'Rascanya', 'Benicalap', 'Poblats del Nord', "Poblats de l'Oest",
  'Poblats del Sud',
];

// District-level population (empadronament ~2025, whole district). Used to
// normalise intervention count and quejas. Matches presupuestos_oficial.json
// distribución_presupuestaria_2025 (pob_total per district).
const POB_DISTRITO: Record<string, number> = {
  'Ciutat Vella': 30002, "L'Eixample": 44631, 'Extramurs': 50643,
  'Campanar': 40917, 'La Saïdia': 48383, 'El Pla del Real': 31020,
  "L'Olivereta": 51474, 'Patraix': 59417, 'Jesús': 53582,
  'Quatre Carreres': 80266, 'Poblats Marítims': 56843,
  'Camins al Grau': 67453, 'Algirós': 36266, 'Benimaclet': 28541,
  'Rascanya': 56703, 'Benicalap': 50152, 'Poblats del Nord': 7009,
  "Poblats de l'Oest": 15261, 'Poblats del Sud': 22043,
};

function fmt(n: number): string {
  return n.toLocaleString('es-ES');
}

// Union of explicit districts + districts derived from zones via barriToDistrict.
// Each intervention counted at most once per district.
function effectiveDistricts(iv: Intervention, barriToDistrict: Record<string, string>): Set<string> {
  const s = new Set<string>();
  for (const d of iv.districtes || []) s.add(d);
  for (const z of iv.zones || []) {
    const d = barriToDistrict[z];
    if (d) s.add(d);
  }
  return s;
}

export function CrucesExplorer({
  intervencions, barriToDistrict, participantes_por_distrito,
  participantes_por_barri, barriPoblacion, quejas, lang,
}: Props) {

  const [activeBlock, setActiveBlock] = useState<'B' | 'C'>('B');

  useEffect(() => {
    function handler(e: Event) {
      const block = (e as CustomEvent).detail?.block as 'B' | 'C';
      if (block === 'B' || block === 'C') setActiveBlock(block);
    }
    window.addEventListener('cruce-show-block', handler);
    return () => window.removeEventListener('cruce-show-block', handler);
  }, []);

  // ============================================================
  // Per-district metric table (foundation for B and C-distrito)
  // ============================================================
  const districtData = useMemo(() => {
    const ivsByDist: Record<string, number> = Object.fromEntries(ALL_DISTRICTS.map(d => [d, 0]));
    for (const iv of intervencions) {
      for (const d of effectiveDistricts(iv, barriToDistrict)) {
        if (d in ivsByDist) ivsByDist[d] += 1;
      }
    }
    const quejasByDist: Record<string, number> = Object.fromEntries(ALL_DISTRICTS.map(d => [d, 0]));
    for (const d of ALL_DISTRICTS) {
      const q = quejas.by_tipo.queja.districts[d]?.total || 0;
      const s = quejas.by_tipo.sugerencia.districts[d]?.total || 0;
      quejasByDist[d] = q + s;
    }
    return ALL_DISTRICTS.map((d) => {
      const pob = POB_DISTRITO[d] || 1;
      const part = participantes_por_distrito[d]?.pct_pob_16 || 0;
      return {
        name: d,
        district: '', // not used at district level
        pob,
        quejas: quejasByDist[d],
        quejas_per_1000: (quejasByDist[d] / pob) * 1000,
        participacion_pct: part,
        intervenciones: ivsByDist[d],
      };
    });
  }, [intervencions, barriToDistrict, participantes_por_distrito, quejas]);

  // ============================================================
  // Per-barri metric table (for C-barri)
  // ============================================================
  const barriData = useMemo(() => {
    // Intervenciones per barri — count iv.zones directly.
    const ivsByBarri: Record<string, number> = {};
    for (const iv of intervencions) {
      const seen = new Set<string>();
      for (const z of iv.zones || []) {
        if (!seen.has(z)) {
          seen.add(z);
          ivsByBarri[z] = (ivsByBarri[z] || 0) + 1;
        }
      }
    }
    // Quejas per barri — sum queja + sugerencia
    const quejasByBarri: Record<string, number> = {};
    const qBarris = quejas.by_tipo.queja.barris || {};
    const sBarris = quejas.by_tipo.sugerencia.barris || {};
    for (const b of new Set([...Object.keys(qBarris), ...Object.keys(sBarris)])) {
      quejasByBarri[b] = (qBarris[b]?.total || 0) + (sBarris[b]?.total || 0);
    }

    // All canonical barris we have data for (union of presupuestos + poblacion)
    const allBarris = new Set<string>([
      ...Object.keys(participantes_por_barri),
      ...Object.keys(barriPoblacion),
    ]);

    const rows: any[] = [];
    for (const b of allBarris) {
      const pob = barriPoblacion[b]?.poblacion_por_anyo?.['2025']
               || barriPoblacion[b]?.poblacion_por_anyo?.['2024']
               || 0;
      const part = participantes_por_barri[b]?.pct_pob_16 || 0;
      const q = quejasByBarri[b] || 0;
      const i = ivsByBarri[b] || 0;
      if (pob === 0) continue; // skip if no population reference
      rows.push({
        name: b,
        district: barriToDistrict[b] || '',
        pob,
        quejas: q,
        quejas_per_1000: (q / pob) * 1000,
        participacion_pct: part,
        intervenciones: i,
      });
    }
    return rows;
  }, [intervencions, quejas, participantes_por_barri, barriPoblacion, barriToDistrict]);

  return (
    <div style="font-family: 'Outfit', system-ui, sans-serif;">
      {activeBlock === 'B' && <ScatterParticipacionIntervenciones data={districtData} lang={lang} />}
      {activeBlock === 'C' && <TresCanalesTable districtData={districtData} barriData={barriData} lang={lang} />}
    </div>
  );
}

// ================================================================
// Block B — Scatter: Participación × Intervenciones
// Both axes are broken: the 0→mainMax segment takes most of the plot so
// the cluster doesn't get squashed by the two outlier districts (Pobles
// del Nord in X, Poblats del Sud in Y). A "//" mark indicates the break.
// ================================================================

// Piecewise linear scale with a gap between the main range and a compressed
// outlier range. Values in the gap (between mainMax and secMin) clamp to the
// main-range end so outliers never land in the visual gap.
function brokenScale(
  v: number,
  mainMax: number,
  secMin: number,
  secMax: number,
  plotStart: number,
  plotLen: number,
  mainFraction: number,
  gapFraction: number,
) {
  const mainLen = plotLen * mainFraction;
  const gapLen = plotLen * gapFraction;
  const secLen = plotLen * (1 - mainFraction - gapFraction);
  const mainEnd = plotStart + mainLen;
  const secStart = mainEnd + gapLen;
  const secEnd = plotStart + plotLen;
  if (v <= mainMax) return plotStart + (v / mainMax) * mainLen;
  if (v < secMin) return mainEnd; // shouldn't happen with well-chosen thresholds
  const f = Math.min(1, (v - secMin) / Math.max(1e-9, secMax - secMin));
  return secStart + f * secLen;
}

function ScatterParticipacionIntervenciones({
  data, lang,
}: {
  data: ReturnType<typeof useDistrictData>;
  lang: 'cas' | 'val';
}) {
  const [popup, setPopup] = useState<string | null>(null);

  // Thresholds chosen from the data.
  // X = intervenciones: 18 districts fit under 30 (most 3-15), Poblats del Sud ≈ 59.
  const X_MAIN_MAX = 35;
  const X_SEC_MIN = 55;
  const X_SEC_MAX = 60;
  // Y = participación: 17 districts sit in 8-14%, Poblats de l'Oest (16%), Poblats
  // del Sud (21%) push the main range to 22%, Poblats del Nord (48%) is the outlier.
  const Y_MAIN_MAX = 22;
  const Y_SEC_MIN = 45;
  const Y_SEC_MAX = 50;

  const MAIN_F = 0.78;  // 78% of plot for main range
  const GAP_F  = 0.06;  // 6% visual gap

  const W = 600, H = 420;
  const padL = 56, padR = 20, padT = 30, padB = 52;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const x = (v: number) => brokenScale(v, X_MAIN_MAX, X_SEC_MIN, X_SEC_MAX, padL, plotW, MAIN_F, GAP_F);
  // Y axis is inverted (higher = further from bottom)
  const yInv = (v: number) => brokenScale(v, Y_MAIN_MAX, Y_SEC_MIN, Y_SEC_MAX, 0, plotH, MAIN_F, GAP_F);
  const y = (v: number) => padT + plotH - yInv(v);

  // Geometry of the axis break marks
  const xGapStart = padL + plotW * MAIN_F;
  const xGapEnd = xGapStart + plotW * GAP_F;
  const yGapStart = padT + plotH - plotH * MAIN_F;      // upper edge of Y main range gap
  const yGapEnd = yGapStart - plotH * GAP_F;            // lower edge of Y sec range

  return (
    <section style="padding: 2rem 1rem; background: #fff;">
      <div class="max-w-5xl mx-auto">
        <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.3rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin-bottom: 0.5rem;">
          {lang === 'cas' ? 'B. Presupuestos participativos × Intervenciones al pleno' : 'B. Pressupostos participatius × Intervencions al ple'}
        </h3>
        <div style="color: #666; max-width: 42rem; line-height: 1.6; font-size: 0.9rem; margin-bottom: 1.25rem;">
          {lang === 'cas' ? (
            <>
              <p style="margin: 0 0 0.75rem;">Quejas y sugerencias no requieren esfuerzo organizado, basta un formulario. Los presupuestos participativos e intervenir en el pleno sí: ambos exigen dedicación deliberada, aunque por vías muy distintas. Los presupuestos participativos canalizan la energía vecinal hacia proyectos concretos de inversión local. El pleno municipal exige articular una posición, representar una entidad y comparecer ante la corporación.</p>
              <p style="margin: 0;">La pregunta de este cruce es si ambas formas de participación organizada van de la mano. Si los mismos distritos que movilizan a su ciudadanía en los presupuestos también generan más intervenciones al pleno, los puntos formarían una diagonal ascendente. Si no la forman, si los canales captan perfiles distintos de ciudadanía organizada, el patrón revelará algo más interesante: que movilizar a la gente en un canal no garantiza que llegue al otro.</p>
            </>
          ) : (
            <>
              <p style="margin: 0 0 0.75rem;">Queixes i suggeriments no requereixen esforç organitzat, n'hi ha prou amb un formulari. Els pressupostos participatius i intervenir al ple sí: tots dos exigixen dedicació deliberada, tot i que per vies molt distintes. Els pressupostos participatius canalitzen l'energia veïnal cap a projectes concrets d'inversió local. El ple municipal exigix articular una posició, representar una entitat i comparèixer davant la corporació.</p>
              <p style="margin: 0;">La pregunta d'aquest creuament és si ambdues formes de participació organitzada van de la mà. Si els mateixos districtes que mobilitzen la seua ciutadania en els pressupostos també generen més intervencions al ple, els punts formarien una diagonal ascendent. Si no la formen, si els canals capten perfils distints de ciutadania organitzada, el patró revelarà alguna cosa més interessant: que mobilitzar la gent en un canal no garantix que arribe a l'altre.</p>
            </>
          )}
        </div>

        <div style="background: #fafafa; border-radius: 12px; padding: 1rem; border: 1px solid #eee;">
          <svg viewBox={`0 0 ${W} ${H}`} style="width: 100%; height: auto; display: block; font-family: 'Outfit', system-ui, sans-serif;"
               onClick={() => setPopup(null)}>
            {/* axes — main segments (skip the gap) */}
            {/* X axis */}
            <line x1={padL} y1={padT + plotH} x2={xGapStart} y2={padT + plotH} stroke="#ccc" stroke-width="1" />
            <line x1={xGapEnd} y1={padT + plotH} x2={padL + plotW} y2={padT + plotH} stroke="#ccc" stroke-width="1" />
            {/* Y axis */}
            <line x1={padL} y1={padT + plotH} x2={padL} y2={yGapStart} stroke="#ccc" stroke-width="1" />
            <line x1={padL} y1={yGapEnd} x2={padL} y2={padT} stroke="#ccc" stroke-width="1" />

            {/* break marks — two small diagonal slashes on each axis */}
            {/* X break */}
            <g stroke="#999" stroke-width="1" fill="none">
              <line x1={xGapStart - 2} y1={padT + plotH + 4} x2={xGapStart + 4} y2={padT + plotH - 4} />
              <line x1={xGapEnd - 4}  y1={padT + plotH + 4} x2={xGapEnd + 2}  y2={padT + plotH - 4} />
            </g>
            {/* Y break */}
            <g stroke="#999" stroke-width="1" fill="none">
              <line x1={padL - 4} y1={yGapStart + 2}  x2={padL + 4} y2={yGapStart - 4} />
              <line x1={padL - 4} y1={yGapEnd + 4}    x2={padL + 4} y2={yGapEnd - 2} />
            </g>

            {/* axis labels */}
            <text x={padL + plotW / 2} y={H - 12} text-anchor="middle" font-size="11" fill="#666">
              {lang === 'cas' ? '→ intervenciones al pleno' : '→ intervencions al ple'}
            </text>
            <text x="14" y={padT + plotH / 2} text-anchor="middle" font-size="11" fill="#666"
                  transform={`rotate(-90 14 ${padT + plotH / 2})`}>
              {lang === 'cas' ? '→ % participación en presupuestos' : '→ % participació en pressupostos'}
            </text>

            {/* X ticks (intervenciones): 0, mainMax, secMin, secMax */}
            <text x={padL}      y={padT + plotH + 14} text-anchor="middle" font-size="10" fill="#999">0</text>
            <text x={xGapStart} y={padT + plotH + 14} text-anchor="middle" font-size="10" fill="#999">{X_MAIN_MAX}</text>
            <text x={xGapEnd}   y={padT + plotH + 14} text-anchor="middle" font-size="10" fill="#999">{X_SEC_MIN}</text>
            <text x={padL + plotW} y={padT + plotH + 14} text-anchor="middle" font-size="10" fill="#999">{X_SEC_MAX}</text>
            {/* Y ticks (% participación): 0, mainMax, secMin, secMax */}
            <text x={padL - 6} y={padT + plotH + 3}   text-anchor="end" font-size="10" fill="#999">0</text>
            <text x={padL - 6} y={yGapStart + 3}      text-anchor="end" font-size="10" fill="#999">{Y_MAIN_MAX}%</text>
            <text x={padL - 6} y={yGapEnd + 3}        text-anchor="end" font-size="10" fill="#999">{Y_SEC_MIN}%</text>
            <text x={padL - 6} y={padT + 4}           text-anchor="end" font-size="10" fill="#999">{Y_SEC_MAX}%</text>

            {/* faint gridlines at main-range end for readability */}
            <line x1={xGapStart} y1={padT} x2={xGapStart} y2={padT + plotH} stroke="#eee" stroke-width="0.5" stroke-dasharray="2,3" />
            <line x1={padL} y1={yGapStart} x2={padL + plotW} y2={yGapStart} stroke="#eee" stroke-width="0.5" stroke-dasharray="2,3" />

            {/* quadrant hints */}
            <text x={padL + plotW - 6} y={padT + 12} text-anchor="end" font-size="10" fill="#c2410c" font-weight="600">
              {lang === 'cas' ? '↗ activos en ambos' : '↗ actius en ambdós'}
            </text>
            <text x={padL + 6} y={padT + plotH - 6} text-anchor="start" font-size="10" fill="#999" font-weight="600">
              {lang === 'cas' ? '↙ silenciosos' : '↙ silenciosos'}
            </text>

            {/* points */}
            {data.map((d) => {
              const cx = x(d.intervenciones);
              const cy = y(d.participacion_pct);
              const isSel = popup === d.name;
              const labelRight = cx < padL + plotW * 0.65;
              return (
                <g key={d.name} style="cursor: pointer;"
                   onClick={(e: any) => { e.stopPropagation(); setPopup(prev => prev === d.name ? null : d.name); }}>
                  <circle cx={cx} cy={cy} r={isSel ? 7 : 5}
                          fill={isSel ? '#e8562a' : 'rgba(232, 86, 42, 0.65)'}
                          stroke={isSel ? '#1e1e1e' : '#fff'} stroke-width={isSel ? 2 : 1} />
                  <text x={labelRight ? cx + 9 : cx - 9} y={cy + 3}
                        text-anchor={labelRight ? 'start' : 'end'} font-size="9.5"
                        fill={isSel ? '#1e1e1e' : '#555'} font-weight={isSel ? '700' : '400'}
                        style="pointer-events: none;">
                    {d.name}
                  </text>
                </g>
              );
            })}

            {/* popup */}
            {(() => {
              if (!popup) return null;
              const sd = data.find(x => x.name === popup);
              if (!sd) return null;
              const cx = x(sd.intervenciones);
              const cy = y(sd.participacion_pct);
              const tipW = 200, tipH = 66;
              const tipX = cx + tipW + 14 > W - 10 ? cx - tipW - 10 : cx + 12;
              const tipY = cy - tipH - 10 < 5 ? cy + 12 : cy - tipH - 8;
              return (
                <g style="pointer-events: none;">
                  <rect x={tipX} y={tipY} width={tipW} height={tipH} rx="6" fill="#1e1e1e" opacity="0.95" />
                  <text x={tipX + 10} y={tipY + 18} font-size="11" font-weight="700" fill="#fff">{sd.name}</text>
                  <text x={tipX + 10} y={tipY + 36} font-size="10" fill="#ddd">
                    {sd.participacion_pct.toFixed(1)}% {lang === 'cas' ? 'participación' : 'participació'}
                  </text>
                  <text x={tipX + 10} y={tipY + 52} font-size="10" fill="#ddd">
                    {sd.intervenciones} {lang === 'cas' ? 'intervenciones' : 'intervencions'}
                  </text>
                </g>
              );
            })()}
          </svg>
        </div>

        <div style="color: #555; font-size: 0.85rem; margin-top: 1.25rem; line-height: 1.65; max-width: 42rem;">
          {lang === 'cas' ? (
            <>
              <p style="margin: 0 0 0.75rem;"><strong>Los puntos no forman una diagonal.</strong> Los dos canales captan perfiles distintos.</p>
              <p style="margin: 0 0 0.75rem;"><strong>Pobles del Nord</strong> es el caso más extremo: 48% de participación acumulada en presupuestos participativos, el triple de la media de la ciudad, pero apenas 1 intervención al pleno en 7 años. Su tejido vecinal es compacto y activo, pero se vuelca hacia dentro: propone y vota proyectos para su propio territorio, sin dar el salto a la esfera formal del pleno municipal.</p>
              <p style="margin: 0 0 0.75rem;"><strong>Poblats del Sud</strong> hace el recorrido contrario: lidera en intervenciones al pleno con 73 en el período analizado, impulsadas sobre todo por el activismo post-DANA y el tejido asociativo de las pedanías del sur. Su participación en presupuestos es alta pero no excepcional.</p>
              <p style="margin: 0 0 0.75rem;">Los distritos urbanos consolidados, Extramurs, Ciutat Vella, Poblats Marítims, ocupan la zona media en ambos ejes: asociacionismo veterano que participa en presupuestos y además llega al pleno, sin dominar ninguno de los dos canales de forma extrema.</p>
              <p style="margin: 0;">La conclusión práctica: invertir en movilización ciudadana para presupuestos participativos no garantiza que esa energía se traslade al pleno. Son circuitos distintos con perfiles distintos de ciudadanía organizada. Una política de participación robusta necesita cultivar los dos.</p>
            </>
          ) : (
            <>
              <p style="margin: 0 0 0.75rem;"><strong>Els punts no formen una diagonal.</strong> Els dos canals capten perfils distints.</p>
              <p style="margin: 0 0 0.75rem;"><strong>Pobles del Nord</strong> és el cas més extrem: 48% de participació acumulada en pressupostos participatius, el triple de la mitjana de la ciutat, però a penes 1 intervenció al ple en 7 anys. El seu teixit veïnal és compacte i actiu, però s'aboca cap a dins: proposa i vota projectes per al seu propi territori, sense donar el salt a l'esfera formal del ple municipal.</p>
              <p style="margin: 0 0 0.75rem;"><strong>Poblats del Sud</strong> fa el recorregut contrari: lidera en intervencions al ple amb 73 en el període analitzat, impulsades sobretot per l'activisme post-DANA i el teixit associatiu de les pedanies del sud. La seua participació en pressupostos és alta però no excepcional.</p>
              <p style="margin: 0 0 0.75rem;">Els districtes urbans consolidats, Extramurs, Ciutat Vella, Poblats Marítims, ocupen la zona mitjana en tots dos eixos: associacionisme veterà que participa en pressupostos i a més arriba al ple, sense dominar cap dels dos canals de forma extrema.</p>
              <p style="margin: 0;">La conclusió pràctica: invertir en mobilització ciutadana per a pressupostos participatius no garantix que eixa energia es traslladi al ple. Són circuits distints amb perfils distints de ciutadania organitzada. Una política de participació robusta necessita cultivar tots dos.</p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

// Auxiliary type helper
function useDistrictData(): any { return []; }

// ================================================================
// Block C — 3-channel ranking table (with distrito/barri toggle)
// ================================================================
function TresCanalesTable({
  districtData, barriData, lang,
}: {
  districtData: any[];
  barriData: any[];
  lang: 'cas' | 'val';
}) {
  type SortKey = 'name' | 'quejas_per_1000' | 'participacion_pct' | 'intervenciones' | 'perfil';
  const [geoMode, setGeoMode] = useState<'distrito' | 'barri'>('distrito');
  const [sortCol, setSortCol] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const activeData = geoMode === 'distrito' ? districtData : barriData;

  // Compute z-scores within the current mode (so rankings are relative to
  // the set of 19 districts or the set of 87 barris, not mixed)
  const withScores = useMemo(() => {
    const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
    const std  = (xs: number[], m: number) => Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length);

    const qs = activeData.map((d: any) => d.quejas_per_1000);
    const ps = activeData.map((d: any) => d.participacion_pct);
    const is = activeData.map((d: any) => d.intervenciones);

    const qm = mean(qs), ps_m = mean(ps), im = mean(is);
    const qs_std = std(qs, qm) || 1;
    const ps_std = std(ps, ps_m) || 1;
    const is_std = std(is, im) || 1;

    return activeData.map((d: any) => {
      const zq = (d.quejas_per_1000 - qm) / qs_std;
      const zp = (d.participacion_pct - ps_m) / ps_std;
      const zi = (d.intervenciones - im) / is_std;
      let perfil: string;
      const aboveQ = zq > 0.4, aboveP = zp > 0.4, aboveI = zi > 0.4;
      const belowQ = zq < -0.4, belowP = zp < -0.4, belowI = zi < -0.4;
      if (aboveQ && aboveP && aboveI) perfil = lang === 'cas' ? 'Organizado' : 'Organitzat';
      else if (belowQ && belowP && belowI) perfil = lang === 'cas' ? 'Silencioso' : 'Silenciós';
      else if (aboveP && aboveI && !aboveQ) perfil = lang === 'cas' ? 'Organizado' : 'Organitzat';
      else if (aboveQ && !aboveP && !aboveI) perfil = lang === 'cas' ? 'Queja individual' : 'Queixa individual';
      else if (aboveP && !aboveQ && !aboveI) perfil = lang === 'cas' ? 'Presupuestario' : 'Pressupostari';
      else if (aboveI && !aboveP && !aboveQ) perfil = lang === 'cas' ? 'Plenario' : 'Plenari';
      else perfil = lang === 'cas' ? 'Mixto' : 'Mixt';
      return { ...d, zq, zp, zi, perfil };
    });
  }, [activeData, lang]);

  const sorted = useMemo(() => {
    if (!sortCol) return withScores;
    const arr = [...withScores];
    arr.sort((a: any, b: any) => {
      if (sortCol === 'name' || sortCol === 'perfil') {
        return sortDir === 'asc' ? a[sortCol].localeCompare(b[sortCol]) : b[sortCol].localeCompare(a[sortCol]);
      }
      const av = a[sortCol] as number;
      const bv = b[sortCol] as number;
      return sortDir === 'asc' ? av - bv : bv - av;
    });
    return arr;
  }, [withScores, sortCol, sortDir]);

  function onSort(col: SortKey) {
    if (sortCol !== col) { setSortCol(col); setSortDir('desc'); return; }
    if (sortDir === 'desc') { setSortDir('asc'); return; }
    setSortCol(null); setSortDir('desc');
  }

  function sortArrow(col: SortKey) {
    if (sortCol !== col) return '';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  // Colour cell based on z-score
  function zColor(z: number): string {
    if (z > 1.0) return '#c2410c';
    if (z > 0.4) return '#e8562a';
    if (z < -1.0) return '#94a3b8';
    if (z < -0.4) return '#cbd5e1';
    return '#fbbf24';
  }
  function zBg(z: number): string {
    if (z > 1.0) return '#fef1ec';
    if (z > 0.4) return '#fff7ed';
    if (z < -1.0) return '#f1f5f9';
    if (z < -0.4) return '#f8fafc';
    return '#fffbeb';
  }

  return (
    <section style="padding: 2rem 1rem; background: #fff; border-top: 1px solid #eee;">
      <div class="max-w-5xl mx-auto">
        <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
          <h3 style="font-family: 'Sora', system-ui, sans-serif; font-size: 1.3rem; font-weight: 700; color: #1e1e1e; letter-spacing: -0.02em; margin: 0;">
            {lang === 'cas' ? 'C. Los tres canales juntos' : 'C. Els tres canals junts'}
          </h3>
          <div style="display: flex; gap: 0.25rem; margin-left: auto;">
            {(['distrito', 'barri'] as const).map((m) => (
              <button
                key={m}
                onClick={() => { setGeoMode(m); setSortCol(null); }}
                style={{
                  fontSize: '0.75rem',
                  fontWeight: geoMode === m ? '600' : '400',
                  color: geoMode === m ? '#fff' : '#666',
                  background: geoMode === m ? '#1e1e1e' : 'none',
                  border: geoMode === m ? 'none' : '1px solid #ddd',
                  borderRadius: '100px',
                  padding: '5px 12px',
                  cursor: 'pointer',
                }}
              >
                {m === 'distrito'
                  ? (lang === 'cas' ? 'Por distrito' : 'Per districte')
                  : (lang === 'cas' ? 'Por barrio' : 'Per barri')}
              </button>
            ))}
          </div>
        </div>
        <div style="color: #666; max-width: 42rem; line-height: 1.6; font-size: 0.9rem; margin-bottom: 1.25rem;">
          {geoMode === 'distrito' ? (
            lang === 'cas' ? (
              <>
                <p style="margin: 0 0 0.75rem;">Los cruces anteriores comparaban los canales de dos en dos. Este los pone juntos. La pregunta final es si existe algún distrito que destaque en los tres a la vez, o si cada canal tiene sus propios protagonistas.</p>
                <p style="margin: 0 0 0.75rem;">Cada distrito recibe una puntuación en los tres canales, normalizada por población para que el tamaño no distorsione la comparación. La última columna sintetiza el perfil dominante de cada distrito según dónde concentra su energía cívica:</p>
                <ul style="margin: 0; padding-left: 1.2rem; font-size: 0.85rem; line-height: 1.7;">
                  <li><strong>Organizado</strong>: por encima de la media en los tres canales. La voz vecinal llega a todas partes.</li>
                  <li><strong>Presupuestario</strong>: alta participación en presupuestos participativos, pero baja presencia en quejas y en el pleno. Energía cívica canalizada hacia proyectos locales concretos.</li>
                  <li><strong>Queja individual</strong>: más quejas individuales que participación organizada. Malestar que no se articula colectivamente.</li>
                  <li><strong>Silencioso</strong>: por debajo de la media en los tres canales. No significa ausencia de malestar, sino ausencia de canales para expresarlo.</li>
                  <li><strong>Mixto</strong>: sin dominancia clara en ningún canal. El perfil más frecuente.</li>
                </ul>
              </>
            ) : (
              <>
                <p style="margin: 0 0 0.75rem;">Els creuaments anteriors comparaven els canals de dos en dos. Aquest els posa junts. La pregunta final és si hi ha algun districte que destaque en els tres a la vegada, o si cada canal té els seus propis protagonistes.</p>
                <p style="margin: 0 0 0.75rem;">Cada districte rep una puntuació en els tres canals, normalitzada per població perquè la mida no distorsione la comparació. L'última columna sintetitza el perfil dominant de cada districte segons on concentra la seua energia cívica:</p>
                <ul style="margin: 0; padding-left: 1.2rem; font-size: 0.85rem; line-height: 1.7;">
                  <li><strong>Organitzat</strong>: per damunt de la mitjana en els tres canals. La veu veïnal arriba a tot arreu.</li>
                  <li><strong>Pressupostari</strong>: alta participació en pressupostos participatius, però baixa presència en queixes i al ple. Energia cívica canalitzada cap a projectes locals concrets.</li>
                  <li><strong>Queixa individual</strong>: més queixes individuals que participació organitzada. Malestar que no s'articula col·lectivament.</li>
                  <li><strong>Silenciós</strong>: per davall de la mitjana en els tres canals. No significa absència de malestar, sinó absència de canals per a expressar-lo.</li>
                  <li><strong>Mixt</strong>: sense dominància clara en cap canal. El perfil més freqüent.</li>
                </ul>
              </>
            )
          ) : (
            lang === 'cas'
              ? 'Mismo ranking pero desagregado por barrios. Los z-scores se recalculan respecto a la media de los barrios de la ciudad (no a la media de distritos). Intervenciones cuenta solo las intervenciones donde el barrio aparece explícitamente en el texto, por eso hay muchos barrios con 0.'
              : 'Mateix rànquing però desagregat per barris. Els z-scores es recalculen respecte a la mitjana dels barris de la ciutat (no a la mitjana de districtes). Intervencions compta només les intervencions on el barri apareix explícitament en el text, per això hi ha molts barris amb 0.'
          )}
        </div>

        <div style={`border: 1px solid #eee; border-radius: 12px; overflow: hidden; background: #fff; ${geoMode === 'barri' ? 'max-height: 560px; overflow-y: auto;' : ''}`}>
          <div style="display: grid; grid-template-columns: minmax(10rem, 1.7fr) minmax(5rem, 1fr) minmax(5rem, 1fr) minmax(5rem, 1fr) minmax(6rem, 1.3fr); gap: 0; padding: 0.6rem 0.4rem; background: #fafafa; border-bottom: 1px solid #eee; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #666; position: sticky; top: 0;">
            <span onClick={() => onSort('name')} style="cursor: pointer; user-select: none; padding: 0 0.5rem;">
              {geoMode === 'distrito'
                ? (lang === 'cas' ? 'Distrito' : 'Districte')
                : (lang === 'cas' ? 'Barrio' : 'Barri')}
              {sortArrow('name')}
            </span>
            <span onClick={() => onSort('quejas_per_1000')} style="cursor: pointer; user-select: none; text-align: right; padding: 0 0.5rem; color: #e8562a;">
              {lang === 'cas' ? 'Quejas / 1k' : 'Queixes / 1k'}{sortArrow('quejas_per_1000')}
            </span>
            <span onClick={() => onSort('participacion_pct')} style="cursor: pointer; user-select: none; text-align: right; padding: 0 0.5rem; color: #d97706;">
              {lang === 'cas' ? '% participación' : '% participació'}{sortArrow('participacion_pct')}
            </span>
            <span onClick={() => onSort('intervenciones')} style="cursor: pointer; user-select: none; text-align: right; padding: 0 0.5rem; color: #1e1e1e;">
              {lang === 'cas' ? 'Intervenciones' : 'Intervencions'}{sortArrow('intervenciones')}
            </span>
            <span onClick={() => onSort('perfil')} style="cursor: pointer; user-select: none; padding: 0 0.5rem;">
              {lang === 'cas' ? 'Perfil' : 'Perfil'}{sortArrow('perfil')}
            </span>
          </div>
          {sorted.map((d: any) => (
            <div key={d.name}
                 style="display: grid; grid-template-columns: minmax(10rem, 1.7fr) minmax(5rem, 1fr) minmax(5rem, 1fr) minmax(5rem, 1fr) minmax(6rem, 1.3fr); gap: 0; align-items: center; padding: 0.55rem 0.4rem; border-bottom: 1px solid #f5f5f5; font-size: 0.82rem;">
              <div style="padding: 0 0.5rem; min-width: 0;">
                <div style="font-weight: 500; line-height: 1.2; overflow: hidden; text-overflow: ellipsis;">{d.name}</div>
                {geoMode === 'barri' && d.district && (
                  <div style="font-size: 0.65rem; color: #aaa; margin-top: 1px;">{d.district}</div>
                )}
              </div>
              <span style={`text-align: right; padding: 0.25rem 0.5rem; background: ${zBg(d.zq)}; color: ${zColor(d.zq)}; font-family: 'Sora', system-ui, sans-serif; font-weight: 700; border-radius: 4px; margin: 0 0.3rem;`}>
                {d.quejas_per_1000.toFixed(0)}
              </span>
              <span style={`text-align: right; padding: 0.25rem 0.5rem; background: ${zBg(d.zp)}; color: ${zColor(d.zp)}; font-family: 'Sora', system-ui, sans-serif; font-weight: 700; border-radius: 4px; margin: 0 0.3rem;`}>
                {d.participacion_pct.toFixed(1)}%
              </span>
              <span style={`text-align: right; padding: 0.25rem 0.5rem; background: ${zBg(d.zi)}; color: ${zColor(d.zi)}; font-family: 'Sora', system-ui, sans-serif; font-weight: 700; border-radius: 4px; margin: 0 0.3rem;`}>
                {d.intervenciones}
              </span>
              <span style="padding: 0 0.5rem; font-size: 0.75rem; color: #555;">
                {d.perfil}
              </span>
            </div>
          ))}
        </div>

        {geoMode === 'distrito' && (
          <div style="margin-top: 1.5rem; max-width: 42rem; color: #444; font-size: 0.875rem; line-height: 1.7;">
            {lang === 'cas' ? (
              <>
                <p style="margin: 0 0 0.75rem;"><strong>Ningún distrito lidera los tres canales a la vez.</strong> Ese es el hallazgo central.</p>
                <p style="margin: 0 0 0.75rem;"><strong>Poblats del Sud</strong> es el único clasificado como Organizado: combina un volumen alto de quejas, una participación notable en presupuestos y 73 intervenciones al pleno, el segundo registro más alto de la ciudad. El efecto DANA y el tejido asociativo histórico de las pedanías del sur explican buena parte de esta actividad.</p>
                <p style="margin: 0 0 0.75rem;"><strong>Poblats del Nord</strong> hace lo contrario: lidera en presupuestos participativos con un 48,4% de participación acumulada, muy por encima de cualquier otro distrito, pero aparece casi ausente en quejas y en el pleno. Su tejido vecinal canaliza su energía hacia la participación presupuestaria, no hacia la esfera formal municipal.</p>
                <p style="margin: 0 0 0.75rem;">Los perfiles Silencioso, L'Olivereta y Benicalap, son los que más requieren atención: no es que sus vecinos estén satisfechos, sino que ninguno de los tres canales recoge bien su voz. Un cuarto de la ciudad vive en distritos que están por debajo de la media en los tres indicadores.</p>
                <p style="margin: 0;">Catorce de diecinueve distritos son Mixto, lo que indica que Valencia tiene una participación ciudadana relativamente distribuida, sin monopolios claros de activismo. Pero esa uniformidad también oculta que ningún distrito ha construido todavía un modelo de participación realmente fuerte en todos los frentes al mismo tiempo.</p>
              </>
            ) : (
              <>
                <p style="margin: 0 0 0.75rem;"><strong>Cap districte lidera els tres canals a la vegada.</strong> Eixe és el descobriment central.</p>
                <p style="margin: 0 0 0.75rem;"><strong>Poblats del Sud</strong> és l'únic classificat com a Organitzat: combina un volum alt de queixes, una participació notable en pressupostos i 73 intervencions al ple, el segon registre més alt de la ciutat. L'efecte DANA i el teixit associatiu històric de les pedanies del sud expliquen bona part d'aquesta activitat.</p>
                <p style="margin: 0 0 0.75rem;"><strong>Poblats del Nord</strong> fa el contrari: lidera en pressupostos participatius amb un 48,4% de participació acumulada, molt per damunt de qualsevol altre districte, però apareix quasi absent en queixes i al ple. El seu teixit veïnal canalitza la seua energia cap a la participació pressupostària, no cap a l'esfera formal municipal.</p>
                <p style="margin: 0 0 0.75rem;">Els perfils Silenciós, L'Olivereta i Benicalap, són els que més requerixen atenció: no és que els seus veïns estiguen satisfets, sinó que cap dels tres canals recull bé la seua veu. Un quart de la ciutat viu en districtes que estan per davall de la mitjana en els tres indicadors.</p>
                <p style="margin: 0;">Catorze de dènou districtes són Mixt, la qual cosa indica que València té una participació ciutadana relativament distribuïda, sense monopolis clars d'activisme. Però eixa uniformitat també oculta que cap districte ha construït encara un model de participació realment fort en tots els fronts al mateix temps.</p>
              </>
            )}
          </div>
        )}

        <div style="margin-top: 1.25rem; padding: 0.9rem 1.1rem; background: #fafafa; border-left: 3px solid #1e1e1e; border-radius: 6px; max-width: 42rem;">
          <h4 style="font-family: 'Sora', system-ui, sans-serif; font-size: 0.85rem; font-weight: 700; color: #1e1e1e; margin-bottom: 0.5rem;">
            {lang === 'cas' ? 'Cómo se lee la tabla' : 'Com es llig la taula'}
          </h4>
          <ul style="margin: 0; padding-left: 1.2rem; color: #444; font-size: 0.8rem; line-height: 1.6;">
            <li>
              <strong>{lang === 'cas' ? 'Quejas / 1k' : 'Queixes / 1k'}</strong>: {lang === 'cas' ? 'quejas y sugerencias por cada 1.000 habitantes del distrito (acumulado 2020-2026).' : 'queixes i suggeriments per cada 1.000 habitants del districte (acumulat 2020-2026).'}
            </li>
            <li>
              <strong>{lang === 'cas' ? '% participación' : '% participació'}</strong>: {lang === 'cas' ? 'porcentaje de población ≥16 años que ha participado al menos una vez en presupuestos participativos (8 ediciones).' : 'percentatge de població ≥16 anys que ha participat almenys una vegada en pressupostos participatius (8 edicions).'}
            </li>
            <li>
              <strong>{lang === 'cas' ? 'Intervenciones' : 'Intervencions'}</strong>: {lang === 'cas' ? 'total de intervenciones en el pleno entre 2019 y 2026 que referencian al distrito (explícita o via barrio).' : "total d'intervencions al ple entre 2019 i 2026 que referencien al districte (explícita o via barri)."}
            </li>
            <li>
              {lang === 'cas'
                ? <>Los colores reflejan la <strong>distancia a la media</strong> de la ciudad: naranja intenso = muy por encima, gris intenso = muy por debajo.</>
                : <>Els colors reflecteixen la <strong>distància a la mitjana</strong> de la ciutat: taronja intens = molt per damunt, gris intens = molt per davall.</>}
            </li>
          </ul>
          <p style="margin: 0.75rem 0 0; font-size: 0.78rem; color: #888; line-height: 1.5;">
            {lang === 'cas'
              ? 'Nota: las tres columnas no cubren el mismo período. Quejas: 2020-2026. Presupuestos participativos: 2015-2026 (8 ediciones). Intervenciones al pleno: 2019-2026. Los perfiles se calculan con los datos disponibles en cada canal, no sobre un período común.'
              : 'Nota: les tres columnes no cobrixen el mateix període. Queixes: 2020-2026. Pressupostos participatius: 2015-2026 (8 edicions). Intervencions al ple: 2019-2026. Els perfils es calculen amb les dades disponibles en cada canal, no sobre un període comú.'}
          </p>
        </div>
      </div>
    </section>
  );
}
