import { t } from '../i18n/index.ts';
import type { Lang } from '../i18n/index.ts';

export function getCatLabels(lang: Lang): Record<string, string> {
  return {
    urbanisme: t(lang, 'cat_urbanisme'),
    mobilitat: t(lang, 'cat_mobilitat'),
    medi_ambient: t(lang, 'cat_medi_ambient'),
    serveis_publics: t(lang, 'cat_serveis_publics'),
    economia: t(lang, 'cat_economia'),
    drets_i_igualtat: t(lang, 'cat_drets_i_igualtat'),
    persones: t(lang, 'cat_persones'),
    cultura: t(lang, 'cat_cultura'),
    participacio: t(lang, 'cat_participacio'),
  };
}

export function getSubLabels(lang: Lang): Record<string, string> {
  return {
    espai_public: t(lang, 'sub_espai_public'),
    habitatge: t(lang, 'sub_habitatge'),
    patrimoni: t(lang, 'sub_patrimoni'),
    usos_turistics: t(lang, 'sub_usos_turistics'),
    transit: t(lang, 'sub_transit'),
    transport_public: t(lang, 'sub_transport_public'),
    zbe: t(lang, 'sub_zbe'),
    mobilitat_activa: t(lang, 'sub_mobilitat_activa'),
    aparcament: t(lang, 'sub_aparcament'),
    contaminacio: t(lang, 'sub_contaminacio'),
    zones_verdes: t(lang, 'sub_zones_verdes'),
    emergencies_climatiques: t(lang, 'sub_emergencies_climatiques'),
    dana_2024: t(lang, 'sub_dana_2024'),
    benestar_animal: t(lang, 'sub_benestar_animal'),
    educacio: t(lang, 'sub_educacio'),
    salut: t(lang, 'sub_salut'),
    serveis_socials: t(lang, 'sub_serveis_socials'),
    seguretat: t(lang, 'sub_seguretat'),
    esports: t(lang, 'sub_esports'),
    festes: t(lang, 'sub_festes'),
    patrimoni_cultural: t(lang, 'sub_patrimoni_cultural'),
    associacionisme: t(lang, 'sub_associacionisme'),
    pressupostos: t(lang, 'sub_pressupostos'),
    comerc_ocupacio: t(lang, 'sub_comerc_ocupacio'),
    agricultura: t(lang, 'sub_agricultura'),
    diversitat: t(lang, 'sub_diversitat'),
    interculturalitat_i_antiracisme: t(lang, 'sub_interculturalitat_i_antiracisme'),
    igualtat_de_genere: t(lang, 'sub_igualtat_de_genere'),
    drets_humans: t(lang, 'sub_drets_humans'),
    drets_linguistics: t(lang, 'sub_drets_linguistics'),
    joventut: t(lang, 'sub_joventut'),
    gent_major: t(lang, 'sub_gent_major'),
    cultura: t(lang, 'sub_cultura'),
    participacio: t(lang, 'sub_participacio'),
    processos_participatius: t(lang, 'sub_processos_participatius'),
    transparencia: t(lang, 'sub_transparencia'),
    consells_sectorials: t(lang, 'sub_consells_sectorials'),
  };
}

export function getAmbitLabels(lang: Lang): Record<string, string> {
  return {
    barri: t(lang, 'ambit_barri'),
    districte: t(lang, 'ambit_districte'),
    multi_barri: t(lang, 'ambit_multi_barri'),
    multi_districte: t(lang, 'ambit_multi_districte'),
    ciutat: t(lang, 'ambit_ciutat'),
    area_metropolitana: t(lang, 'ambit_area_metropolitana'),
    no_especificat: t(lang, 'ambit_no_especificat'),
  };
}
