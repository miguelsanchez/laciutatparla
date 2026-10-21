import type { APIRoute } from 'astro';
import { readData } from '../../utils/data.ts';

/** /<lang>/textos.json: id → full text in the page's language, for the search on /intervencions/.
 *  Fetched on the first query instead of shipping every text in the page (issue #97). */
export function getStaticPaths() {
  return [{ params: { lang: 'cas' } }, { params: { lang: 'val' } }];
}

export const GET: APIRoute = ({ params }) => {
  const field = params.lang === 'cas' ? 'text_cas' : 'text_val';
  const intervencions: any[] = readData('intervencions.json');
  const texts = Object.fromEntries(intervencions.map((iv) => [iv.id, iv[field] ?? '']));
  return new Response(JSON.stringify(texts), { headers: { 'Content-Type': 'application/json' } });
};
