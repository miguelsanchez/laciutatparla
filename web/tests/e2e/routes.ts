// The site's routes, as [cas, val] pairs, with detail pages taken from the fixture.
import { readFileSync } from 'fs';
import { resolve } from 'path';

const FIXTURE = resolve(process.cwd(), 'tests/fixtures/data');
const read = (name: string) => JSON.parse(readFileSync(resolve(FIXTURE, name), 'utf-8'));

export const interventions: any[] = read('intervencions.json');
export const entities: any[] = read('entitats.json');
export const plenos: any[] = read('plenos.json');

/** A named speaker (older actas anonymise them as [***]) and their pleno, for content checks. */
const NAMED = interventions.find((iv) => iv.intervinient && !iv.intervinient.includes('*'))!;
export const PLENO_SPEAKER: string = NAMED.intervinient;
export const PLENO = plenos.find((p) => p.id === NAMED.pleno_id)!;
export const INTERVENTION = interventions[0];
export const ENTITY = entities.find((e) => e.num_intervencions > 0)!;

export const PAIRS: [string, string][] = [
  ['', ''],
  ['plens/', 'plens/'],
  ['intervencions/', 'intervencions/'],
  ['entitats/', 'entitats/'],
  ['mapa/', 'mapa/'],
  ['otras-voces/', 'altres-veus/'],
  ['la-ciutat/', 'la-ciutat/'],
  ['datos/', 'dades/'],
  ['analisis/', 'analisi/'],
  ['metodologia/', 'metodologia/'],
  ['legal/', 'legal/'],
  [`plens/${PLENO.id}/`, `plens/${PLENO.id}/`],
  [`intervencions/${INTERVENTION.id}/`, `intervencions/${INTERVENTION.id}/`],
  [`entitats/${ENTITY.id}/`, `entitats/${ENTITY.id}/`],
];

export const url = (lang: 'cas' | 'val', path: string) => `/${lang}/${path}`;
