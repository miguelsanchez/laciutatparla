export function formatFecha(fecha: string, lang: 'cas' | 'val'): string {
  const [y, m, d] = fecha.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString(lang === 'val' ? 'ca-ES' : 'es-ES', {
    day: 'numeric', month: 'short', year: 'numeric',
  });
}

export function withCanonicalEntitat(
  ivs: any[],
  entitats: any[],
  lang: 'cas' | 'val',
): any[] {
  const byId: Record<string, any> = Object.fromEntries(entitats.map((e: any) => [e.id, e]));
  return ivs.map((iv: any) => {
    const ent = byId[iv.entitat_id];
    if (!ent) return iv;
    const nom = (lang === 'val' ? ent.nom_val : ent.nom_cas) ?? ent.nom_cas ?? iv.entitat;
    return nom !== iv.entitat ? { ...iv, entitat: nom } : iv;
  });
}

/** Interventions for the list islands (/intervencions/, /mapa/) without their full texts, which were
 *  86 % of the data and made both pages weigh 6–7 MB (issue #97). The text modal fetches them from
 *  /textos/<id>.json and the search from /<lang>/textos.json. */
export function withoutTexts(ivs: any[]): any[] {
  return ivs.map(({ text_cas, text_val, text_original, ...iv }: any) => iv);
}

export function formatIntervinient(name: string, lang: 'cas' | 'val'): string {
  const parts = name.split(',').map(s => s.trim()).filter(Boolean);
  if (parts.length <= 1) return name;
  const connector = lang === 'val' ? ' i ' : ' y ';
  return parts.slice(0, -1).join(', ') + connector + parts[parts.length - 1];
}
