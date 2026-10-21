import type { APIRoute } from 'astro';
import { readData } from '../../utils/data.ts';

/** /textos/<id>.json: the full texts of one intervention. /intervencions/ and /mapa/ leave them out of
 *  their island props (they were 86 % of the data, issue #97); the text modal fetches them on open. */
export function getStaticPaths() {
  const intervencions: any[] = readData('intervencions.json');
  return intervencions.map((iv) => ({
    params: { id: iv.id },
    props: { text_cas: iv.text_cas ?? '', text_val: iv.text_val ?? '' },
  }));
}

export const GET: APIRoute = ({ props }) =>
  new Response(JSON.stringify(props), { headers: { 'Content-Type': 'application/json' } });
