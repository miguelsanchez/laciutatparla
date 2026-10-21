import rss from '@astrojs/rss';
import type { APIRoute } from 'astro';
import { readData } from '../../utils/data.ts';

export function getStaticPaths() {
  return [{ params: { lang: 'cas' } }, { params: { lang: 'val' } }];
}

export const GET: APIRoute = ({ params, site }) => {
  const lang = params.lang as 'cas' | 'val';
  const isCas = lang === 'cas';

  const intervencions: any[] = readData('intervencions.json');

  const sorted = [...intervencions]
    .sort((a, b) => (a.fecha < b.fecha ? 1 : -1))
    .slice(0, 50);

  const siteBase = (site?.href ?? 'https://laciutatparla.es/').replace(/\/$/, '');

  return rss({
    title: isCas
      ? 'La Ciutat Parla — Intervenciones ciudadanas'
      : "La Ciutat Parla — Intervencions ciutadanes",
    description: isCas
      ? 'Las últimas intervenciones ciudadanas en los plenos del Ajuntament de València.'
      : "Les darreres intervencions ciutadanes als plens de l'Ajuntament de València.",
    site: siteBase,
    items: sorted.map((iv) => {
      const title = iv.intervinient
        ? `${iv.intervinient} — ${iv.entitat}`
        : iv.entitat;
      const description = isCas
        ? (iv.resum_cas ?? iv.resum_val ?? '')
        : (iv.resum_val ?? iv.resum_cas ?? '');
      return {
        title,
        description,
        pubDate: new Date(iv.fecha),
        link: `/${lang}/intervencions/${iv.id}/`,
      };
    }),
    customData: `<language>${isCas ? 'es' : 'ca'}</language>`,
  });
};
