#!/usr/bin/env python3
"""
Apply entity merges, floor-cession re-attributions and deletions.

Design: MERGES are defined by ENTITY TEXT PATTERNS (stable, from interventions)
rather than entity IDs (unstable, change every time script 06 runs).
At runtime we resolve text patterns → entity IDs via the variant_map.
"""
import json
from pathlib import Path
from slugify import slugify
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"
INTERVENTIONS_FILE = DATA_DIR / "raw" / "interventions_raw.json"
ENTITIES_FILE = DATA_DIR / "entitats.json"
VARIANT_MAP_FILE = DATA_DIR / "raw" / "entity_variant_map.json"

interventions = json.loads(INTERVENTIONS_FILE.read_text())
entities_list = json.loads(ENTITIES_FILE.read_text())
entities = {e["id"]: e for e in entities_list}
variant_map = json.loads(VARIANT_MAP_FILE.read_text()) if VARIANT_MAP_FILE.exists() else {}

# ─── KNOWN BAD VARIANT MAP ENTRIES (script 06 sometimes misgroups these) ─────
# These texts reliably appear in interventions and must map to the correct entity.
# Applied as a patch BEFORE any further processing.
VARIANT_MAP_FORCED = {
    # Roqueta texts occasionally end up assigned to Fuensanta by Claude
    "associació de veïns de la roqueta": "associacio-veinal-roqueta",
    "associació de veïns la roqueta":    "associacio-veinal-roqueta",
    # Torre texts same issue
    "associació de veïns de la torre":   "av-la-torre",
    "associ de veïns de la torre":       "av-la-torre",
    # Inquilinos: variants without "de la CV" suffix
    "asociación de inquilinos de vivienda pública":                                      "asociacion-inquilinos-vivienda-publica",
    "asociación de vecinos de san isidro / asociación de inquilinos de vivienda pública": "asociacion-inquilinos-vivienda-publica",
    # Natzaret: valencian form maps to same entity as "Nazaret Unido"
    "associació de veïns i veïnes de natzaret": "asociacion-vecinos-nazaret-unido",
    "av nazaret unido": "asociacion-vecinos-nazaret-unido",
    # Stop Accidents: catalan article variant maps to same entity
    "associació stop accidents": "stop-accidents",
    # Cabanyal-Canyamelar: new entity from 2023-10-24
    "associació de veïns i veïnes del cabanyal-canyamelar": "av-cabanyal-canyamelar",
    # ACICOM / Ciutadania i Comunicació
    "associacio ciutadania i comunicacio-acicom": "ciutadania-comunicacio",
    # Del Río registered as AV Abastos but explicitly represents Colectivo Fuera Túnel
    "associació de veïns abastos-finca roja (en representació de col·lectiu fuera túnel)": "colectivo-fuera-tunel",
    # ONGD-CV: valencian spelling variant
    "coordinadora de organizaciones no gubernamentales para el desarrollo de la comunitat valenciana": "coordinadora-ong-desarrollo-valencia",
    # Unió de Consumidors: valencian form
    "unió de consumidors de valència": "union-consumidores-valencia",
    # Mundo Solidario: new entity from 2025-04-30
    "asociación intercultural mundo solidario": "asociacion-intercultural-mundo-solidario",
    # TDAH MAS 16: from 2025-04-11-3
    "asociación tdah mas 16 valència": "asociacion-tdah-mas-16",
    # Patraix cultural association: from 2025-04-11-3
    "associació cultural i de consumidors patraix": "associacio-cultural-consumidors-patraix",
    # AVV Sant Marcel·lí: from 2025-04-11-3
    "avv de sant marcel·lí": "avv-sant-marcelli",
    # Cáritas: from 2025-04-11-3
    "cáritas diocesana": "caritas-diocesana",
    # Cruces de Mayo La Torre: from 2025-04-11-3
    "asociación cultural cruces de mayo la torre": "asociacion-cruces-mayo-la-torre",
    # STA-Intersindical: from 2025-04-11-3
    "sta-intersindical": "sta-intersindical",
    # Cuidem la Raïosa: lowercase variant
    "associació cuidem la raïosa": "cuidem-la-raiosa",
    # Castellar-l'Oliveral Devesa D26 variant
    "av castellar-l'oliveral - devesa d26": "av-castellar-loliveral",
    "av castellar-l'oliveral": "av-castellar-loliveral",
    # Patraix AV (distinct from Coordinadora Feminista — floor cession, not same entity)
    "associació de veïns cultural i de consumidors patraix": "associacio-cultural-consumidors-patraix",
    "asociación de vecinos cultural y de consumidores patraix": "associacio-cultural-consumidors-patraix",
    "associació de veïns cultural i de consumidors patraix / coordinadora feminista de valència": "associacio-cultural-consumidors-patraix",
    # Plataforma Intercultural: AV variant is the same entity
    "associació de veïns plataforma intercultural d'espanya": "asociacion-plataforma-intercultural-espana",
    "asociación de vecinos plataforma intercultural de españa": "asociacion-plataforma-intercultural-espana",
    # SOS Racisme / Unió Africana: same entity, floor cession
    "sos racisme pv / federació unió africana espanya": "sos-racisme-unio-africana",
    "sos racisme pv / federación unión africana españa": "sos-racisme-unio-africana",
    "sos racismo pv / federación unión africana españa": "sos-racisme-unio-africana",
    "federació unió africana espanya / sos racisme país valencià": "sos-racisme-unio-africana",
    "federación unión africana españa / sos racismo país valenciano": "sos-racisme-unio-africana",
    # CEAR (without CEPAIM — they shared time but are separate entities)
    "comissió española de ayuda al refugiado (cear) i fundació cepaim": "cear",
    "comisión española de ayuda al refugiado (cear) i fundación cepaim": "cear",
    "comissió espanyola d'ajuda al refugiat (cear) i fundació cepaim": "cear",
    # STA-Intersindical: all variants map to same
    "sta-intersindical": "sta-intersindical",
    "sta-intersindical valenciana": "sta-intersindical",
    "sta- intersindical valenciana": "sta-intersindical",
    "sindicat de treballadores i treballadors de les administracions i els serveis públics-intersindical": "sta-intersindical",
    "sindicat de treballadores i treballadors de les administracions i els serveis publics-intersindical": "sta-intersindical",
    "sindicat de treballadores i treballadors de les administracions i els serveis públics-intersindical valenciana": "sta-intersindical",
    "sindicato de trabajadoras y trabajadores de las administraciones y los servicios públicos-intersindical": "sta-intersindical",
    # Penya-Roja: all variants (plataforma vecinal + AV) are the same entity
    "plataforma de vecinos de penya-roja": "plataforma-vecinal-penyaroja",
    "plataforma vecinal del barrio de peña-roja": "plataforma-vecinal-penyaroja",
    "plataforma veïnal del barri de penya-roja": "plataforma-vecinal-penyaroja",
    "associació de veïns del barri de penya-roja": "plataforma-vecinal-penyaroja",
    "asociación de vecinos del barrio de penya-roja": "plataforma-vecinal-penyaroja",
    "asociación de vecinos de penya-roja": "plataforma-vecinal-penyaroja",
    "associació de veïns de penya-roja / plataforma vecinal barrio de penya-roja": "plataforma-vecinal-penyaroja",
    # Benimaclet AV: old name → inclusive name
    "associació de veïns de benimaclet": "associacio-veinal-benimaclet",
    "asociación de vecinos de benimaclet": "associacio-veinal-benimaclet",
    # Per l'Horta
    "associació per l'horta": "per-l-horta",
    "asociación por la huerta": "per-l-horta",
    "associació per l'horta / plataforma ciutadana horta és futur-no a la zal": "per-l-horta",
    # València Acull
    "associació valència acull": "valencia-acull",
    "asociación valencia acull": "valencia-acull",
    # Marítim-Aiora: all variants same AV
    "associació de veïns i veïns de marítim-aiora": "av-maritim-ayora",
    "asociación de vecinos y vecinas de marítim-aiora": "av-maritim-ayora",
    "associació de veïns i veïnes de marítim-aiora": "av-maritim-ayora",
    "associació de veïns de marítim-aiora": "av-maritim-ayora",
    "asociación de vecinos de marítim-ayora": "av-maritim-ayora",
    "vecinos del barrio de ayora / av de marítim-ayora": "av-maritim-ayora",
    # Nou Moles
    "associació de veïns de nou moles": "associacio-veins-nou-moles",
    "asociación de vecinos de nou moles": "associacio-veins-nou-moles",
    "associació de veïns i veïnes de nou moles / asociación de vecinos de tres forques y nou moles": "associacio-veins-nou-moles",
    "asociación de vecinos y vecinas de nou moles / asociación de vecinos de tres forques y nou moles": "associacio-veins-nou-moles",
    # FAVV — Federació d'Associacions de Veïns de València: all name variants → favv
    "federación y movimiento vecinal": "favv",
    "federació i moviment veïnal": "favv",
    "federació d'associacions de veïns": "favv",
    "federación de asociaciones de vecinos": "favv",
    "federación de asociaciones de vecinos de valència": "favv",
    "federación de asociaciones de vecinos de valencia": "favv",
    "federació d'associacions de veïns de valència": "favv",
    "federació d'associacions de veïns i veïnes de valència": "favv",
    "federación de asociaciones vecinales de valencia": "favv",
    "favv (federación de asociaciones vecinales de valència)": "favv",
    # Taxi: all variants same entity
    "federació sindical del taxi de valència": "federacio-taxi",
    "federación sindical del taxi de valencia": "federacio-taxi",
    "federación sindical del taxi de valència": "federacio-taxi",
}
for k, v in VARIANT_MAP_FORCED.items():
    if variant_map.get(k) != v:
        print(f"  VM patch: {repr(k)} {variant_map.get(k)} -> {v}")
        variant_map[k] = v


def text_to_eid(entitat_text: str) -> str:
    """Resolve entity text → entity ID via variant map, fallback to slug."""
    if not entitat_text:
        return "desconegut"
    return variant_map.get(entitat_text.lower().strip(), slugify(entitat_text))


# ─── 1. MERGES — defined by representative entity texts (stable) ──────────────
#
# `match_texts`: list of entity name texts from interventions that identify
#   which entities belong to this merge group. We resolve these via variant_map
#   to get the current entity IDs (which may change between script 06 runs).
# `exclude_texts`: entity IDs resolved from these texts are EXCLUDED from the merge
#   (e.g., Colectivo Fuera Túnel should not be merged with AV Abastos).
#
MERGES = [
    dict(canonical_id="av-abastos-finca-roja",
         nom_cas="Asociación Vecinal Abastos-Finca Roja",
         nom_val="Associació Veïnal Abastos-Finca Roja",
         tipus="av",
         match_texts=[
             "AV Abastos-Finca Roja",
             "Asociación de Vecinos Abastos-Finca Roja",
             "Asociación de Vecinos de Abastos – Finca Roja",
             "Asociación de Vecinos Abastos-Finca Roja / Colectivo Fuera Túnel",
             "Associació de Veïns Abastos-Finca Roja / Colectivo Fuera Túnel",
         ],
         exclude_texts=["Colectivo Fuera Túnel"]),

    dict(canonical_id="av-la-torre",
         nom_cas="Asociación de Vecinas y Vecinos de La Torre",
         nom_val="Associació de Veïnes i Veïns de La Torre",
         tipus="av",
         match_texts=[
             "AV La Torre", "AVV La Torre",
             "Asociación de Vecinos La Torre",
             "Associació de Veïns de la Torre",
             "Associació de Veïnes i Veïns de la Torre-Faitanar",
             "Associció de Veïnes i Veïns de la Torre-Faitanar",
             "Associació de Vecinos Sociópolis-La Torre-Faitanar",
             "Asociación de Vecinos Sociópolis-La Torre-Faitanar",
         ]),

    dict(canonical_id="av-la-petxina",
         nom_cas="Asociación Vecinal de La Petxina",
         nom_val="Associació Veïnal de La Petxina",
         tipus="av",
         match_texts=[
             "AV La Petxina", "AV la Petxina",
             "AV Arrancapins-la Petxina",
             "Associació Veïnal Arrancapins-La Petxina",
             "Associació Veïnal de la Petxina",
             "Asociación Vecinal de la Petxina",
             "Associació de Veïns Arrancapins-La Petxina",
             "Asociación de Vecinos Arrancapins-La Petxina",
             "Associació de Veïns de la Petxina / Plataforma del Corredor Verd",
             "Associció de Veïns de la Petxina / Plataforma del Corredor Verd",
             "Asociación Vecinal Arrancapins-La Petxina",
         ]),

    dict(canonical_id="associacio-veinal-roqueta",
         nom_cas="Asociación Vecinal La Roqueta",
         nom_val="Associació Veïnal La Roqueta",
         tipus="av",
         match_texts=[
             "Associació Veïnal la Roqueta",
             "Associació Veïnal La Roqueta",
             "Asociación Vecinal La Roqueta",
             "Associació de Veïns de la Roqueta",
             "Associació de Veïns La Roqueta",
             "Asociación de Vecinos La Roqueta",
             "Associción Veïnal la Roqueta",
             "Associación Veïnal la Roqueta",
             "Associció Veïnal la Roqueta",
             "Associció de Veïns La Roqueta",
             "Associció de Veïns de la Roqueta",
             "Associció de Veïns la Roqueta",
             "AV la Roqueta",
         ]),

    dict(canonical_id="cuidem-la-raiosa",
         nom_cas="Asociación Vecinal y Cultural Cuidem La Raïosa",
         nom_val="Associació Veïnal i Cultural Cuidem La Raïosa",
         tipus="av",
         match_texts=[
             "Asociación Cuidem La Raïosa",
             "Asociación Cuidem la Raïosa",
             "Associació Cuidem la Raiosa",
             "Associció Cuidem la Raiosa",
         ]),

    dict(canonical_id="avacu",
         nom_cas="Asociación Valenciana de Consumidores y Usuarios (AVACU)",
         nom_val="Associació Valenciana de Consumidors i Usuaris (AVACU)",
         tipus="altres",
         match_texts=[
             "AVACU",
             "Asociación Valenciana de Consumidores y Usuarios-AVACU",
         ]),

    dict(canonical_id="associacio-veins-forn-alcedo",
         nom_cas="Asociación de Vecinos del Forn d'Alcedo",
         nom_val="Associació de Veïns del Forn d'Alcedo",
         tipus="av",
         match_texts=[
             "AV Forn d'Alcedo",
             "Associació de Veïns del Forn d'Alcedo",
             "Associ de Veïns del Forn d'Alcedo",
         ]),

    dict(canonical_id="asociacion-vecinos-fuensanta",
         nom_cas="Asociación de Vecinos de la Fuensanta",
         nom_val="Associació de Veïns de la Fuensanta",
         tipus="av",
         match_texts=[
             "AVV Fuensanta",
             "Asociación de Vecinos de la Fuensanta",
         ]),

    dict(canonical_id="av-sant-marcelli",
         nom_cas="Asociación Vecinal del Barrio de Sant Marcel·lí",
         nom_val="Associació Veïnal del Barri de Sant Marcel·lí",
         tipus="av",
         match_texts=[
             "Associació de Veïns del Barri de Sant Marcel·lí",
             "Associació de Veïns i Veïnes del barri Sant Marcel·lí",
             "Associ de Veïns del Barri de Sant Marcel·lí",
             "Asociación Veïnal del barrio de Sant Marcel·lí",
             "Associació de Veïns de Sant Marcel·lí",
         ]),

    dict(canonical_id="asociacion-inquilinos-vivienda-publica",
         nom_cas="Asociación de Inquilinos de Vivienda Pública de la Comunitat Valenciana",
         nom_val="Associació d'Inquilins d'Habitatge Públic de la Comunitat Valenciana",
         tipus="plataforma",
         match_texts=[
             "Asociación de Inquilinos de Vivienda Pública de la CV",
             "Asociación de Inquilinos de Vivienda Pública de la Comunitat Valenciana",
             "Associació de Llogaters de Vivenda Pública de la CV / Asociación de Inquilinos de Vivienda Pública de la CV",
             "Associció de Llogaters de Vivenda Pública de la CV / Asociación de Inquilinos de Vivienda Pública de la CV",
             "Asociación de Inquilinos de Vivienda Pública",
             "Asociación de Vecinos de San Isidro / Asociación de Inquilinos de Vivienda Pública",
         ]),

    dict(canonical_id="plataforma-orriols-en-lucha",
         nom_cas="Plataforma Orriols en Lucha",
         nom_val="Plataforma Orriols en Lluita",
         tipus="plataforma",
         match_texts=[
             "Asociación Plataforma Orriols en Lucha",
             "Plataforma Orriols en Lucha",
         ]),

    dict(canonical_id="asociacion-plataforma-intercultural-espana",
         nom_cas="Plataforma Intercultural de España",
         nom_val="Plataforma Intercultural d'Espanya",
         tipus="plataforma",
         match_texts=[
             "Asociación Plataforma Intercultural de España",
             "Plataforma Intercultural de España",
             "Associació de Veïns Plataforma Intercultural d'Espanya",
             "Asociación de Vecinos Plataforma Intercultural de España",
         ]),

    dict(canonical_id="club-esportiu-samarucs-valencia",
         nom_cas="Club Esportiu LGTB+ Samarucs Valencia",
         nom_val="Club Esportiu LGTB+ Samarucs València",
         tipus="esportiu",
         match_texts=[
             "Samarucs",
             "Club esportiu LGTB+ Samarucs València",
         ]),

    dict(canonical_id="plataforma-valencia-aire",
         nom_cas="Plataforma Valencia por el Aire",
         nom_val="Plataforma València per l'Aire",
         tipus="plataforma",
         match_texts=[
             "Asociación Mesura",
             "Asociación Mesura / CAVECOVA / València per l'aire",
             "Associació Mesura / Plataforma València per l'Aire",
             "Associ Mesura / Plataforma València per l'Aire",
             "Associció Mesura / Plataforma València per l'Aire",
             "Plataforma València per l'Aire, Mesura",
         ]),

    dict(canonical_id="av-del-palmar",
         nom_cas="Asociación Vecinal El Palmar",
         nom_val="Associació Veïnal El Palmar",
         tipus="av",
         match_texts=["AV del Palmar"]),

    dict(canonical_id="avv-campanar",
         nom_cas="Asociación de Vecinos de Campanar",
         nom_val="Associació de Veïns de Campanar",
         tipus="av",
         match_texts=[
             "AVV Campanar",
             "Asociación de Vecinos Campanar",
             "Associació de Veïns Campanar",
             "Asociación de Vecinos de Campanar",
             "Associació de Veïns de Campanar",
         ]),

    dict(canonical_id="asociacion-mujeres-separadas-divorciadas",
         nom_cas="Asociación de Mujeres Separadas y Divorciadas del País Valenciano",
         nom_val="Associació de Dones Separades i Divorciades del País Valencià",
         tipus="altres",
         match_texts=[
             "Asociación de Mujeres Separadas y Divorciadas del País Valenciano",
             "Asociación de Mujeres Separadas y Divorciadas del País Valencià",
             "Associació de Dones Separades i Divorciades del País Valencià",
             "Associació de Mujeres Separadas y Divorciadas del País Valencià",
         ]),

    dict(canonical_id="asociacion-intercultural-candombe",
         nom_cas="Asociación Intercultural Candombe",
         nom_val="Associació Intercultural Candombe",
         tipus="ong",
         match_texts=[
             "Asociación Intercultural Candombe",
             "Associació Intercultural Candombe",
         ]),

    dict(canonical_id="orriols-conviu",
         nom_cas="Orriols Conviu",
         nom_val="Orriols Conviu",
         tipus="plataforma",
         match_texts=["Orriols Conviu"]),

    dict(canonical_id="consell-joventut-valencia",
         nom_cas="Consell de la Joventut de València",
         nom_val="Consell de la Joventut de València",
         tipus="altres",
         match_texts=[
             "Consell de la Joventut de València",
             "Consejo de la Juventud de Valencia",
         ]),

    dict(canonical_id="fampa-valencia",
         nom_cas="FAMPA València",
         nom_val="FAMPA València",
         tipus="educacio",
         match_texts=["FAMPA València", "FAMPA Valencia"]),

    dict(canonical_id="asociacion-mujeres-voces-resistencias",
         nom_cas="Asociación Mujeres, Voces y Resistencia",
         nom_val="Associació Dones, Veus i Resistència",
         tipus="ong",
         match_texts=[
             "Asociación Mujeres, Voces y Resistencia",
             "Asociación Mujeres, Voces y Resistencias",
         ]),

    # --- Merges added from entity review ---

    dict(canonical_id="asociacion-tdah-mas-16",
         nom_cas="Asociación TDAH MAS 16 València",
         nom_val="Associació TDAH MAS 16 València",
         tipus="ong",
         match_texts=[
             "Asociación TDAH MAS 16 València",
             "Asociación TDAH MAS 16 Valencia",
             "Associació TDAH MAS 16 València",
         ]),

    dict(canonical_id="av-sant-marcelli",
         nom_cas="Asociación Vecinal del Barrio de Sant Marcel·lí",
         nom_val="Associació Veïnal del Barri de Sant Marcel·lí",
         tipus="av",
         match_texts=[
             "Associació de Veïns del Barri de Sant Marcel·lí",
             "Associació de Veïns i Veïnes del barri Sant Marcel·lí",
             "Associ de Veïns del Barri de Sant Marcel·lí",
             "Asociación Veïnal del barrio de Sant Marcel·lí",
             "Associació de Veïns de Sant Marcel·lí",
             "AVV de Sant Marcel·lí",
             "Asociación de Vecinos y Vecinas de Sant Marcel·lí",
             "Associació de Veïns i Veïnes de Sant Marcel·lí",
         ]),

    dict(canonical_id="plataforma-vecinal-penyaroja",
         nom_cas="Plataforma Vecinal Barrio Penya-roja",
         nom_val="Plataforma Veïnal Barri Penya-roja",
         tipus="plataforma",
         match_texts=[
             "Plataforma Vecinal Barrio Penya-roja",
             "Plataforma Veïnal Barri Penya-roja",
             "Plataforma Vecinal Barrio Peña-roja",
             "Plataforma Veïnal Barri de Penya-roja",
             "Asociación de Vecinos de Penya-roja",
             "Associació de Veïns de Penya-roja",
             "Asociación de Vecinos de Peña-roja",
             "Asociación de Vecinos Penya-roja",
         ]),

    dict(canonical_id="cruces-mayo-la-torre",
         nom_cas="Asociación Cultural Cruces de Mayo La Torre",
         nom_val="Associació Cultural Creus de Maig La Torre",
         tipus="cultural",
         match_texts=[
             "Asociación Cultural Cruces de Mayo La Torre",
             "Associació Cultural Cruces de Mayo La Torre",
             "Associació Cultural Creus de Maig La Torre",
             "Asociación Cultural Cruces de Maig La Torre",
         ]),

    dict(canonical_id="av-devesa-saler",
         nom_cas="Asociación de Vecinos Devesa-El Saler",
         nom_val="Associació de Veïns Devesa-El Saler",
         tipus="av",
         match_texts=[
             "Asociación de Vecinos Devesa-El Saler",
             "Associació de Veïns Devesa-El Saler",
             "Asociación de Vecinos Devesa - El Saler",
             "Asociación de Vecinos Mont de la Devesa del Saler",
             "Associació de Veïns Mont de la Devesa del Saler",
             "Asociación de Vecinos Dehesa D.26",
             "Associació de Veïns Dehesa D.26",
         ]),

    dict(canonical_id="sos-racisme-unio-africana",
         nom_cas="SOS Racismo PV / Federación Unión Africana España",
         nom_val="SOS Racisme PV / Federació Unió Africana Espanya",
         tipus="ong",
         match_texts=[
             "SOS Racisme PV / Federació Unió Africana Espanya",
             "SOS Racisme PV / Federación Unión Africana España",
             "Federació Unió Africana Espanya / SOS Racisme País Valencià",
             "Federación Unión Africana España / SOS Racismo País Valenciano",
             "SOS Racismo PV / Federación Unión Africana España",
         ]),

    dict(canonical_id="cear",
         nom_cas="Comisión Española de Ayuda al Refugiado (CEAR)",
         nom_val="Comissió Espanyola d'Ajuda al Refugiat (CEAR)",
         tipus="ong",
         match_texts=[
             "Comisión Española de Ayuda al Refugiado (CEAR)",
             "Comissió Espanyola d'Ajuda al Refugiat (CEAR)",
             "Comissió Española de Ayuda al Refugiado (CEAR) i Fundació CEPAIM",
             "Comisión Española de Ayuda al Refugiado (CEAR) i Fundación CEPAIM",
         ]),

    dict(canonical_id="sta-intersindical",
         nom_cas="STA-Intersindical Valenciana",
         nom_val="STA-Intersindical Valenciana",
         tipus="sindical",
         match_texts=[
             "STA-Intersindical",
             "STA-Intersindical Valenciana",
             "STA- Intersindical Valenciana",
             "Sindicat de Treballadores i Treballadors de les Administracions i els Serveis Públics-Intersindical",
             "Sindicato de Trabajadoras y Trabajadores de las Administraciones y los Servicios Públicos-Intersindical",
         ]),

    dict(canonical_id="col-lectiu-lambda",
         nom_cas="Colectivo Lambda",
         nom_val="Col·lectiu Lambda",
         tipus="ong",
         match_texts=[
             "Colectivo Lambda",
             "Col·lectiu Lambda",
         ]),

    dict(canonical_id="jovesolides",
         nom_cas="Jóvenes hacia la Solidaridad y el Desarrollo",
         nom_val="Joves cap a la Solidaritat i el Desenvolupament",
         tipus="ong",
         match_texts=[
             "Jóvenes hacia la Solidaridad y el Desarrollo",
             "Joves cap a la Solidaritat i el Desenvolupament",
             "Jovesolides",
         ]),

    dict(canonical_id="asociacion-comerciantes-centro-historico-valencia",
         nom_cas="Asociación de Comerciantes del Centro Histórico de València",
         nom_val="Associació de Comerciants del Centre Històric de València",
         tipus="empresa",
         match_texts=[
             "Asociación de Comerciantes del Centro Histórico de València",
             "Associació de Comerciants del Centre Històric de València",
         ]),

    dict(canonical_id="favv",
         nom_cas="Federación de Asociaciones Vecinales de Valencia (FAVV)",
         nom_val="Federació d'Associacions de Veïns de València (FAVV)",
         tipus="av",
         match_texts=[
             "FAVV (Federación de Asociaciones Vecinales de València)",
             "Federación de Asociaciones Vecinales de Valencia",
             "Federació d'Associacions de Veïns de València",
             "Federació d'Associacions de Veïns i Veïnes de València",
             "Federación de Asociaciones de Vecinos",
             "Federación de Asociaciones de Vecinos de Valencia",
             "Federación de Asociaciones de Vecinos de València",
             "Federación y movimiento vecinal",
             "Federació i moviment veïnal",
             "Federació d'Associacions de Veïns",
         ]),
]

# ─── 2. FLOOR CESSION RE-ATTRIBUTIONS ────────────────────────────────────────
REASSIGN = {
    "2024-05-28-003": ("Colectivo Fuera Túnel", "colectivo-fuera-tunel"),
    "2024-01-29-004": ("Asociación de Inquilinos de Vivienda Pública de la CV", "asociacion-inquilinos-vivienda-publica"),
    "2025-11-18-006": ("Asociación Ciudadana para la Defensa de la Sanidad Pública del País Valencià (ACDESA)", "acdesa"),
    "2022-12-22-002": ("Asociación de Vecinos del barrio de San Antonio", "av-sant-antoni-saidia"),
    "2021-04-29-002": ("Plataforma Veïnal del Barri de Penya-roja", "plataforma-vecinal-penyaroja"),
    "2025-05-27-005": ("Asociación Chrysallis Comunitat Valenciana", "chrysallis-comunitat-valenciana"),
}

# ─── 3. DELETE ───────────────────────────────────────────────────────────────
DELETE_IV_IDS = {
    # Presidenta thanks/session management (not citizen interventions)
    "2024-06-28-002",   # Presidenta "Gràcies, senyor Aguado"
    "2024-09-16-1-026", # "No especificado" generic thanks (Presidenta)
    "2024-09-25-005",   # "No especificat" "Gracias por su intervención" (Presidenta)
    "2025-04-11-3-009", # Sra. Presidenta session management
    "2025-04-11-3-011", # "No especificado" minuto de silencio request
    "2025-04-11-3-012", # Sancanuto "53 minuts de silenci" (protest gesture, real speech replaced by manual)
    "2025-07-22-101",   # Tabib (merged into 100 as joint intervention with El Hadri)
    # Concejales/políticos (not citizens)
    "2024-06-28-007",   # Sra. Llopis (concejala PSOE)
    # Truncated/interrupted starts (real speech in next intervention)
    "2024-06-28-003",   # García "Buenos días a todas..." (interrupted, full speech in 004)
    "2024-09-16-1-011", # Sr. Navarro "Voy a ser muy breve" (preamble to 012)
    "2024-09-16-1-018", # Beatriu Cardona "Agradezco..." (fragment, real speech in 020)
    "2024-09-25-001",   # Cabel truncated intro (full speech in 002)
    "2024-09-25-003",   # Ascione "Sí. Ascione, sí." (name confirmation, real speech in 004)
    "2024-09-16-1-024", # Ramón "Soy Ramón y no Ramos" (name correction, full speech in 025)
    # Concejales/políticos pre-2015 (art. 12 boilerplate captures political portavoces, not citizens)
    "2013-01-25-003",   # Sr. Estrela (Grupo Socialista) — político
    "2013-01-25-004",   # Sr. Novo (concejal) — político
    # False positive: pleno debating regulation of citizen interventions (no actual citizen spoke)
    "2018-01-25-001",   # "intervenciones ciudadanas" phrase matched in regulation debate text
}
DELETE_ENTITY_IDS = {"ajuntament-valencia", "compromis", "grup-vox"}

# ─── 4. INTERVENTION FIELD PATCHES ──────────────────────────────────────────
# Fix wrong names and missing entities from bad Claude parsing.
# Format: iv_id → dict of fields to overwrite
IV_PATCHES = {
    "2024-06-28-004": {
        "intervinient": "Jorge García Pascual",
    },
    "2024-09-16-1-006": {
        "intervinient": "Ángeles Pedraza Muna",  # same person as 005
    },
    "2024-09-16-1-007": {
        "intervinient": "Ángeles Pedraza Muna",
        "entitat": "Asociación València Acull",
    },
    "2024-09-25-002": {
        "intervinient": "María Jesús Cabel Sánchez",
    },
    "2024-09-25-004": {
        "intervinient": "Stefano Carlo Ascione",
        "entitat": "Asociación Cuidem La Raïosa",
    },
    "2025-04-30-003": {
        "entitat": "Asociación Intercultural Mundo Solidario",
    },
    "2025-01-28-004": {
        "entitat": "San Juan de Dios-Servicios Sociales",
    },
    "2025-02-25-003": {
        "intervinient": "Clodoaldo Roldán, Josep Benlloch, Lucía Senabre",
    },
    "2025-07-22-002": {
        "intervinient": "Miguel Carlos Oliver Trilles, Jose Domingo Estrela Leiva",
    },
    "2025-02-25-004": {
        "intervinient": "José Casermeiro Castro, Bernardo Marcos Pastor",
    },
    "2024-09-16-1-012": {
        "intervinient": "Victor Navarro",
    },
    "2024-09-25-006": {
        "intervinient": "Beatriu Cardona Prats i Elida Puig Cebolla",
    },
    "2025-04-11-3-001": {
        "intervinient": "Ana Juana Broncano López",
        "entitat": "Asociación TDAH MAS 16 València",
        "tipus_entitat": "av",
    },
}

# ─── 5. MANUAL INTERVENTIONS — missed by parser, added here ──────────────────
# These interventions exist in the raw text but script 05 failed to detect them
# (e.g., Presidenta comment between speakers broke the block detection).
MANUAL_INTERVENTIONS = [
    {
        "id": "2025-04-11-2-003",
        "pleno_id": "2025-04-11-2",
        "ordre": 3,
        "intervinient": "Rosario González Rodríguez",
        "entitat": "AV Abastos-Finca Roja",
        "tipus_entitat": "av",
        "barri_o_zona": "Abastos",
        "punts_ordre_dia": "Soterramiento de las vías de Serrería",
        "idioma_original": "castellano",
        "text_original": "Voy a ser breve porque creo que Miguel Sánchez ha hecho una exposición impecable de todo lo que está sucediendo en esta ciudad. Entonces, lo de Serrería por supuesto que se tiene que solucionar y de la mejor manera para los vecinos, no porque políticamente interese hacerlo en unas fechas o en otras fechas. Y me da lo mismo que sea el Gobierno central el que ponga los inconvenientes o los ponga el gobierno de la ciudad. Entonces, yo solamente pido o nuestra asociación lo único que reclama es una ciudad mucho más social, mucho más preocupada por el medio ambiente, mucho más preocupada por los vecinos. Desde luego, nosotros representamos al túnel de la avenida Pérez Galdós, porque eso es insufrible y los vecinos están hartos. Ustedes prometieron que lo iban a cerrar y creo que además, incluso había presupuestos de los fondos europeos para utilizarlos en ese trabajo. Y entonces, vamos, mi intervención es dar un poco de voz a esos vecinos. Al margen de solidarizarme con los de Serrería que llevan todavía mucho más años reclamándole. Nada más. Muchas gracias.",
        "temes": ["urbanisme", "infraestructures", "barris"],
        "text_cas": "",
        "text_val": "Seré breu perquè crec que Miguel Sánchez ha fet una exposició impecable de tot el que està passant en esta ciutat. Aleshores, el de Serreria per descomptat que s'ha de solucionar i de la millor manera per als veïns, no perquè políticament interesse fer-ho en unes dates o en unes altres. I m'és igual que siga el Govern central el que pose els inconvenients o els pose el govern de la ciutat. Aleshores, jo sols demane o la nostra associació l'únic que reclama és una ciutat molt més social, molt més preocupada pel medi ambient, molt més preocupada pels veïns. Per descomptat, nosaltres representem al túnel de l'avinguda Pérez Galdós, perquè això és insuportable i els veïns estan farts. Vostés van prometre que l'anaven a tancar i crec que a més, fins i tot hi havia pressupostos dels fons europeus per a utilitzar-los en eixe treball. I aleshores, vaja, la meua intervenció és donar un poc de veu a eixos veïns. Al marge de solidaritzar-me amb els de Serreria que porten encara molts més anys reclamant-ho. Res més. Moltes gràcies.",
        "resum_cas": "Reclama una ciudad más social y preocupada por el medio ambiente y los vecinos, apoyando la eliminación del túnel de Pérez Galdós y solidarizándose con los vecinos de Serrería.",
        "resum_val": "Reclama una ciutat més social i preocupada pel medi ambient i els veïns, recolzant l'eliminació del túnel de Pérez Galdós i solidaritzant-se amb els veïns de Serreria.",
    },
    {
        "id": "2025-04-11-2-004",
        "pleno_id": "2025-04-11-2",
        "ordre": 4,
        "intervinient": "Cristóbal Aguado Sanchis",
        "entitat": "AV la Petxina",
        "tipus_entitat": "av",
        "barri_o_zona": "La Petxina",
        "punts_ordre_dia": "Soterramiento de las vías de Serrería",
        "idioma_original": "valenciano",
        "text_original": "Bon dia, senyora alcaldessa. Vull felicitar-la per defensar els interessos de València amb el soterrament de les vies en Serreria. Volem confiar en la intenció del Ministeri per a realitzar-ho, encara que els terminis no semblen definits. Esperem que arriben a un consens. Segons fonts ministerials, la tramitació administrativa està pendent per la falta de documentació de l'Ajuntament, qüestió que vosté nega. Les dues administracions han de resoldre si els informes són suficients i esmenar els possibles requeriments. Entenem que és important la coordinació amb altres infraestructures ferroviàries com el futur túnel passant que connectarà l'Estació del Nord amb el Corredor Mediterrani. El Ministeri ha d'explicar la prioritat i la coordinació dels projectes per a minimitzar les afeccions al servici durant les obres. Es desconeixen raons pressupostàries fins que es redacte el projecte, estimat de 260 milions d'euros. El ministre sembla disposat a acordar amb la Generalitat i l'Ajuntament, però haurà d'aclarir la forma de finançament abans d'escometre amb un cronograma. El soterrament en Serreria és una demanda històrica i necessària per a l'eliminació de la barrera urbana. Les vies dividixen en barris com Penya-roja i Natzaret, i el soterrament ho reunificaria. Millorar la mobilitat, eliminar passos a nivells i crear connexions transversals facilitaria el trànsit rodat, dels vianants i ciclistes. Regeneració urbana. El soterrament alliberaria sòl per a nous espais verds i equipaments. Reducció de l'impacte acústic i visual. Eliminaria el soroll i l'impacte visual de trens i vies, millorant la qualitat de vida. I seguretat, es suprimirien els riscos d'accidents, augmentant la seguretat per a conductors i vianants. Ens alegrem que l'Ajuntament aposte per estos principis de desenvolupament urbà sostenible planificant una ciutat verda i ecològica. El que no entenem perquè ens sembla contradictori és que el major projecte urbanístic que escometrà en esta legislatura no s'apliquen els mateixos criteris. Parlem de la supressió del túnel de Pérez Galdós, una altra demanda històrica i necessària per justament les mateixes raons. Atenció. Eliminació de la barrera urbana. El túnel és una infraestructura obsoleta que dividix els barris i dificulta la seua connexió generant una barrera física i social. Millorar la mobilitat. La creació de noves connexions transversals facilitaria el trànsit rodat de vianants i ciclistes. Va ser construït com una ronda per agilitzar el trànsit, però amb el creixement de la ciutat s'ha convertit en un eix viari intern, per la qual cosa la seua pacificació és fonamental. Regeneració urbana. L'eliminació obriria la possibilitat d'una millor reurbanització de l'avinguda creant espais més amables, amb millors zones verdes i major integració. Reducció de l'impacte acústic i visual. El trànsit pel túnel genera contaminació acústica de l'aire que empitjora la qualitat de vida de les persones a l'avinguda. I seguretat, es considera un punt negre on han ocorregut accidents de trànsit i mantindre'l no elimina este risc. Alcaldessa, el soterrament de Serreria depén del Ministeri, però l'eliminació del túnel de Pérez Galdós és la seua responsabilitat directa. Siga conseqüent amb els principis que li exigix al Govern central i aplique'ls també en aquests projecte, Suprimisca el túnel, per favor. El projecte guanyador incloïa voreres amples, tres fileres d'arbres, carril bici, carril bus i l'eliminació del túnel. Es van concedir 9,9 milions d'euros de fons Next Generation. Amb el canvi de govern s'han buscat excuses per a no eliminar-lo. S'ha utilitzat un estudi de la Universitat Politècnica de València per a justificar la seua conservació, al·legant que les parets no podrien suportar el pes d'una llosa de cobriment. Però el projecte original no contemplava esta solució, sinó la demolició total del túnel, la protecció del col·lector existent amb una llosa i el cobriment amb terra i grava. A més, el Govern central li demana justificar el manteniment dels objectius i de les ajudes europees. Però les respostes del consistori són insuficients i inexactes. Afirmen que existix un carril bus exclusiu per al transport públic, quan en realitat este serà compartit amb els vehicles que vullguen accedir als barris al llarg dels 720 metres de longitud del túnel, és a dir, quasi la meitat de l'avinguda. Asseguren que mantindrà la tercera fila d'arbres en el centre de l'avinguda, una cosa impossible en la zona del túnel. Justifiquen la millora de la connectivitat transversal entre els barris només amb les voreres més amples, ja que així costa menys temps creuar l'avinguda. És ridícul. L'Ajuntament no descarta eliminar el túnel després de l'obra, però un any després no ha fet res. El Ministeri ha advertit que mantindre'l incomplix els objectius de les ajudes, es perd el carril bus exclusiu, desapareix la gran part de la fila central d'arbres i es manté la barrera entre barris. Això pot suposar la devolució de les ajudes i una greu multa. Alcaldessa, li exigim coherència i acció immediata per eliminar-lo abans que finalitze l'obra de l'avinguda. Sol·licitem la continuïtat del projecte actual sense demores, però al mateix temps la licitació d'un nou projecte per a la supressió del túnel. I si vol, podem fer un ple per a parlar més específicament d'aquest tema. Esperem que seguisquen el mateix criteri urbanístic i que la ciutat puga vore com les obres de supressió de les barreres urbanes, tant de Serreria com de Pérez Galdós, com altres, puguen ser una realitat el més prompte possible. Moltes gràcies.",
        "temes": ["urbanisme", "infraestructures", "mobilitat", "medi_ambient", "barris"],
        "text_cas": "Buenos días, señora alcaldesa. Quiero felicitarla por defender los intereses de València con el soterramiento de las vías en Serrería. Queremos confiar en la intención del Ministerio para realizarlo, aunque los plazos no parecen definidos. Esperamos que lleguen a un consenso. Según fuentes ministeriales, la tramitación administrativa está pendiente por la falta de documentación del Ayuntamiento, cuestión que usted niega. Las dos administraciones deben resolver si los informes son suficientes y subsanar los posibles requerimientos. Entendemos que es importante la coordinación con otras infraestructuras ferroviarias como el futuro túnel pasante que conectará la Estación del Norte con el Corredor Mediterráneo. El Ministerio debe explicar la prioridad y la coordinación de los proyectos para minimizar las afecciones al servicio durante las obras. Se desconocen razones presupuestarias hasta que se redacte el proyecto, estimado de 260 millones de euros. El ministro parece dispuesto a acordar con la Generalitat y el Ayuntamiento, pero deberá aclarar la forma de financiación antes de acometer con un cronograma. El soterramiento en Serrería es una demanda histórica y necesaria para la eliminación de la barrera urbana. Las vías dividen barrios como Penya-roja y Nazaret, y el soterramiento los reunificaría. Mejorar la movilidad, eliminar pasos a nivel y crear conexiones transversales facilitaría el tránsito rodado, de peatones y ciclistas. Regeneración urbana. El soterramiento liberaría suelo para nuevos espacios verdes y equipamientos. Reducción del impacto acústico y visual. Eliminaría el ruido y el impacto visual de trenes y vías, mejorando la calidad de vida. Y seguridad, se suprimirían los riesgos de accidentes, aumentando la seguridad para conductores y peatones. Nos alegramos de que el Ayuntamiento apueste por estos principios de desarrollo urbano sostenible planificando una ciudad verde y ecológica. Lo que no entendemos porque nos parece contradictorio es que al mayor proyecto urbanístico que acometerá en esta legislatura no se apliquen los mismos criterios. Hablamos de la supresión del túnel de Pérez Galdós, otra demanda histórica y necesaria por justamente las mismas razones. Atención. Eliminación de la barrera urbana. El túnel es una infraestructura obsoleta que divide los barrios y dificulta su conexión generando una barrera física y social. Mejorar la movilidad. La creación de nuevas conexiones transversales facilitaría el tránsito rodado de peatones y ciclistas. Fue construido como una ronda para agilizar el tránsito, pero con el crecimiento de la ciudad se ha convertido en un eje viario interno, por lo que su pacificación es fundamental. Regeneración urbana. La eliminación abriría la posibilidad de una mejor reurbanización de la avenida creando espacios más amables, con mejores zonas verdes y mayor integración. Reducción del impacto acústico y visual. El tránsito por el túnel genera contaminación acústica del aire que empeora la calidad de vida de las personas en la avenida. Y seguridad, se considera un punto negro donde han ocurrido accidentes de tráfico y mantenerlo no elimina este riesgo. Alcaldesa, el soterramiento de Serrería depende del Ministerio, pero la eliminación del túnel de Pérez Galdós es su responsabilidad directa. Sea consecuente con los principios que le exige al Gobierno central y aplíquelos también en este proyecto. Suprima el túnel, por favor. El proyecto ganador incluía aceras amplias, tres hileras de árboles, carril bici, carril bus y la eliminación del túnel. Se concedieron 9,9 millones de euros de fondos Next Generation. Con el cambio de gobierno se han buscado excusas para no eliminarlo. Se ha utilizado un estudio de la Universidad Politécnica de València para justificar su conservación, alegando que las paredes no podrían soportar el peso de una losa de cubrimiento. Pero el proyecto original no contemplaba esta solución, sino la demolición total del túnel, la protección del colector existente con una losa y el cubrimiento con tierra y grava. Además, el Gobierno central le pide justificar el mantenimiento de los objetivos y de las ayudas europeas. Pero las respuestas del consistorio son insuficientes e inexactas. Afirman que existe un carril bus exclusivo para el transporte público, cuando en realidad este será compartido con los vehículos que quieran acceder a los barrios a lo largo de los 720 metros de longitud del túnel, es decir, casi la mitad de la avenida. Aseguran que mantendrá la tercera fila de árboles en el centro de la avenida, algo imposible en la zona del túnel. Justifican la mejora de la conectividad transversal entre los barrios solo con las aceras más amplias, ya que así cuesta menos tiempo cruzar la avenida. Es ridículo. El Ayuntamiento no descarta eliminar el túnel después de la obra, pero un año después no ha hecho nada. El Ministerio ha advertido que mantenerlo incumple los objetivos de las ayudas, se pierde el carril bus exclusivo, desaparece gran parte de la fila central de árboles y se mantiene la barrera entre barrios. Esto puede suponer la devolución de las ayudas y una grave multa. Alcaldesa, le exigimos coherencia y acción inmediata para eliminarlo antes de que finalice la obra de la avenida. Solicitamos la continuidad del proyecto actual sin demoras, pero al mismo tiempo la licitación de un nuevo proyecto para la supresión del túnel. Y si quiere, podemos hacer un pleno para hablar más específicamente de este tema. Esperamos que sigan el mismo criterio urbanístico y que la ciudad pueda ver cómo las obras de supresión de las barreras urbanas, tanto de Serrería como de Pérez Galdós, como otras, puedan ser una realidad lo antes posible. Muchas gracias.",
        "text_val": "",
        "resum_cas": "Felicita a la alcaldesa por defender el soterramiento de Serrería pero exige coherencia: pide aplicar los mismos principios de desarrollo urbano sostenible para eliminar el túnel de Pérez Galdós, advirtiendo del riesgo de perder fondos europeos.",
        "resum_val": "Felicita l'alcaldessa per defensar el soterrament de Serreria però exigeix coherència: demana aplicar els mateixos principis de desenvolupament urbà sostenible per a eliminar el túnel de Pérez Galdós, advertint del risc de perdre fons europeus.",
    },
    {
        "id": "2025-04-11-2-005",
        "pleno_id": "2025-04-11-2",
        "ordre": 5,
        "intervinient": "José A. Barba",
        "entitat": "AV Nazaret Unido",
        "tipus_entitat": "av",
        "barri_o_zona": "Nazaret",
        "punts_ordre_dia": "Soterramiento de las vías de Serrería",
        "idioma_original": "castellano",
        "text_original": "Buenos días. Muchas gracias, alcaldesa, y al conjunto de la corporación por darnos la posibilidad de tomar la palabra en este pleno sobre una cuestión que afecta y preocupa, y mucho, a los vecinos del barrio de Nazaret. Tomamos la palabra para alzar la voz desde el barrio de Nazaret, quizá para algunos de ustedes un barrio menor. Para alzar la voz y reclamar una vez más lo que consideramos una cuestión de justicia social y urbana, de equidad territorial y sobre todo, de dignidad para nuestro barrio, para la ciudad de València, como es el soterramiento de las vías de Serrería. Las vías de Serrería constituyen desde hace décadas una cicatriz que atraviesa y divide nuestra ciudad. Para el barrio de Nazaret esta barrera ferroviaria ha supuesto un aislamiento crónico, una desconexión física y simbólica del resto de València, dificultando el desarrollo, la cohesión y las oportunidades para nuestros vecindarios. Acabar con esta barrera no es un capricho, es una necesidad urgente y un proyecto de ciudad que debe abordarse con valentía y visión de futuro. En este sentido, desde la Asociación estamos totalmente de acuerdo con los planteamientos que defiende la alcaldesa y su equipo de gobierno en el Ayuntamiento de València. Porque hemos escuchado algunas promesas, algunas propuestas y muchas declaraciones, pero las cosas deben hacerse bien y no dejar a medias un problema que ha de salir del paso. Esto no es resolver un problema, es un agravio. Hay soterramiento de las vías y como hemos venido defendiendo muchas veces, las vías deben ser soterradas lo más al sur posible. Teóricamente al menos llega el soterramiento prácticamente hasta la pista del Saler. Solo así garantiza la verdadera integración por la ciudad y la calidad de vida del barrio. Es un proyecto que puede seguir siendo una patada hacia adelante. No queremos más excusas. Los vecinos y vecinas de Nazaret estamos cansados de promesas que nunca se concretan y de retrasos injustificados y de argumentos técnicos que solo parecen aplicarse cuando se trata de València. Exigimos al Gobierno de España un compromiso firme, claro y definitivo con esta actuación. No entendemos y no podemos aceptar que mientras otras ciudades como Barcelona o municipios de su área metropolitana se llevan a cabo operaciones ferroviarias con su soterramiento multimillonario o mientras en el País Vasco se desarrollan proyectos similares, aquí se nos niega una actuación como mínimo menos costosa y tan necesaria para los valencianos. Es legítimo que nos sintamos discriminados, no hay otra palabra. Para los vecinos de València y en especial los del barrio como es Nazaret tenemos que conformarnos con menos. ¿Por qué seguimos siendo tratados como ciudadanos de segunda? Esto no es un proyecto menor, ni localista. Es un proyecto de ciudad, de futuro, que afecta a la forma de vida de miles de personas y al modelo de desarrollo que queremos en nuestro barrio para la ciudad. Como representante nuestros que son, queremos pedirles que exijan al Gobierno de España que deje atrás la ambigüedad, que escuche a la ciudad y a sus barrios, que se siente a trabajar junto al Ayuntamiento para avanzar en el soterramiento de las vías de Serrería, aún más cuando el Ayuntamiento ya ha expresado su voluntad de cofinanciar la creación e incluso adelantar parte del presupuesto. No pedimos privilegios, pedimos justicia. No queremos ser menos y no vamos a permitir ser muchos menos porque nuestro barrio se está jugando mucho. Reclamamos igualdad de trato a fin de que la marginación histórica dé una solución estructural de una barrera que llevamos demasiado tiempo sufriendo y no pararemos por lograrla. Muchas gracias.",
        "temes": ["urbanisme", "infraestructures", "mobilitat", "barris"],
        "text_cas": "",
        "text_val": "Bon dia. Moltes gràcies, alcaldessa, i al conjunt de la corporació per donar-nos la possibilitat de prendre la paraula en este ple sobre una qüestió que afecta i preocupa, i molt, als veïns del barri de Natzaret. Prenem la paraula per alçar la veu des del barri de Natzaret, potser per a alguns de vostés un barri menor. Per alçar la veu i reclamar una vegada més el que considerem una qüestió de justícia social i urbana, d'equitat territorial i sobretot, de dignitat per al nostre barri, per a la ciutat de València, com és el soterrament de les vies de Serreria. Les vies de Serreria constituïxen des de fa dècades una cicatriu que travessa i dividix la nostra ciutat. Per al barri de Natzaret esta barrera ferroviària ha suposat un aïllament crònic, una desconnexió física i simbòlica de la resta de València, dificultant el desenvolupament, la cohesió i les oportunitats per als nostres veïnats. Acabar amb esta barrera no és un caprici, és una necessitat urgent i un projecte de ciutat que ha d'abordar-se amb valentia i visió de futur. En este sentit, des de l'Associació estem totalment d'acord amb els plantejaments que defén l'alcaldessa i el seu equip de govern a l'Ajuntament de València. Perquè hem escoltat algunes promeses, algunes propostes i moltes declaracions, però les coses han de fer-se bé i no deixar a mitges un problema que ha d'eixir del pas. Això no és resoldre un problema, és un greuge. Hi ha soterrament de les vies i com hem vingut defensant moltes vegades, les vies han de ser soterrades el més al sud possible. Teòricament almenys arriba el soterrament pràcticament fins a la pista del Saler. Sols així garantix la veritable integració per la ciutat i la qualitat de vida del barri. És un projecte que pot seguir sent una puntada de peu cap endavant. No volem més excuses. Els veïns i veïnes de Natzaret estem cansats de promeses que mai es concreten i de retards injustificats i d'arguments tècnics que sols semblen aplicar-se quan es tracta de València. Exigim al Govern d'Espanya un compromís ferm, clar i definitiu amb esta actuació. No entenem i no podem acceptar que mentre altres ciutats com Barcelona o municipis de la seua àrea metropolitana es duen a terme operacions ferroviàries amb el seu soterrament multimilionari o mentre al País Basc es desenvolupen projectes similars, ací se'ns nega una actuació com a mínim menys costosa i tan necessària per als valencians. És legítim que ens sentim discriminats, no hi ha una altra paraula. Per als veïns de València i especialment els del barri com és Natzaret hem de conformar-nos amb menys. Per què continuem sent tractats com a ciutadans de segona? Això no és un projecte menor, ni localista. És un projecte de ciutat, de futur, que afecta la forma de vida de milers de persones i al model de desenvolupament que volem en el nostre barri per a la ciutat. Com a representants nostres que són, volem demanar-los que exigisquen al Govern d'Espanya que deixe arrere l'ambigüitat, que escolte la ciutat i els seus barris, que s'assega a treballar junt amb l'Ajuntament per a avançar en el soterrament de les vies de Serreria, encara més quan l'Ajuntament ja ha expressat la seua voluntat de cofinançar la creació i fins i tot avançar part del pressupost. No demanem privilegis, demanem justícia. No volem ser menys i no anem a permetre ser molt menys perquè el nostre barri s'hi està jugant molt. Reclamem igualtat de tracte a fi que la marginació històrica done una solució estructural d'una barrera que portem massa temps patint i no pararem per aconseguir-la. Moltes gràcies.",
        "resum_cas": "Exige al Gobierno de España un compromiso firme con el soterramiento de las vías de Serrería, denunciando el aislamiento crónico del barrio de Nazaret y reclamando igualdad de trato respecto a otras ciudades.",
        "resum_val": "Exigeix al Govern d'Espanya un compromís ferm amb el soterrament de les vies de Serreria, denunciant l'aïllament crònic del barri de Natzaret i reclamant igualtat de tracte respecte a altres ciutats.",
    },
    # ── 2025-04-11-3: Extraordinary DANA reconstruction pleno ──────────────
    # Parser only captured 9 of ~22 interventions. Presidenta interjections and
    # multiple INTERVENCIONES AL PUNTO N sections broke block detection.
    #
    # Broncano (001) already exists but with incomplete text — UPDATE replaces it.
    {
        "id": "2025-04-11-3-001",
        "pleno_id": "2025-04-11-3",
        "ordre": 2,
        "intervinient": "Ana Juana Broncano López",
        "entitat": "Asociación TDAH MAS 16 València",
        "tipus_entitat": "av",
        "barri_o_zona": "La Torre",
        "punts_ordre_dia": "Reconstrucción DANA",
        "idioma_original": "castellano",
        "text_original": "Muy buenos días. Soy Ana Juana Broncano López, vecina de toda la vida de La Torre, y me gustaría ver en la señora Catalá la cara amable. Hasta ahora solo la hemos visto en fotos y no se ha asomado en ninguna calle a preguntar a los vecinos nada. O sea, realmente no se ha preocupado por el estado psicológico que están padeciendo. Son seis meses, son seis meses de nefasta gestión. Y encima nosotros somos personas que ya tenemos la sensibilidad muy dañada por la señora Catalá, porque nosotros lo que queremos es ayuda, ayuda. Y nosotros lo que pedimos son recursos. Recursos que los tiene el Ayuntamiento. Nosotros somos parte de València, no somos no parte de València. No nos pueden tratar tan injustamente. Y menos a las personas mayores que siguen sin poder bajar a la calle, las tenemos que atender. A los niños. En fin, lo que son nuestros vecinos y vecinas que lo están pasando muy mal. Usted no va, no se pasea por la calle y ve los ojos vidriosos de la gente. Yo sí, porque somos vecinos. Y yo soy de las menos afectadas porque tengo vivienda, pero lo que yo no puedo tolerar que a una vecindad tan dañada se la siga dañando tan injustamente. Es nefasto. Y míreme a la cara. ¿Sabe? Póngame una cara amable. ¿Vale? Y entonces me va a atender...\nMuy bien, me alegro mucho. Pero si toma nota, que sean hechos.\nBueno, en primer lugar yo voy a ir por la parte cultural. De toda la vida, que soy de La Torre, tenemos que cruzar para aquí, para allá, para realizar nuestras inquietudes. Pues muy bien, yo como hemos estado pasando por el puente de la Solidaridad que ha sido una gran alegría para nosotros dentro de lo que nos ha pasado, la catástrofe. Pero una cosa es una catástrofe natural y otra cosa es cómo ustedes la están gestionando. Vale, pues entonces como he tenido que ir mucho a San Marcelino veo que tiene un centro cultural donde se realizan muchas actividades e inquietudes. Porque nosotros en La Torre también tenemos muchas inquietudes, pero lo que no tenemos es centros culturales para la juventud, para nuestros niños, para nuestros mayores. Y una biblioteca decente, no un cuchitril como se está creando ahora. Entonces, un centro cultural es muy necesario para la convivencia, para la sociabilidad, para que los vecinos y vecinas de La Torre compartamos espacios amables.\nY luego, La Torre va en crecimiento. Con lo cual también sería necesario tener una escuela infantil municipal para ayudar. Bueno, porque tiene que haber, porque no tenemos otra, una pequeñita, y La Torre va en crecimiento. Entonces, necesitamos de ese espacio. Y todo lo que digo son competencias municipales. Y luego, por otro lado, ¿por qué no tienen ustedes la decencia de poner una piscina municipal? Porque ya de momento nos tenemos que buscar la vida como siempre en las localidades cercanas. Incluso yo, cuando estudiaba en el Padre Manjón, una profesora muy preparada mentalmente con el deporte nos llevaba a la piscina Vedrí, donde está la Alameda que todo ello lo he vivido. Y entonces teníamos que pasar para arriba, para abajo. Y hablo que yo tengo 64 años. También tengo memoria y he vivido muchas cosas. Y sigue el barrio igual, con muchas necesidades. Y hágase cargo de lo que es su competencia municipal.\nY entonces yo creo que este tipo de gestión usted que tiene la responsabilidad, moral ya creo no lo sé si tiene usted moralidad porque si tuviera ya hubiera velado por nuestros intereses.\nRespétenos usted a nosotros. Cuando me respeten a mí, yo respetaré.\nEstamos aquí desde las 11:00 de la mañana. No han sido capaces de respetarnos.\nY yo también a usted que tenga respeto con los ciudadanos de La Torre, que es usted nuestra alcaldesa y no se olvide que somos de València. Que parece que seamos un apartheid esto ya.\nY luego, lo de la piscina municipal y todo lo que he estado solicitando es para que la convivencia familiar, hablo de mayores, niños, las familias que van en crecimiento, tengamos sociabilidad, tengamos una vida amable. Y somos parte de l'horta y muy contentos. Y tenemos una playa de Pinedo al lado, que yo antes me acuerdo de pequeña iba andando con mi madre y mis amiguitos. Ahora no tenemos ni opción de eso. Por lo menos, la piscina municipal es muy importante. Porque hace calor en València, ¿verdad? Pues nosotros lo pasamos peor que ustedes. No hay derecho. Y somos de València y queremos a València mucho. Quiéranos usted a nosotros.\nYa está, ya he terminado.",
        "temes": ["dana_emergencies", "cultura", "educacio", "esports", "barris", "infraestructures"],
        "text_cas": "",
        "text_val": "Molt bon dia. Sóc Ana Juana Broncano López, veïna de tota la vida de La Torre, i m'agradaria vore en la senyora Catalá la cara amable. Fins ara sols l'hem vista en fotos i no s'ha acostat a cap carrer a preguntar als veïns res. O siga, realment no s'ha preocupat per l'estat psicològic que estan patint. Són sis mesos, són sis mesos de nefasta gestió. I a sobre nosaltres som persones que ja tenim la sensibilitat molt danyada per la senyora Catalá, perquè nosaltres el que volem és ajuda, ajuda. I nosaltres el que demanem són recursos. Recursos que els té l'Ajuntament. Nosaltres som part de València, no som no part de València. No ens poden tractar tan injustament. I menys a les persones majors que seguixen sense poder baixar al carrer, les hem d'atendre. Als xiquets. En fi, el que són els nostres veïns i veïnes que ho estan passant molt malament. Vosté no va, no es passeja pel carrer i veu els ulls vidriosos de la gent. Jo sí, perquè som veïns. I jo sóc de les menys afectades perquè tinc vivenda, però el que jo no puc tolerar que a un veïnat tan danyat se'l seguisca danyant tan injustament. És nefast. I mire'm a la cara. Sap? Pose'm una cara amable. Val? I aleshores m'atendrà...\nMolt bé, m'alegre molt. Però si pren nota, que siguen fets.\nBé, en primer lloc jo vaig a anar per la part cultural. De tota la vida, que sóc de La Torre, hem de creuar cap ací, cap allà, per a realitzar les nostres inquietuds. Doncs molt bé, jo com hem estat passant pel pont de la Solidaritat que ha sigut una gran alegria per a nosaltres dins del que ens ha passat, la catàstrofe. Però una cosa és una catàstrofe natural i una altra cosa és com vostés l'estan gestionant. Val, doncs aleshores com he hagut d'anar molt a San Marcelino veig que té un centre cultural on es realitzen moltes activitats i inquietuds. Perquè nosaltres a La Torre també tenim moltes inquietuds, però el que no tenim és centres culturals per a la joventut, per als nostres xiquets, per als nostres majors. I una biblioteca decent, no un forat com s'està creant ara. Aleshores, un centre cultural és molt necessari per a la convivència, per a la sociabilitat, perquè els veïns i veïnes de La Torre compartim espais amables.\nI després, La Torre va en creixement. Amb la qual cosa també seria necessari tindre una escola infantil municipal per a ajudar. Bé, perquè n'hi ha d'haver, perquè no en tenim altra, una xicoteta, i La Torre va en creixement. Aleshores, necessitem d'eixe espai. I tot el que dic són competències municipals. I després, per un altre costat, per què no tenen vostés la decència de posar una piscina municipal? Perquè ja de moment ens hem de buscar la vida com sempre a les localitats properes. Fins i tot jo, quan estudiava al Pare Manjón, una professora molt preparada mentalment amb l'esport ens portava a la piscina Vedrí, on està l'Alameda que tot allò ho he viscut. I aleshores havíem de passar cap amunt, cap avall. I parle que jo tinc 64 anys. També tinc memòria i he viscut moltes coses. I seguix el barri igual, amb moltes necessitats. I faça's càrrec del que és la seua competència municipal.\nI aleshores jo crec que este tipus de gestió vosté que té la responsabilitat, moral ja crec no sé si té vosté moralitat perquè si en tinguera ja haguera vetlat pels nostres interessos.\nRespecte'ns vosté a nosaltres. Quan em respecten a mi, jo respectaré.\nEstem ací des de les 11:00 del matí. No han sigut capaços de respectar-nos.\nI jo també a vosté que tinga respecte amb els ciutadans de La Torre, que és vosté la nostra alcaldessa i no s'oblide que som de València. Que pareix que siguem un apartheid això ja.\nI després, el de la piscina municipal i tot el que he estat sol·licitant és perquè la convivència familiar, parle de majors, xiquets, les famílies que van en creixement, tinguem sociabilitat, tinguem una vida amable. I som part de l'horta i molt contents. I tenim una platja de Pinedo al costat, que jo abans em recorde de xicoteta anava caminant amb la meua mare i els meus amiguets. Ara no tenim ni opció d'això. Almenys, la piscina municipal és molt important. Perquè fa calor a València, veritat? Doncs nosaltres ho passem pitjor que vostés. No hi ha dret. I som de València i volem a València molt. Vulga'ns vosté a nosaltres.\nJa està, ja he acabat.",
        "resum_cas": "Vecina de La Torre denuncia la nefasta gestión municipal tras la DANA, reclama un centro cultural, escuela infantil municipal y piscina municipal para el barrio, y exige que la alcaldesa atienda las necesidades de los ciudadanos.",
        "resum_val": "Veïna de La Torre denuncia la nefasta gestió municipal després de la DANA, reclama un centre cultural, escola infantil municipal i piscina municipal per al barri, i exigeix que l'alcaldessa atenga les necessitats dels ciutadans.",
    },
    {
        "id": "2025-04-11-3-100",
        "pleno_id": "2025-04-11-3",
        "ordre": 1,
        "intervinient": "Ramón Roberto Expósito Marco",
        "entitat": "Per l'Horta",
        "tipus_entitat": "plataforma",
        "barri_o_zona": "La Torre, Faitanar",
        "punts_ordre_dia": "Reconstrucción DANA",
        "idioma_original": "valenciano",
        "text_original": "Bon dia. Sóc Robert Expósito, veí de la Torre-Faitanar i amb molt d'orgull llaurador a l'horta de Faitanar. Com molta gent d'aquesta ciutat, vaig vore la meua vida devastada a conseqüència de la dana. I com tots al meu barri, vaig perdre amics i veïns que, per desgràcia, no podrem reconstruir les seues vides. Ells mai més tornaran.\nAvui estem ací per parlar de reconstrucció, però des de Faitanar ens preguntem: Reconstrucció de què? D'unes infraestructures que han matat als meus veïns?, que han ofegat les nostres vides? Potser vullguen reconstruir una xarxa d'aigua potable que a Faitanar no tenim, un clavegueram que tampoc tenim. O potser siga la mobilitat, basada en un metro que sis mesos després ens nega l'accés a l'estació. Tots els dies quan anem a treballar ens juguen la vida a l'anar sobre carreteres que han solsit, en llocs s'han reduït un metre d'amplària. Estem parlant de carreteres de dos metres i mig. Sí, s'asfaltaren després de la dana algunes carreteres que tenien clots, però que no implicaven risc per a la vida de les persones. Això sí, eren molt visibles. Què ha de passar perquè això s'arregle?, una altra desgràcia? Ha de morir algú per a donar-li solució? Potser la reconstrucció siga escoltar un poc al ciutadà, saber quines són les seues necessitats i saber el que està passant sobre el terreny.\nEl primer que vàrem intentar reconstruir són les nostres vides. Si hi ha una cosa difícil sobre una horta que a Faitanar sis mesos després encara no hem pogut regar. Per si faltava poc, les collites que aconseguírem salvar ens les estan furtant. On està la guarderia rural? Fa mesos que no la veem. On està la Policia Local? Tampoc la veem. Els nostres camps estan convertint-se en uns abocadors il·legals d'enderrocs, fem i deixalles, i este ajuntament no actua. Al camí vell de Picassent junt a la creu de terme hui en dia ja és una escombrera. Duem més de sis anys denunciant-ho i no s'actua. Des de l'horta demanem que s'actúe, que es faça alguna cosa, que es treballe. Crec que el càrrecs que ostenten els obliga. Sense esta horta esta ciutat no existiria. Cal prendre mesures, posar videovigilància als camins rurals que donen accés a les nostres explotacions i a les nostres cases, reparar els camins que impliquen el perill per a la vida de la gent, una presència policial continuada, la retirada de les taxes en Mercavalència a les explotacions afectades per la dana. Cal previndre la plaga de mosques i mosquits que està gestant-se, perquè d'ací uns mesos serà insuportable. I sobretot, eliminar les barreres arquitectòniques que ens varen ofegar.\nPer acabar, només faré dos dos preguntes, senyora Catalá, que m'agradaria que puguera contestar-me. La primera és perquè aquest ajuntament, el meu ajuntament, no forma part de la Plataforma pel Soterrament de les Vies que varen ofegar els meus veïns. I la segona és perquè aquella fatídica vesprada quan cridàvem desesperats des de Faitanar demanant auxili a la Policia Local ens deien: 'Llame usted a la Policía Local de Paiporta'. No sabien ni en quin terme estava Faitanar. Amb això finalitzaré.",
        "temes": ["dana_emergencies", "medi_ambient", "seguretat", "infraestructures", "barris"],
        "text_cas": "Buenos días. Soy Robert Expósito, vecino de La Torre-Faitanar y con mucho orgullo labrador en la huerta de Faitanar. Como mucha gente de esta ciudad, vi mi vida devastada a consecuencia de la DANA. Y como todos en mi barrio, perdí amigos y vecinos que, por desgracia, no podremos reconstruir sus vidas. Ellos nunca más volverán.\nHoy estamos aquí para hablar de reconstrucción, pero desde Faitanar nos preguntamos: ¿Reconstrucción de qué? ¿De unas infraestructuras que han matado a mis vecinos?, ¿que han ahogado nuestras vidas? Quizás quieran reconstruir una red de agua potable que en Faitanar no tenemos, un alcantarillado que tampoco tenemos. O quizás sea la movilidad, basada en un metro que seis meses después nos niega el acceso a la estación. Todos los días cuando vamos a trabajar nos jugamos la vida al ir sobre carreteras que se han hundido, en sitios se han reducido un metro de anchura. Estamos hablando de carreteras de dos metros y medio. Sí, se asfaltaron después de la DANA algunas carreteras que tenían baches, pero que no implicaban riesgo para la vida de las personas. Eso sí, eran muy visibles. ¿Qué tiene que pasar para que esto se arregle?, ¿otra desgracia? ¿Tiene que morir alguien para darle solución? Quizás la reconstrucción sea escuchar un poco al ciudadano, saber cuáles son sus necesidades y saber lo que está pasando sobre el terreno.\nLo primero que intentamos reconstruir son nuestras vidas. Si hay una cosa difícil sobre una huerta que en Faitanar seis meses después aún no hemos podido regar. Por si faltaba poco, las cosechas que conseguimos salvar nos las están robando. ¿Dónde está la guardería rural? Hace meses que no la vemos. ¿Dónde está la Policía Local? Tampoco la vemos. Nuestros campos se están convirtiendo en unos vertederos ilegales de escombros, basura y residuos, y este ayuntamiento no actúa. En el camino viejo de Picassent junto a la cruz de término hoy en día ya es una escombrera. Llevamos más de seis años denunciándolo y no se actúa. Desde la huerta pedimos que se actúe, que se haga algo, que se trabaje. Creo que los cargos que ostentan les obliga. Sin esta huerta esta ciudad no existiría. Hay que tomar medidas, poner videovigilancia en los caminos rurales que dan acceso a nuestras explotaciones y a nuestras casas, reparar los caminos que implican peligro para la vida de la gente, una presencia policial continuada, la retirada de las tasas en Mercavalència a las explotaciones afectadas por la DANA. Hay que prevenir la plaga de moscas y mosquitos que se está gestando, porque de aquí unos meses será insoportable. Y sobre todo, eliminar las barreras arquitectónicas que nos ahogaron.\nPara acabar, solo haré dos preguntas, señora Catalá, que me gustaría que pudiera contestarme. La primera es por qué este ayuntamiento, mi ayuntamiento, no forma parte de la Plataforma por el Soterramiento de las Vías que ahogaron a mis vecinos. Y la segunda es por qué aquella fatídica tarde cuando llamábamos desesperados desde Faitanar pidiendo auxilio a la Policía Local nos decían: 'Llame usted a la Policía Local de Paiporta'. No sabían ni en qué término estaba Faitanar. Con esto finalizaré.",
        "text_val": "",
        "resum_cas": "Labrador de Faitanar denuncia la devastación de la DANA, la falta de agua potable, alcantarillado, presencia policial y riego seis meses después, y pregunta por qué el Ayuntamiento no forma parte de la Plataforma por el Soterramiento de las vías.",
        "resum_val": "Llaurador de Faitanar denuncia la devastació de la DANA, la falta d'aigua potable, clavegueram, presència policial i reg sis mesos després, i pregunta per què l'Ajuntament no forma part de la Plataforma pel Soterrament de les vies.",
    },
    {
        "id": "2025-04-11-3-101",
        "pleno_id": "2025-04-11-3",
        "ordre": 3,
        "intervinient": "Manuel Folgado Pedrós",
        "entitat": "Associació Cultural i de Consumidors Patraix",
        "tipus_entitat": "cultural",
        "barri_o_zona": "Faitanar, La Torre",
        "punts_ordre_dia": "Reconstrucción DANA",
        "idioma_original": "castellano",
        "text_original": "Buenos días, señora alcaldesa, concejales del Ayuntamiento de València. En primer lugar agradecer a la Asociación Vecinal de Patraix por poder participar en esta sesión extraordinaria. Y también aprovecho que la última vez que estuve aquí comentando, también a la Asociación de La Torre que se me pasó por los nervios, disculpad.\nMe voy a centrar un poquitín en lo que es la zona de Faitanar. Yo soy vecino, soy hijo de agricultores, he sido agricultor hasta prácticamente hace 15-20 años y sigo teniendo tierra en la zona de Faitanar. Comentar simplemente que la huerta se sigue degradando año tras año, década tras década. Se va viendo parcelas abandonadas, caminos rurales sin espacio para circular los peatones, los vehículos, muy mala iluminación, poste de luz y de teléfono a punto de caerse, que ya se comentó en el anterior pleno que estuvimos aquí y a fecha de hoy todavía no se ha podido actuar. Entiendo que hay cosas más importantes, pero sí que nos gustaría a los vecinos de allí que se fuera gestionando.\nSobre todo después de la dana, también indicar que las parcelas agrícolas están todavía sin riego, prácticamente son cinco meses y medio, lo que es riego de agua de río o de las depuradoras. Sí que es cierto que mantenemos con pocos socios lo que son motores de riego que con mucho esfuerzo lo hicieron nuestros abuelos y con ello estamos salvando lo que son los cultivos, tanto de hortalizas como de frutales. Comentar también en cuanto un poco a esta ley de protección de la huerta que quizás aprieta demasiado. Hoy nos acompaña con nosotros también una vecina que es Amparo. Ella tiene 78 años, todavía conduce muy bien. Está la verdad que muy bien ella. Pero tiene un problema ahora con unos vecinos que se han instalado allí y ahora no tienen dónde dejar su vehículo, vehículo que todos en la ciudad tenemos parking público, privado, arcén donde dejarlo, transporte público donde llegar. Ella no quiere, ella solamente quiere seis, diez metros cuadrados donde dejar su coche. ¿No puede dejar unos bolos? Es mi pregunta. A cambio, ella con sus sobrinos, con los nietos, sigue cultivando allí. Tiene una parcela de unos 6.000 metros. Y sería un trueque, de seis metros, diez metros cuadrados a cambio de 6.000 metros. ¿Vale la pena? Creo que sí que vale la pena.\nObviamente, como ha dicho Roberto, también agricultor, vecino y amigo, sí que es cierto que la presencia policial no existe prácticamente, puntualmente. Pero eso nos haría falta también a nosotros, también somos ciudadanos de allí y es difícil vivir en lo que es, bueno, vecinos, sin una protección que pase por allí de forma disuasoria. También para nuestras casas y sobre todo para las cosechas también. Nos falta un espacio de movilidad entre lo que es La Torre y València Sud. No tenemos arcén. Es un peligro eso. Hay momentos que para salir de la carretera a la zona donde está la gasolinera Texaco te puedes tirar cinco o diez minutos a las horas punta. No puedes ni acceder con el coche, cruzar la carretera. Imaginaos los peatones que tengan que venir desde La Torre a Faitanar a coger el metro. Que por cierto, como ha dicho Roberto, todavía seguimos sin arcén. Tenemos que dar toda la vuelta a pie, cerca de 40 minutos andando. Obviamente ahora hace buen tiempo, pero tiempo atrás hemos estado con lluvias y por la tarde a las 06:30 era de noche. Todos buscamos creo que es ese bienestar. Condiciones básicas como es el agua potable, no tenemos. Luz también. Luz, que a la una de la noche sigamos teniendo luz en las calles. Tampoco la tenemos porque son solares. Alcantarillado, tampoco lo tenemos. Esto lo que hace que nuestros mayores que han vivido allí vayan yéndose o bien a residencia o a casa de sus hijos. Y los jóvenes no creo que vayamos por allí sin estas condiciones mínimas.\nDebemos de integrar estas actividades, además de integrar lo que son actividades dentro de ese marco agrícola. Atraer a la población a estos espacios fomentando la agricultura y actividades que puedan convivir sirviendo de esparcimiento a la ciudad. Actividades vinculadas con la naturaleza, zonas verdes donde nuestras familias puedan convivir. Crear jardines dentro de esos espacios. Hay espacios muy abandonados allí. ¿Por qué no crear zonas verdes donde podamos salir? Hablamos de la huerta de la ciudad. Y por qué no de la ciudad a la huerta, disfrutando de estos espacios, incluso donde poder comer una paella con la familia, con los amigos, a traer la ciudad a la huerta y no estar reñidos como a veces nos sentimos nosotros. Una conversión de esas parcelas abandonadas a zonas verdes. Actividades como algunos restaurantes que hoy en día tenemos en medio de la huerta, que tengan su propia cosecha hortícola, que se los obligue de alguna forma y eso es kilómetro cero.\nSí, alcaldesa. Un segundo. Ruego que estudien esa viabilidad real de la huerta adaptada a nuestra sociedad actual, en un estado de bienestar y esa forma de acercar la ciudad a la huerta. Y sí que quiero resaltar también la figura que viene realizando el Consell Agrari en mantener una cierta preocupación por la huerta de esas vivencias y sobre todo, evitar conflictos entre vecinos. Es un buen mediador esta persona y con ello nos ayuda bastante, a parte de todas las gestiones que se vienen realizando.\nGracias.",
        "temes": ["dana_emergencies", "medi_ambient", "infraestructures", "seguretat", "barris"],
        "text_cas": "",
        "text_val": "Bon dia, senyora alcaldessa, regidors de l'Ajuntament de València. En primer lloc agrair a l'Associació Veïnal de Patraix per poder participar en esta sessió extraordinària. I també aprofite que l'última vegada que vaig estar ací comentant, també a l'Associació de La Torre que se'm va passar pels nervis, disculpeu.\nMe centraré un poquet en el que és la zona de Faitanar. Jo sóc veí, sóc fill d'agricultors, he sigut agricultor fins pràcticament fa 15-20 anys i seguisc tenint terra a la zona de Faitanar. Comentar simplement que l'horta es seguix degradant any rere any, dècada rere dècada. Es van veient parcel·les abandonades, camins rurals sense espai per a circular els vianants, els vehicles, molt mala il·luminació, pals de llum i de telèfon a punt de caure, que ja es va comentar en l'anterior ple que vam estar ací i a data de hui encara no s'ha pogut actuar.\nSobretot després de la dana, també indicar que les parcel·les agrícoles estan encara sense reg, pràcticament són cinc mesos i mig. Mantenim amb pocs socis el que són motors de reg que amb molt d'esforç ho van fer els nostres avis i amb això estem salvant els cultius. Cal estudiar la viabilitat real de l'horta adaptada a la nostra societat actual i acostar la ciutat a l'horta.\nGràcies.",
        "resum_cas": "Vecino de Faitanar denuncia la degradación de la huerta tras la DANA, la falta de riego, agua potable, alcantarillado, iluminación y presencia policial, y pide integrar actividades que acerquen la ciudad a la huerta.",
        "resum_val": "Veí de Faitanar denuncia la degradació de l'horta després de la DANA, la falta de reg, aigua potable, clavegueram, il·luminació i presència policial, i demana integrar activitats que acosten la ciutat a l'horta.",
    },
    {
        "id": "2025-04-11-3-102",
        "pleno_id": "2025-04-11-3",
        "ordre": 6,
        "intervinient": "Maria Aniuska Dolz Sánchez",
        "entitat": "AMPA CP Padre Manjón",
        "tipus_entitat": "educacio",
        "barri_o_zona": "La Torre",
        "punts_ordre_dia": "Reconstrucción DANA",
        "idioma_original": "castellano",
        "text_original": "Buenos días a todas y a todos. En primer lugar, dar las gracias a todas las asociaciones y entidades que nos han cedido su turno de palabra para estar hoy aquí. Personalmente si algo bueno he sacado de esta situación es la estrecha relación que tenemos actualmente con muchas de las asociaciones vecinales que nos ayudaron en un primer y siguientes momentos, especialmente con mis compañeras más afectadas de Castellar y Forn d'Alcedo, pero haciendo extensible al resto de pedanías de Pobles del Sud y el resto de València.\nCada mes, desde octubre del año pasado nos preguntan cómo se encuentra La Torre, qué necesidades tiene, qué falta por arreglar. ¿Se puede hablar de normalidad? No, no se puede hablar de normalidad. Después de casi seis meses, este ayuntamiento no ha resuelto las necesidades importantes que hemos transmitido en las reuniones. Habéis hecho cosas, no lo puedo negar. Sobre todo en casos particulares. Pero seguimos repitiendo la misma retahíla de carencias en cada encuentro. Más bien la situación ya estaba mal antes de la dana y queréis dejar las cosas como estaban. Ya no nos conformamos con eso. Queremos La Torre versión 2.0. Esto no es posible si no se realizan inversiones en nuestra pedanía. No podemos depender siempre de ayudas externas. Hablo, entre otras cosas, de los famosos EDIL. El propio Ayuntamiento de València debe asumir la parte que le corresponde y actuar en consecuencia.\nHace unas semanas tuvimos tres días de alerta por fuerte temporal. Colegio cerrado, centro de mayores y alcaldías cerrados, pendientes del caudal del famoso barranco del Poyo. Todo el mundo con el miedo en el cuerpo. Afortunadamente solo fue un susto. Si se llega a repetir la circunstancia del 29 de octubre el mal en La Torre hubiese sido el mismo, desearía que sin víctimas mortales esta vez. No se ha hecho nada en todo este tiempo que pueda evitar que vuelva a pasar. Los principales agravantes de la situación siguen estando. Por ejemplo, las vías del tren y el nuevo cauce del río. ¿Tenemos que sufrir esa incertidumbre cada vez que llueva en alguna parte de València? La salud mental de muchas vecinas y vecinos está al límite. ¿Qué seguridad pueden tener que no vuelva a pasar? Necesitamos acciones preventivas desde antes de ayer.\nLas propuestas de las vecinas y vecinos de La Torre las tienen bien descritas en la moción que ha presentado el Grupo Compromís y seguramente sean las mismas que tengan en los talleres de participación para la agenda de reconstrucción de las pedanías afectadas por la dana que está llevando a cabo este ayuntamiento. Solo pedimos a la hora de decidir se cuente con la participación real de todos los implicados: administraciones, vecinas y vecinos, técnicos, expertos, etcétera.\nPor último, les pido un favor. Que cambien la famosa frasecita de: 'El Ayuntamiento de València ha asumido a pulmón'. Que con un presupuesto de casi 1.400.000.000 euros sobra ese dramatismo. A pulmón lo que llevan haciendo hace meses las personas que viven en plantas bajas dañadas, los daños de pequeños comercios afectados, los inquilinos que apenas pueden pagar el alquiler o los vecinos que no pueden hacer frente a la reparación de sus ascensores y garajes a la vez.\nMuchas gracias.",
        "temes": ["dana_emergencies", "educacio", "participacio_ciutadana", "barris", "infraestructures"],
        "text_cas": "",
        "text_val": "Bon dia a totes i a tots. En primer lloc, donar les gràcies a totes les associacions i entitats que ens han cedit el seu torn de paraula per a estar hui ací. Cada mes, des d'octubre de l'any passat ens pregunten com es troba La Torre, quines necessitats té, què falta per arreglar. Es pot parlar de normalitat? No, no es pot parlar de normalitat. Després de quasi sis mesos, este ajuntament no ha resolt les necessitats importants que hem transmés en les reunions. Volem La Torre versió 2.0. Això no és possible si no es realitzen inversions a la nostra pedania. No podem dependre sempre d'ajudes externes. El propi Ajuntament de València ha d'assumir la part que li correspon i actuar en conseqüència.\nFa unes setmanes vam tindre tres dies d'alerta per fort temporal. Col·legi tancat, centre de majors i alcaldies tancats, pendents del cabal del famós barranc del Poyo. Tot el món amb la por al cos. No s'ha fet res en tot este temps que puga evitar que torne a passar. Necessitem accions preventives des d'abans d'ahir.\nPer últim, els demane un favor. Que canvien la famosa fraseta de: 'L'Ajuntament de València ha assumit a pulmó'. Que amb un pressupost de quasi 1.400.000.000 euros sobra eixe dramatisme. A pulmó el que porten fent fa mesos les persones que viuen en plantes baixes danyades, els danys de xicotets comerços afectats, els inquilins que a penes poden pagar el lloguer o els veïns que no poden fer front a la reparació dels seus ascensors i garatges alhora.\nMoltes gràcies.",
        "resum_cas": "Representante del AMPA del CP Padre Manjón denuncia que seis meses después de la DANA nada ha cambiado en La Torre, exige inversiones reales y acciones preventivas ante futuras riadas.",
        "resum_val": "Representant de l'AMPA del CP Pare Manjón denuncia que sis mesos després de la DANA res ha canviat a La Torre, exigeix inversions reals i accions preventives davant futures riuades.",
    },
    {
        "id": "2025-04-11-3-103",
        "pleno_id": "2025-04-11-3",
        "ordre": 7,
        "intervinient": "Mª Isabel Collado Villagrasa",
        "entitat": "Associació Cuidem la Raïosa",
        "tipus_entitat": "av",
        "barri_o_zona": "La Torre",
        "punts_ordre_dia": "Reconstrucción DANA",
        "idioma_original": "castellano",
        "text_original": "Buenos días. Gracias por este pleno extraordinario, muy necesario. Bueno, gracias no. Ha sido una obligación, desgraciadamente. Quiero comunicarles que ayer vinieron a La Torre para hablarnos del fondo EDIL y nos quedamos muy sorprendidos que aún están preparando el EDIL Dana y que se pidió el EDIL València primero. Pero no estamos en el EDIL València. ¿Por qué? No lo entendemos muy bien porque somos València. El código postal 46017, València. Pero vivimos pasado el cauce del río, que eso por lo visto ha creado una barrera y que poco importa al Ayuntamiento central lo que pase detrás de esa barrera.\nPues lo que pasó es que una noche vino tanta agua y tanto barro que murieron muchos vecinos. Y los que seguimos en vida hemos tenido que luchar con todas nuestras fuerzas contra el barro, contra la inclemencia. Hemos tenido que ir a comprar ropa, ropa interior, zapatos a nuestros vecinos que no tenían nada, darles de comer y ayudarlos. Muchos meses. Yo crucé el primer día el puente para ir a comprar mangueras, para ir a comprar ropa interior para mis vecinos y estaba la Policía ahí en masa. Y yo pregunté: '¿Pero qué os ocurre?', 'No tenemos orden, no podemos pasar a ayudar'. Eso fue horroroso. A la vuelta sí que no subí nada cargada porque soy una persona mayor y en el puente ayudaron mucha gente joven que ya venía a ayudar. Pero la Policía, los Bomberos, etcétera, vinieron a ayudar dos o tres días después. Estábamos completamente solos.\nLuego empezaron a venir las ayudas. En la alcaldía se pusieron cosas, pero sin ningún control. Me ofrecí porque yo he trabajado toda mi vida en transporte internacional y logística. Fui a hablar con la alcaldía y les dije: 'Va a haber abusos. Necesitáis una hoja Excel o un programa'. Y me dijeron que no necesitaban mi ayuda, que quién era yo, que ellos tenían estudios. Y me estuve paseando de la parroquia a la alcaldía y de la alcaldía a la parroquia todo un día pidiendo que por favor entrelazaran datos y no lo hicieron.\nEntonces, como ayer vinieron del Ayuntamiento a decirnos que van a participar con nosotros qué es lo que queremos. Queremos ayuda, no queremos política. No hacemos política en la asociación de vecinos. Pero mucha pena y profunda. Hace falta mucho dinero para reconstruir después de una riada y pedimos lo que ya pedíamos hace muchos años: autobús, estación en València Sud, viviendas asequibles, un centro cultural y deportivo digno, escuelas infantiles. Y deporte, sobre todo deporte, que solamente hay fútbol. Se ha corrido a instalar el fútbol y no hay más deportes en La Torre, y nuestros jóvenes se tienen que ir fuera. Tenemos espacio ahora para hacer centro cultural y deportivo. Y es lo que pedimos, que por favor nos hagan caso y dejen de hacer política en este pleno. Y ayuden de verdad a la gente.",
        "temes": ["dana_emergencies", "serveis_socials", "infraestructures", "cultura", "esports", "barris"],
        "text_cas": "",
        "text_val": "Bon dia. Gràcies per este ple extraordinari, molt necessari. Bé, gràcies no. Ha sigut una obligació, desgraciadament. Vull comunicar-los que ahir van vindre a La Torre per a parlar-nos del fons EDIL i ens vam quedar molt sorpresos que encara estan preparant l'EDIL Dana i que es va demanar l'EDIL València primer. Però no estem en l'EDIL València. Per què? No ho entenem molt bé perquè som València. El codi postal 46017, València. Però vivim passat el llit del riu, que això pel que es veu ha creat una barrera i que poc importa a l'Ajuntament central el que passe darrere d'eixa barrera.\nDoncs el que va passar és que una nit va vindre tanta aigua i tant de fang que van morir molts veïns. I els que seguim en vida hem hagut de lluitar amb totes les nostres forces contra el fang. Hem hagut d'anar a comprar roba, roba interior, sabates als nostres veïns que no tenien res, donar-los de menjar i ajudar-los.\nVolem ajuda, no volem política. Fa falta molts diners per a reconstruir després d'una riuada i demanem el que ja demanem fa molts anys: autobús, estació a València Sud, vivendes assequibles, un centre cultural i esportiu digne, escoles infantils. I esport, sobretot esport, que sols hi ha futbol. I és el que demanem, que per favor ens facen cas i deixen de fer política en este ple. I ajuden de veritat a la gent.",
        "resum_cas": "Vecina de La Torre denuncia el abandono de las pedanías del sur tras la DANA, la falta de coordinación en la gestión de ayudas, y reclama transporte, viviendas asequibles, centro cultural y deportivo.",
        "resum_val": "Veïna de La Torre denuncia l'abandó de les pedanies del sud després de la DANA, la falta de coordinació en la gestió d'ajudes, i reclama transport, vivendes assequibles, centre cultural i esportiu.",
    },
    {
        "id": "2025-04-11-3-104",
        "pleno_id": "2025-04-11-3",
        "ordre": 8,
        "intervinient": "Andrés Eduardo Valverde Gil",
        "entitat": "Associació Cuidem la Raïosa",
        "tipus_entitat": "av",
        "barri_o_zona": "La Torre",
        "punts_ordre_dia": "Reconstrucción DANA",
        "idioma_original": "castellano",
        "text_original": "Buenos días, señora alcaldesa. Buenos días para todos. Como podrán notar, no soy español, pero he sufrido la dana como cada uno de los que habitamos allá. El tema que a mí me duele un poco es el tema de la vivienda. La vivienda es algo que literalmente nos está matando y perdón por la palabra, pero es que esta semana estuve viendo un podcast de un influencer inmobiliario donde prácticamente está queriendo vender València y resume que las personas que no tenemos los recursos salgamos de València. Vale, me ha tocado salir de València. Luego, vayamos a las pedanías del sur. Vale, estoy en las pedanías del sur. Pero busco en Idealista y no hay viviendas de 800 euros. Cada vez la vivienda si cogemos la media está en 1.600, si cogemos la mediana está en 1.200. No nos vamos a reír con la moda. Ahora el tema es los derechos fundamentales y los derechos rectores. Sabemos que el tema de la vivienda es un derecho rector, pero el artículo 47, el artículo 43, todos estos se ven afectados porque no se protege a las viviendas y a las familias. Las familias con hijos, los jóvenes, las personas de bajos ingresos, los adultos mayores no pueden competir con personas que vienen y pagan 12 meses de renta, 12 meses de alquiler. No podemos competir. Ahora soy una persona relajada, 6 meses, con posible a 12 meses. No sabemos qué va a pasar con nosotros. Seguramente el Ayuntamiento me va a tener que desahuciar porque no tenemos otra opción.\nY termino con esto, en la vivienda social he hecho solicitudes. En EVAH, dos veces. En AUMSA. Y el realojo. ¿Cuál de esos cuatro me han servido? Gracias a Dios estoy aquí parado y gracias a una gastroenteritis de mi hija, porque si no hubiese ido a mercar a Carrefour a las siete de la tarde y hoy no estuviera aquí reclamando una vivienda, sino que estuviera en la lista de los afectados. Culmino, la falta de interés en el tema de la vivienda es complicado porque nos estamos llenando de inversión extranjera e inversión nacional. Y todo eso con el tema de la burocracia no podemos competir.\nMuchas gracias.",
        "temes": ["dana_emergencies", "habitatge", "barris"],
        "text_cas": "",
        "text_val": "Bon dia, senyora alcaldessa. Bon dia per a tots. Com podran notar, no sóc espanyol, però he patit la dana com cadascun dels que habitem allà. El tema que a mi em dol un poc és el tema de l'habitatge. L'habitatge és una cosa que literalment ens està matant. Les famílies amb fills, els joves, les persones de baixos ingressos, els adults majors no poden competir amb persones que vénen i paguen 12 mesos de renda, 12 mesos de lloguer. No podem competir. Ara sóc una persona reallotjada, 6 mesos, amb possible a 12 mesos. No sabem què passarà amb nosaltres.\nEn l'habitatge social he fet sol·licituds. En EVAH, dos vegades. En AUMSA. I el reallotjament. Quin d'eixos quatre m'han servit? Gràcies a Déu estic ací dret i gràcies a una gastroenteritis de la meua filla, perquè si no haguera anat a comprar a Carrefour a les set de la vesprada i hui no estiguera ací reclamant un habitatge, sinó que estiguera en la llista dels afectats.\nMoltes gràcies.",
        "resum_cas": "Vecino migrante de La Torre denuncia la crisis de vivienda agravada por la DANA, la imposibilidad de competir en el mercado inmobiliario y la ineficacia de las solicitudes de vivienda social.",
        "resum_val": "Veí migrant de La Torre denuncia la crisi d'habitatge agreujada per la DANA, la impossibilitat de competir al mercat immobiliari i la ineficàcia de les sol·licituds d'habitatge social.",
    },
    {
        "id": "2025-04-11-3-105",
        "pleno_id": "2025-04-11-3",
        "ordre": 9,
        "intervinient": "Ikram Boulghoudan",
        "entitat": "Jóvenes hacia la Solidaridad y el Desarrollo",
        "tipus_entitat": "ong",
        "barri_o_zona": "València",
        "punts_ordre_dia": "Reconstrucción DANA",
        "idioma_original": "castellano",
        "text_original": "Buenos días. Y aquí estamos. Exigimos justicia, transparencia y un poco de respeto. La clase política debe estar a la altura. Basta ya de discursos populistas que alimentan a la extrema derecha. Basta ya de usar a las personas migrantes como moneda de cambio para pactos presupuestarios. Y además venimos a exigir algo que debe ser obvio, la regularización inmediata y sin excepción para todas las personas afectadas por la dana. Porque hay barreras extraculturales que impiden esa protección, como el padrón. Qué alternativa tiene una persona migrante sin contrato escrito ni padrón fijo, aunque lleve años trabajando y viviendo aquí. Acompañamos hoy a más de 40 jóvenes en situación administrativa irregular que vivían en los municipios más afectados y que hoy no pueden optar la regularización porque tenían contratos verbales. ¿De verdad estas personas no son víctimas? ¿De verdad no merecen protección ni reparación? Nosotras sí estuvimos, nos organizamos, actuamos. Y por eso hoy decimos alto y claro: Regularización ya, reconocimiento ya, justicia ya. No vamos a permitir que sigan señalando a quienes han salvado, sostenido, reconstruido, porque nosotras también somos pueblo. Y el pueblo, todo el pueblo tiene derecho a ser defendido. Y por hoy queremos decir con todas las letras: El trabajo de las entidades autoorganizadas por personas migrantes merece visibilidad, respeto, recursos, reconocimientos, porque donde el Estado no llegó llegamos nosotras y no nos vamos a callar.\nMuchas gracias.",
        "temes": ["dana_emergencies", "igualtat", "participacio_ciutadana", "serveis_socials"],
        "text_cas": "",
        "text_val": "Bon dia. I ací estem. Exigim justícia, transparència i un poc de respecte. La classe política ha d'estar a l'altura. Prou ja de discursos populistes que alimenten l'extrema dreta. Prou ja d'usar les persones migrants com a moneda de canvi per a pactes pressupostaris. I a més venim a exigir una cosa que hauria de ser òbvia, la regularització immediata i sense excepció per a totes les persones afectades per la dana. Acompanyem hui a més de 40 joves en situació administrativa irregular que vivien als municipis més afectats i que hui no poden optar a la regularització perquè tenien contractes verbals. De veritat estes persones no són víctimes? Nosaltres sí que vam estar, ens vam organitzar, vam actuar. I per això hui diem alt i clar: Regularització ja, reconeixement ja, justícia ja. El treball de les entitats autoorganitzades per persones migrants mereix visibilitat, respecte, recursos, reconeixements, perquè on l'Estat no va arribar vam arribar nosaltres i no ens callarem.\nMoltes gràcies.",
        "resum_cas": "Exige la regularización inmediata de personas migrantes afectadas por la DANA, denuncia los discursos de odio y reivindica el papel de las entidades migrantes en la reconstrucción.",
        "resum_val": "Exigeix la regularització immediata de persones migrants afectades per la DANA, denuncia els discursos d'odi i reivindica el paper de les entitats migrants en la reconstrucció.",
    },
    {
        "id": "2025-04-11-3-106",
        "pleno_id": "2025-04-11-3",
        "ordre": 10,
        "intervinient": "Jorge Guillot Artés",
        "entitat": "Asociación Cultural Cruces de Mayo La Torre",
        "tipus_entitat": "cultural",
        "barri_o_zona": "Sociópolis, La Torre",
        "punts_ordre_dia": "Reconstrucción DANA",
        "idioma_original": "castellano",
        "text_original": "Buenos días, alcaldesa, miembros del Pleno. Pues bueno, yo puedo ser o debo ser el díscolo de lo que estoy oyendo con mis vecinos. Yo vivo en Sociópolis. Y de momento, en los últimos 15 días, 20 días, el Ayuntamiento está trabajando mucho. Sobre todo en el tema de limpieza de vehículos, que era una cosa que estábamos demandando por tema de seguridad, de contaminación y todo. De momento la zona está quedando bastante limpia. Y a colación de lo que ha dicho el compañero, el tema del campo de fútbol de deporte, pues yo encantado. Ser vecino y poder escuchar a esos niños todos los días de entrenamiento y sobre todo los domingos, oír esas risas que disfrutan de un deporte, pues yo encantadísimo no de tener un campo de fútbol, de tener una piscina y de tener todas las cosas que el Ayuntamiento o que el gobierno en sí pueda ofrecernos, no a mi barrio sino a todos los barrios de València, generando en ello una calidad de vivir y de poder disfrutar de esta tierra que tenemos.\nEl problema que nosotros tenemos realmente pues igual son que los consorcios, vuelvo con el tema del Consorcio, pero yo sigo teniendo derramas. A mí el Consorcio no me facilita los pagos rápidos para habilitar ascensores, garajes y todo. Seguimos teniendo ese problema. Yo que me pongas un parque más, un parque menos, pues al fin y al cabo yo cuando vivo en el piso 19 me gustaría coger un ascensor o poder aparcar los coches directamente y no dejarlos en la calle. El tema de seguridad. Pues yo siempre que veo patrullas de Policía, por lo menos en mi zona. Yo hablo siempre de Sociópolis. Pero lo que es una zona que puede ser de futuro, que realmente tiene que haber construcción y que el Ayuntamiento, del color que sea, de la parte que sea, tiene que apostar que esa zona en breve será un barrio importante de València. Y deberíamos todos un poco pues eso, viendo cómo está el caso de que cuesta todo. Pero no solo el barrio de La Torre. Otros barrios que también por otras circunstancias están afectados no solo por la dana, sino por otras circunstancias que pueda tener. Pues pensar que poco a poco, entre todos, todas las asociaciones, y entre vosotros, todos los políticos, nos echéis una mano para que vayamos teniendo un futuro para las generaciones que vienen en breve.\nMuchísimas gracias.",
        "temes": ["dana_emergencies", "barris", "infraestructures", "seguretat"],
        "text_cas": "",
        "text_val": "Bon dia, alcaldessa, membres del Ple. Jo visc a Sociòpolis. I de moment, en els últims 15-20 dies, l'Ajuntament està treballant molt. Sobretot en el tema de neteja de vehicles, que era una cosa que estàvem demanant per tema de seguretat, de contaminació. De moment la zona està quedant bastant neta. El problema que nosaltres tenim realment és el dels consorcis, seguisc tenint derrames. El Consorci no em facilita els pagaments ràpids per a habilitar ascensors, garatges. Seguim tenint eixe problema. Jo que em posen un parc més, un parc menys, al cap i a la fi jo quan visc al pis 19 m'agradaria agafar un ascensor o poder aparcar els cotxes directament. Sociòpolis és una zona de futur i l'Ajuntament ha d'apostar perquè eixa zona serà un barri important de València.\nMoltíssimes gràcies.",
        "resum_cas": "Vecino de Sociópolis reconoce mejoras recientes en limpieza pero denuncia la lentitud del Consorcio para habilitar ascensores y garajes, y pide apostar por el futuro del barrio.",
        "resum_val": "Veí de Sociòpolis reconeix millores recents en neteja però denuncia la lentitud del Consorci per a habilitar ascensors i garatges, i demana apostar pel futur del barri.",
    },
    {
        "id": "2025-04-11-3-107",
        "pleno_id": "2025-04-11-3",
        "ordre": 11,
        "intervinient": "Consuelo Riveiro Carro",
        "entitat": "AVV de Sant Marcel·lí",
        "tipus_entitat": "av",
        "barri_o_zona": "Sant Marcel·lí, Sociópolis",
        "punts_ordre_dia": "Reconstrucción DANA",
        "idioma_original": "castellano",
        "text_original": "Buenos días. Yo vengo no a pedir sino a exigir, por favor, que queremos un consultorio nuevo, que en Sociópolis hay terrenos de la Conselleria de Sanidad para un centro nuevo de salud y que los médicos y enfermeras sean no sean cambiables, que sean fijos. Y los médicos que puedan decidir también cuando tienen que mandar a un paciente a un especialista, que no tengan que esperar dos años o tres cuando lo llamen, que ya están en el cementerio a lo mejor. Los pacientes sería mejor tratados y menos esperas. Y que para que funcionara bien el ministro de Sanidad debía de haber sido médico y después director médico. Entonces sabría lo que es la sanidad pública. Pero si ponen a cualquiera de ministro de Sanidad, entonces no puede funcionar. Porque yo fui criada en Alemania y nacida, y sé cómo funciona la sanidad. Y es una vergüenza que en una ciudad tan bonita que tenemos como es València y La Torre, que nos tienen abandonados porque ustedes solo miran el centro de València porque es lo que les da dinero con los turistas. Pero La Torre la tratan como lo último, como si fuéramos mierda tirada en el suelo.\nMuchas gracias, eso es todo.",
        "temes": ["dana_emergencies", "salut", "barris"],
        "text_cas": "",
        "text_val": "Bon dia. Jo vinc no a demanar sinó a exigir, per favor, que volem un consultori nou, que a Sociòpolis hi ha terrenys de la Conselleria de Sanitat per a un centre nou de salut i que els metges i infermeres siguen fixos. I els metges que puguen decidir quan han d'enviar un pacient a un especialista, que no hagen d'esperar dos anys o tres. Els pacients serien millor tractats i menys esperes. És una vergonya que en una ciutat tan bonica com és València i La Torre, que ens tenen abandonats perquè vostés sols miren el centre de València perquè és el que els dona diners amb els turistes. Però La Torre la tracten com l'últim.\nMoltes gràcies, això és tot.",
        "resum_cas": "Vecina de Sant Marcel·lí exige un nuevo centro de salud en Sociópolis con médicos fijos, y denuncia el abandono de La Torre frente al centro de la ciudad.",
        "resum_val": "Veïna de Sant Marcel·lí exigeix un nou centre de salut a Sociòpolis amb metges fixos, i denuncia l'abandó de La Torre front al centre de la ciutat.",
    },
    {
        "id": "2025-04-11-3-108",
        "pleno_id": "2025-04-11-3",
        "ordre": 12,
        "intervinient": "Piedad Ruiz",
        "entitat": "Cáritas Diocesana",
        "tipus_entitat": "ong",
        "barri_o_zona": "La Torre, Forn d'Alcedo, Castellar-l'Oliveral",
        "punts_ordre_dia": "Reconstrucción DANA",
        "idioma_original": "castellano",
        "text_original": "Hola, buenos días. En primer lugar, quisiera agradecer sinceramente la oportunidad que nos brindan para poder volver a intervenir en este pleno municipal. Y antes de nada, transmitir mi sorpresa por alguna declaración que he oído referente a los primeros días de la dana, estando yo ahí presente, por la falta de coordinación. Simplemente decirle a esta persona que no debe conocer lo que es la Ley de Protección de Datos. Sí que había una coordinación absoluta entre el ayuntamiento de la pedanía, Servicios Sociales y lo que era la parroquia y actualmente Cáritas.\nBueno, para Cáritas tiene un profundo significado poder dar testimonio de este trabajo compartido que hemos llevado a cabo en estos meses tan difíciles con el Ayuntamiento de València y con el resto de entidades sociales en apoyo de las personas afectadas por la dana en las pedanías de La Torre, Horno de Alcedo y Castellar-l'Oliveral. Como organización con una larga trayectoria de acompañamiento a personas en situación de vulnerabilidad, especialmente en La Torre donde llevamos muchos años trabajando junto a las familias del barrio, conocemos bien una realidad que ha hecho más duro el impacto de esta emergencia. Esta cercanía nos ha permitido actuar sobre el terreno con agilidad y conocimiento desde el primer momento.\nQuiero expresar públicamente nuestro más sincero agradecimiento al Ayuntamiento de València por su compromiso por haber contado desde el primer momento con Cáritas y por haber facilitado una colaboración estrecha, fluida y eficaz. Esta coordinación ha sido fundamental para poder dar una respuesta ágil, organizada y sobre todo humana, centrada en las personas que más lo necesitan en los momentos más difíciles.\nEl nuevo centro social de La Torre va a ser un elemento fundamental. Es una oportunidad de seguir consolidando nuestro compromiso de trabajar de manera estructural y continuada en la mejora de las condiciones de la vida de las familias. Valoramos muy positivamente la activación de la Mesa de Coordinación Social para las Personas Afectadas por la Dana, impulsada por este Ayuntamiento de València. Este espacio en el que participa Cáritas junto a entidades como Cruz Roja, la Red de Lucha contra la Pobreza, el Banco de Alimentos, Aldeas Infantiles, el proyecto Babel y los propios Servicios Sociales municipales nos permite compartir información, coordinar los recursos disponibles y sobre todo, atender de manera integral y personalizada las situaciones de las distintas unidades familiares.\nY quiero terminar agradeciendo de nuevo al Ayuntamiento que haya contado con nosotros, que haya confiado en nosotros y que haya facilitado nuestra labor.\nMuchas gracias.",
        "temes": ["dana_emergencies", "serveis_socials", "participacio_ciutadana", "barris"],
        "text_cas": "",
        "text_val": "Hola, bon dia. En primer lloc, voldria agrair sincerament l'oportunitat que ens brinden per a poder tornar a intervindre en este ple municipal. Per a Càritas té un profund significat poder donar testimoni d'este treball compartit que hem dut a terme en estos mesos tan difícils amb l'Ajuntament de València i amb la resta d'entitats socials en suport de les persones afectades per la dana a les pedanies de La Torre, Forn d'Alcedo i Castellar-l'Oliveral. Volem expresar públicament el nostre més sincer agraïment a l'Ajuntament de València pel seu compromís per haver comptat des del primer moment amb Càritas i per haver facilitat una col·laboració estreta, fluida i eficaç.\nEl nou centre social de La Torre serà un element fonamental. Valorem molt positivament l'activació de la Taula de Coordinació Social per a les Persones Afectades per la Dana, impulsada per este Ajuntament de València. Este espai en el qual participa Càritas junt amb entitats com Creu Roja, la Xarxa de Lluita contra la Pobresa, el Banc d'Aliments, Aldees Infantils, el projecte Babel i els propis Serveis Socials municipals ens permet compartir informació, coordinar els recursos disponibles i sobretot, atendre de manera integral les situacions de les distintes unitats familiars.\nMoltes gràcies.",
        "resum_cas": "Cáritas agradece la coordinación con el Ayuntamiento en la atención a afectados por la DANA, valora la Mesa de Coordinación Social y el futuro centro social de La Torre.",
        "resum_val": "Càritas agraïx la coordinació amb l'Ajuntament en l'atenció a afectats per la DANA, valora la Taula de Coordinació Social i el futur centre social de La Torre.",
    },
    {
        "id": "2025-04-11-3-109",
        "pleno_id": "2025-04-11-3",
        "ordre": 13,
        "intervinient": "Mariam Andrea Narváez Ayala",
        "entitat": "Asociación Por ti Mujer",
        "tipus_entitat": "ong",
        "barri_o_zona": "Sociópolis, La Torre",
        "punts_ordre_dia": "Reconstrucción DANA",
        "idioma_original": "castellano",
        "text_original": "Buenos días. Gracias por este espacio de palabra. Hablo en nombre de la Asociación Por ti Mujer. Somos una comunidad diversa, resiliente y sobre todo comprometida con la ciudad y con nuestro trabajo, y con las compañeras a las que atendemos. Venimos hoy sobre todo para construir y proponer desde nuestra experiencia y cooperación. Hoy queremos hablar de algo que para muchas de nuestras compañeras fue más que un proyecto y hablamos de las huertas urbanas en clave de género que están ubicadas en Sociópolis, en la pedanía de La Torre. Este espacio no solo significaba para las compañeras un espacio de salud y aprendizaje, sino que también era un espacio para construir comunidad. Era un espacio también de dignidad para muchas de nuestras mujeres. Mujeres en situación de vulnerabilidad y de exclusión social. Mujeres que encontraron en estas huertas un espacio de pertenencia, de cuidado mutuo y también de autonomía.\nCuando este espacio dejó de funcionar por la dana no solo se cerraron estas parcelas, sino que se cerró también todo un ecosistema social y emocional que ayudaba justamente a sostener estas vidas de las mujeres. Para muchas de ellas la huerta era un espacio terapéutico y de recuperación personal, pero también de espacio intercultural y de intercambio intergeneracional.\nEn estos momentos, a partir de la crisis generada por la dana, la población migrante ha estado presente desde el día 0, trabajando codo a codo y colaborando en la reconstrucción desde abajo. Sin embargo, también hemos sido víctimas de dos situaciones bastante complejas. No solo la dana, sino también los discursos de odio que se han generado a raíz de esta situación. Pero es que estos bulos no solo afectan nuestra imagen, también afectan nuestras vidas, nuestro acceso a los derechos, nuestra seguridad ciudadana y nuestras posibilidades de participación como ciudadanos de pleno derecho.\nPor eso hoy pedimos que se considere la recuperación del programa de las huertas urbanas de Sociópolis como una opción concreta de justicia social, de sostenibilidad ambiental y de participación ciudadana real. No solo es cuestión medioambiental, es una cuestión de equidad de género, de integración, de interculturalidad y sobre todo de inclusión. Nosotras queremos ser parte de ese camino, porque llevamos caminando en la huerta más de diez años y el trabajo de las mujeres que están allí día a día ha hecho que las huertas urbanas tengan un reconocimiento no solo nacional sino también a nivel internacional como espacios urbanos verdes y de acciones positivas.\nMuchas gracias.",
        "temes": ["dana_emergencies", "igualtat", "medi_ambient", "participacio_ciutadana", "barris"],
        "text_cas": "",
        "text_val": "Bon dia. Gràcies per este espai de paraula. Parle en nom de l'Associació Per tu Dona. Som una comunitat diversa, resilient i sobretot compromesa amb la ciutat. Hui volem parlar de les hortes urbanes en clau de gènere que estan ubicades a Sociòpolis, a la pedania de La Torre. Este espai no sols significava per a les companyes un espai de salut i aprenentatge, sinó que també era un espai per a construir comunitat. Era un espai de dignitat per a moltes de les nostres dones. Dones en situació de vulnerabilitat i d'exclusió social que van trobar en estes hortes un espai de pertinença, de cura mútua i d'autonomia.\nQuan este espai va deixar de funcionar per la dana no sols es van tancar estes parcel·les, sinó que es va tancar tot un ecosistema social i emocional. Per això hui demanem que es considere la recuperació del programa de les hortes urbanes de Sociòpolis com una opció concreta de justícia social, de sostenibilitat ambiental i de participació ciutadana real.\nMoltes gràcies.",
        "resum_cas": "Pide la recuperación de las huertas urbanas de género en Sociópolis destruidas por la DANA, como espacio de justicia social, inclusión e interculturalidad para mujeres migrantes.",
        "resum_val": "Demana la recuperació de les hortes urbanes de gènere a Sociòpolis destruïdes per la DANA, com a espai de justícia social, inclusió i interculturalitat per a dones migrants.",
    },
    # ── 2025-04-11-3 PUNTO 2 ──────────────────────────────────────────────────
    {
        "id": "2025-04-11-3-110",
        "pleno_id": "2025-04-11-3",
        "ordre": 15,
        "intervinient": "Mª Amparo Puchades Giner",
        "entitat": "AV Castellar-l'Oliveral",
        "tipus_entitat": "av",
        "barri_o_zona": "Castellar-l'Oliveral",
        "punts_ordre_dia": "Reconstrucción DANA - Punto 2",
        "idioma_original": "valenciano",
        "text_original": "Bon dia, alcaldessa, regidores, regidors. El passat 20 de desembre poguérem expressar i compartir amb tots vostés en este mateix espai, la casa de tots, l'estat de xoc, inquietud i vulnerabilitat instal·lat a les nostres vides, commocionades pel gran impacte de la catàstrofe, que moltes eren les preguntes que ens assaltaven cada dia, què funcionà i què no funcionà en la prevenció i atenció requerida i urgent. I forem escoltades i ateses amb proximitat per l'alcaldessa. I volem creure que per tots vostés.\nVenim mantenint una sèrie de reunions de seguiment on podem expressar necessitats, demandes, amb escolta, respecte i paciència, molta paciència per la nostra part. Ens esforcem en aportar solucions, en ser proactives, atenent el més urgent i immediat del nostre veïnat, lluny de crispacions, sorolls, exageracions o fanatisme, perquè sabem de la magnitud i complexitat que requerix la reconstrucció i restauració dels nostres hàbitats i les nostres vides.\nPerò sis mesos després cal un ple extraordinari i forçat que els interpel·la com a governança. No han estat capaços d'integrar-nos de primera mà ni en la comissió no permanent, ni en les seues conclusions, ni en processos participatius reals i seriosos. No ens sentim tractades com a ciutadanes compromeses, madures i organitzades. No ens han oferit espais on poder fer una crítica serena i constructiva que creiem absolutament necessària per no repetir errors i per prendre les solucions adequades. Cal una col·laboració estreta i sincera per garantir que les accions i decisions adoptades responguen realment a les necessitats i aspiracions de la comunitat.\nI lluny, molt lluny d'això, dia a dia veiem com ens han escalat a càlculs interessats i partidistes. Com podem recuperar la confiança, la tranquil·litat i la pau quan l'esfera política ignora o banalitza els efectes del canvi climàtic, de la crisi ecosocial i de biodiversitat que afrontem?\nDes dels 14 punts de la proposta d'acord de Castellar-l'Oliveral, exposaré el número 6 per la gran preocupació del veïnat. Es tracta de l'eliminació de les barreres artificials al pas de l'aigua front a noves avingudes, com l'avinguda de Ruiz i Comes. Cal aprofitar les sis séquies que travessen l'avinguda, tres de rec i tres de desaigüe, per a drenar el poble. Les séquies no tenen entrades per l'aigua a l'oest de l'avinguda. El ribàs no pot fer la seua funció tal com està i el pont de pantaló tampoc, perquè en el seu dia les infraestructures preexistents i pròpies de l'horta no van ser respectades i estan tallades o mal canalitzades. Cal augmentar la permeabilitat del sòl implementant sistemes de drenatge sostenible per evitar la retenció de l'aigua, garantir accions de drenatge natural en les intervencions urbanes, eliminar barreres i promoure la renaturalització del territori. Punt 7: Reclamar al Consell la recuperació de la Llei 5/2018 de l'horta de València. Punt 10: Crear una taula de seguiment amb la participació de les associacions veïnals, grups d'experts en adaptació al canvi climàtic i tots els grups polítics. Pla de barri integral complet.\nI ara els demane un compromís a tots vostés, el compromís per la seua part d'atendre i tindre en consideració les evidències científiques sobre canvi climàtic i territori en el Mediterrani ibèric. Necessitem, volem i reclamem polítiques d'altura.\nMoltes gràcies.",
        "temes": ["dana_emergencies", "medi_ambient", "participacio_ciutadana", "infraestructures", "barris"],
        "text_cas": "Buenos días, alcaldesa, concejalas, concejales. El pasado 20 de diciembre pudimos expresar y compartir con todos ustedes en este mismo espacio, la casa de todos, el estado de shock, inquietud y vulnerabilidad instalado en nuestras vidas, conmocionadas por el gran impacto de la catástrofe.\nVenimos manteniendo una serie de reuniones de seguimiento donde podemos expresar necesidades, demandas, con escucha, respeto y paciencia, mucha paciencia por nuestra parte. Nos esforzamos en aportar soluciones, en ser proactivas, atendiendo lo más urgente e inmediato de nuestro vecindario.\nPero seis meses después hace falta un pleno extraordinario y forzado que les interpela como gobernanza. No han sido capaces de integrarnos de primera mano ni en la comisión no permanente, ni en sus conclusiones, ni en procesos participativos reales y serios. No nos sentimos tratadas como ciudadanas comprometidas, maduras y organizadas.\nDesde los 14 puntos de la propuesta de acuerdo de Castellar-l'Oliveral, expondré el número 6 por la gran preocupación del vecindario. Se trata de la eliminación de las barreras artificiales al paso del agua frente a nuevas avenidas. Hay que aprovechar las seis acequias que atraviesan la avenida para drenar el pueblo. Hay que aumentar la permeabilidad del suelo implementando sistemas de drenaje sostenible, garantizar acciones de drenaje natural, eliminar barreras y promover la renaturalización del territorio. Punto 7: Reclamar al Consell la recuperación de la Ley 5/2018 de la huerta de València. Punto 10: Crear una mesa de seguimiento con asociaciones vecinales, expertos en cambio climático y todos los grupos políticos. Plan de barrio integral completo.\nNecesitamos, queremos y reclamamos políticas de altura.\nMuchas gracias.",
        "text_val": "",
        "resum_cas": "Representante de Castellar-l'Oliveral critica la falta de participación ciudadana real en la reconstrucción post-DANA y propone eliminar barreras al drenaje, recuperar la ley de la huerta y crear una mesa de seguimiento.",
        "resum_val": "Representant de Castellar-l'Oliveral critica la falta de participació ciutadana real en la reconstrucció post-DANA i proposa eliminar barreres al drenatge, recuperar la llei de l'horta i crear una taula de seguiment.",
    },
    # ── 2025-04-11-3 PUNTO 3 ──────────────────────────────────────────────────
    {
        "id": "2025-04-11-3-111",
        "pleno_id": "2025-04-11-3",
        "ordre": 18,
        "intervinient": "Silvana Gabriela Cabrera Martínez",
        "entitat": "Asociación Intercultural Candombe",
        "tipus_entitat": "ong",
        "barri_o_zona": "València",
        "punts_ordre_dia": "Reconstrucción DANA - Punto 3",
        "idioma_original": "castellano",
        "text_original": "Hoy vengo a este pleno a ser el altavoz de la situación que viven miles de personas que siguen siendo invisibilizadas por este ayuntamiento. Personas migrantes que antes, durante y después de la dana han sido dejadas atrás, ignoradas por unas instituciones más preocupadas por limpiar su imagen que por garantizar derechos y brindar soluciones. La dana dejó al descubierto no solo los fallos estructurales en las infraestructuras, sino una verdad aún más grave: el abandono institucional hacia las personas migrantes que, según el informe de Oxfam, son entre 28.000 y 41.000 personas las que viven en los municipios afectados.\nA pesar de esta realidad concreta, las autoridades no han gestionado ningún plan estatal ni autonómico para ayudar a quienes se encuentran en situación administrativa irregular, ni mucho menos ningún plan de reubicación para las familias afectadas. Antes y después de la dana, el empadronamiento ha sido un obstáculo burocrático e ideológico. Lo que debería ser un derecho y obligación de los ayuntamientos, el acceso al padrón para poder existir a los ojos de la Administración, se convierte en una herramienta de exclusión. Sin padrón no hay derechos, no hay acceso a la sanidad, ni a la educación, ni a los servicios sociales, ni a las ayudas específicas creadas para subsanar esta emergencia.\nA esto se suma la dificultad para acceder a alquileres dignos, para escolarizar a sus hijos e hijas o para simplemente vivir. A día de hoy, miles de personas siguen sin regularizar su situación porque eso para ustedes no es una prioridad. Desde las instituciones públicas se estigmatiza a la juventud migrante, se propagan discursos de odio, se maltrata a quienes van a realizar un trámite, se hace política desde el miedo. Hablo de trabajadoras del hogar y los cuidados que después de haber salvado la vida a sus empleadores fueron despedidas sin ningún tipo de derecho, de las trabajadoras del campo y de la construcción. Hablo de personas viviendo en condiciones infrahumanas, de jóvenes detenidos en la calle por la estrategia racista de paradas por perfil racial.\nUna vez más, las organizaciones de base fuimos quienes respondimos para brindar atención a las personas migrantes, para hacer lo que ustedes no hicieron. Frente a su abandono, el Colectivo Parque Alcosa y Regularización Ya somos quienes hemos salido a las calles creando una unidad móvil de atención en las zonas afectadas.\nEs por eso que hoy venimos a exigir que los procesos de reconstrucción de los barrios no se hagan desde una mirada racista y colonial. Es urgente que las administraciones públicas asuman su responsabilidad frente a la ausencia de alternativas que garanticen el acceso al padrón de las personas migrantes. Que se preocupen políticas públicas con un enfoque antirracista. Basta de lavarse las manos con discursos vacíos. Basta de convertir la vida de las personas migrantes en moneda de cambio político.\nRegularización ya.",
        "temes": ["dana_emergencies", "igualtat", "serveis_socials", "habitatge", "participacio_ciutadana"],
        "text_cas": "",
        "text_val": "Hui vinc a este ple a ser l'altaveu de la situació que viuen milers de persones que seguixen sent invisibilitzades per este ajuntament. Persones migrants que abans, durant i després de la dana han sigut deixades arrere, ignorades per unes institucions més preocupades per netejar la seua imatge que per garantir drets i brindar solucions. La dana va deixar al descobert no sols les fallades estructurals en les infraestructures, sinó una veritat encara més greu: l'abandó institucional cap a les persones migrants.\nMalgrat esta realitat concreta, les autoritats no han gestionat cap pla estatal ni autonòmic per a ajudar a qui es troben en situació administrativa irregular. L'empadronament ha sigut un obstacle burocràtic i ideològic. El que hauria de ser un dret i obligació dels ajuntaments es convertix en una eina d'exclusió. Sense padró no hi ha drets.\nPer això hui venim a exigir que els processos de reconstrucció dels barris no es facen des d'una mirada racista i colonial. És urgent que les administracions públiques assumisquen la seua responsabilitat. Regularització ja.",
        "resum_cas": "Denuncia el abandono institucional hacia personas migrantes tras la DANA, el empadronamiento como herramienta de exclusión, y exige políticas antirracistas y regularización inmediata.",
        "resum_val": "Denuncia l'abandó institucional cap a persones migrants després de la DANA, l'empadronament com a eina d'exclusió, i exigeix polítiques antiracistes i regularització immediata.",
    },
    {
        "id": "2025-04-11-3-112",
        "pleno_id": "2025-04-11-3",
        "ordre": 19,
        "intervinient": "Beatriu Cardona Prats, Joan Domínguez Pavía",
        "entitat": "STA-Intersindical",
        "tipus_entitat": "sindical",
        "barri_o_zona": "Castellar-l'Oliveral, La Torre, Forn d'Alcedo",
        "punts_ordre_dia": "Reconstrucción DANA - Punto 3",
        "idioma_original": "valenciano",
        "text_original": "Molt bon dia, membres de la corporació municipal. Intervindrem en eixos 5 minuts que tenim entre els dos, Joan Domínguez i jo mateixa, Beatriu Cardona, representant al nostre sindicat i com a membres del Consell Escolar Municipal de València en representació del nostre sindicat, que és el majoritari docent. Per suposat, anem a enfocar la nostra intervenció al món educatiu i subscrivim les paraules de les entitats veïnals i de persones migrades que han intervingut abans.\nLa capacitat de resposta davant la dana que va afectar a València va mostrar molts aspectes millorables, per dir-ho suaument. La gestió inicial va estar tràgicament marcada per retards, la qual cosa va limitar la coordinació i l'assignació de recursos en els moments crítics. No actuar a l'hora va ser determinant i això va costar vides que no podrem recuperar mai. Molts veïns i veïnes, col·lectius locals i organitzacions socials hem denunciat una falta de previsió, de coordinació i de resposta eficaç per part de les administracions.\nTot i que la versió institucionalitzada vol canviar la història, la realitat viscuda a peu de carrer als pobles del sud de València, com Castellar-Oliveral, la Torre o Forn d'Alcedo, va ser molt més crua. Per quatre motius. Primer, no es va activar a temps cap protocol d'alerta encara que l'episodi de pluges estava anunciat des de feia dies. Dos, les zones inundables no tenien cap tipus de prevenció implementada. Tres, bombers, policies i serveis d'emergència van ser enviats tard i sense mitjans suficients. Quatre, va haver una manca absoluta d'informació oficial.\nEls dies posteriors a la dana moltes cases i comerços van quedar abandonades a la seua sort, sense ajuda institucional immediata. I la neteja i assistència van recaure en gran part en la solidaritat veïnal. De la mateixa forma, els centres educatius van vore com era el personal docent i no docent del centre, mestres, conserges, educadores, que acudien a netejar el fang i a posar en ordre de forma immediata les instal·lacions. I va ser gràcies a això que els centres afectats pogueren reiniciar les seues activitats de seguida.\nHui per hui, quasi cinc mesos i mig després, hem de seguir denunciant algunes situacions de precarietat a molts nivells que estan patint les nostres escoles.\nHui dia encara no està operatiu el gimnàs del CEIP Forn d'Alcedo. Seguix en les mateixes condicions. En algunes aules encara poden apreciar-se humitats. Al CEIP Castellar-l'Oliveral sabem que la Conselleria encara no ha sufragar les despeses originades per la gratuïtat en els menús de l'alumnat que va acollir afectat per la dana. Al CEIP Pare Manjón continuen esperant resposta respecte a què fer davant les peticions de certificats que s'han perdut arrossegats per les aigües. El mobiliari amb el qual s'ha anat reposant tot allò perdut ha arribat amb molta lentitud.\nPer millorar la situació dels centres afectats és fonamental implementar mesures concretes: agilització de tràmits burocràtics, transparència i seguiment, prioritzar els centres educatius, inversió en resiliència i participació ciutadana.\nHui es dona la casualitat que fa 32 anys que va ser assassinat Guillem Agulló. Sempre diem ni oblit ni perdó. I citant també a una representant veïnal, diem 20:11, ni oblit ni perdó.",
        "temes": ["dana_emergencies", "educacio", "participacio_ciutadana", "barris"],
        "text_cas": "Muy buenos días, miembros de la corporación municipal. Intervendremos en esos 5 minutos que tenemos entre los dos, Joan Domínguez y yo misma, Beatriu Cardona, representando a nuestro sindicato y como miembros del Consejo Escolar Municipal de València en representación de nuestro sindicato, que es el mayoritario docente. Por supuesto, vamos a enfocar nuestra intervención al mundo educativo.\nLa capacidad de respuesta ante la DANA que afectó a València mostró muchos aspectos mejorables, por decirlo suavemente. La gestión inicial estuvo trágicamente marcada por retrasos. No actuar a tiempo fue determinante y eso costó vidas que no podremos recuperar nunca. La realidad vivida a pie de calle en los pueblos del sur de València fue mucho más cruda. No se activó a tiempo ningún protocolo de alerta. Las zonas inundables no tenían ningún tipo de prevención implementada. Bomberos, policías y servicios de emergencia fueron enviados tarde y sin medios suficientes. Hubo una falta absoluta de información oficial.\nLos centros educativos vieron cómo era el personal docente y no docente quien acudía a limpiar el barro. Hoy en día aún no está operativo el gimnasio del CEIP Forn d'Alcedo. En el CEIP Castellar-l'Oliveral la Conselleria aún no ha sufragado los gastos de los menús del alumnado acogido. En el CEIP Padre Manjón continúan esperando respuesta sobre los certificados perdidos.\nEs fundamental implementar medidas concretas: agilización de trámites burocráticos, transparencia, priorizar los centros educativos, inversión en resiliencia y participación ciudadana.\nHoy se da la casualidad de que hace 32 años fue asesinado Guillem Agulló. Siempre decimos ni olvido ni perdón. 20:11, ni olvido ni perdón.",
        "text_val": "",
        "resum_cas": "El sindicato docente STA-Intersindical denuncia la nefasta gestión de la DANA en los centros educativos de las pedanías del sur, con gimnasios inoperativos, mobiliario sin reponer y falta de financiación.",
        "resum_val": "El sindicat docent STA-Intersindical denuncia la nefasta gestió de la DANA als centres educatius de les pedanies del sud, amb gimnasos inoperatius, mobiliari sense reposar i falta de finançament.",
    },
    # Sancanuto punto 3: real speech (replaces 012 which was just "53 minuts de silenci")
    {
        "id": "2025-04-11-3-113",
        "pleno_id": "2025-04-11-3",
        "ordre": 17,
        "intervinient": "Cintia Sancanuto Chardí",
        "entitat": "AV del Palmar",
        "tipus_entitat": "av",
        "barri_o_zona": "El Palmar",
        "punts_ordre_dia": "Reconstrucción DANA - Punto 3",
        "idioma_original": "valenciano",
        "text_original": "Gràcies. Me n'alegre per una part que hagen reconduït el debat en un sol punt perquè una de les coses que es basa l'administració, en esta i en totes, és el tema de las parcelitas. Este trosset és meu, este és d'un altre. Vuelva usted mañana. Açò és en la siguiente ventanilla. Aleshores, tractar-nos a tot el sud com un sol conjunt interdependent és una cosa que cal sol·licitar. Interdependent i també com a part de la ciutat.\nEn una intervenció anterior han dit que està molt lleig que les entitats ciutadanes fem política. La política és l'activitat que fa la ciutadania quan intervé als assumptes públics amb la seua opinió, vot o de qualsevol altra forma. Si, sí que fem política. Qualsevol acte públic és política. El que no fem és partidisme. No tenia preparada esta segona intervenció. Era una mesura d'autoprotecció que hem dissenyat els pobles perquè no tenim els mateixos drets, no tenim dret a rèplica. Vostés ara van a intervindre, van a parlar i no ens anem a poder defendre fins a un altre plenari on ens escolten, i hem vist que no tenen massa ganes d'escoltar-nos.\nUna de les coses que demanem és la participació i vaig a dir-los -no ho dic jo, és un terme acadèmic- que la participació no és 'le informo' i 'esto se publicó en el DOG'. La participació no és manipulació. La participació no és fer-se una foto amb nosaltres i un maquillatge estètic. Ni tan sols és només informació. La participació comença amb la consulta, continua amb la coordinació i el compromís amb eixa consulta. I la participació finalitza amb donar-li a qui ha participat la capacitat d'agència per a resoldre els seus problemes, no decidir per altres.\nVoldria comentar temes que han estat molt lletjos. Per exemple, la preciosa campanya 'Qué bien sabe volver al Palmar' no ens va saber tant bé, perquè nosaltres vam estar rebent i desviant turismes els mateixos dies de les inundacions, i els vam haver de desviar el mateix poble. Turisme estranger desinformat que pretenia arribar a Alginet en bicicleta en plena inundació, totalment desinformat, que açò es va corregir i es va traduir en una informació retardada i mal. I des de les mateixes agències de turisme, oficines de turisme de l'Ajuntament, regentades per Visit València, quan ja s'havia passat tota la inundació i el que reclamava era la recuperació econòmica del sector hostaler, que és molt important al meu poble, se'ls estava dient que no vingueren a l'Albufera. Aquella campanya de Qué bien sabe era què agre ens ha sabut que l'Ajuntament ens tire a la gent fora.\nBé, crec que no cal que diga res més. Han estat coses molt lleges, coses de falta de comunicació i d'un profund desconeixement. Ja que han demostrat eixe profund desconeixement del nostre territori només demanem això, que ens continuen escoltant i que eixa escolta implique un compromís en respectar aquelles coses que pacten amb nosaltres.\nI ara, si alguna persona més del veïnat vol dir alguna cosa en este minut i mig que em queda, pregue que passeu.",
        "temes": ["dana_emergencies", "participacio_ciutadana", "economia", "barris"],
        "text_cas": "Gracias. Me alegro por una parte de que hayan reconducido el debate en un solo punto porque una de las cosas en que se basa la administración, en esta y en todas, es el tema de las parcelitas. Este trocito es mío, este es de otro. Vuelva usted mañana. Esto es en la siguiente ventanilla. Entonces, tratarnos a todo el sur como un solo conjunto interdependiente es algo que hay que solicitar. Interdependiente y también como parte de la ciudad.\nEn una intervención anterior han dicho que está muy feo que las entidades ciudadanas hagamos política. La política es la actividad que hace la ciudadanía cuando interviene en los asuntos públicos con su opinión, voto o de cualquier otra forma. Sí, sí que hacemos política. Cualquier acto público es política. Lo que no hacemos es partidismo. No tenía preparada esta segunda intervención. Era una medida de autoprotección que hemos diseñado los pueblos porque no tenemos los mismos derechos, no tenemos derecho a réplica. Ustedes ahora van a intervenir, van a hablar y no nos vamos a poder defender hasta otro plenario donde nos escuchen, y hemos visto que no tienen muchas ganas de escucharnos.\nUna de las cosas que pedimos es la participación y voy a decirles -no lo digo yo, es un término académico- que la participación no es 'le informo' y 'esto se publicó en el DOG'. La participación no es manipulación. La participación no es hacerse una foto con nosotros y un maquillaje estético. Ni siquiera es solo información. La participación empieza con la consulta, continúa con la coordinación y el compromiso con esa consulta. Y la participación finaliza con darle a quien ha participado la capacidad de agencia para resolver sus problemas, no decidir por otros.\nQuería comentar temas que han sido muy feos. Por ejemplo, la preciosa campaña 'Qué bien sabe volver al Palmar' no nos supo tan bien, porque nosotros estuvimos recibiendo y desviando turistas los mismos días de las inundaciones, y los tuvimos que desviar el mismo pueblo. Turismo extranjero desinformado que pretendía llegar a Alginet en bicicleta en plena inundación. Y desde las mismas agencias de turismo, oficinas de turismo del Ayuntamiento, regentadas por Visit València, cuando ya se había pasado toda la inundación y lo que reclamaba era la recuperación económica del sector hostelero, que es muy importante en mi pueblo, se les estaba diciendo que no vinieran a la Albufera. Aquella campaña de Qué bien sabe era qué amargo nos ha sabido que el Ayuntamiento nos eche a la gente fuera.\nBien, creo que no hace falta que diga nada más. Han sido cosas muy feas, cosas de falta de comunicación y de un profundo desconocimiento. Ya que han demostrado ese profundo desconocimiento de nuestro territorio solo pedimos eso, que nos sigan escuchando y que esa escucha implique un compromiso en respetar aquellas cosas que pacten con nosotros.",
        "text_val": "",
        "resum_cas": "Segunda intervención de Sancanuto defendiendo que las entidades ciudadanas hacen política legítima, exigiendo participación real y denunciando la campaña turística que perjudicó al Palmar tras la DANA.",
        "resum_val": "Segona intervenció de Sancanuto defensant que les entitats ciutadanes fan política legítima, exigint participació real i denunciant la campanya turística que va perjudicar el Palmar després de la DANA.",
    },
    # ── 2025-07-22: Fix Oliver/Estrela text + merge El Hadri/Tabib ─────────────
    {
        "id": "2025-07-22-002",
        "pleno_id": "2025-07-22",
        "ordre": 2,
        "intervinient": "Miguel Carlos Oliver Trilles, Jose Domingo Estrela Leiva",
        "entitat": "Associació Cultural Falla Av. Malvarrosa-Antoni Pons-Cavite / Societat Marina Auxiliant",
        "tipus_entitat": "cultural",
        "barri_o_zona": "Poblats Marítims, Cabanyal",
        "punts_ordre_dia": "Discursos de odio",
        "idioma_original": "mixt",
        "text_original": "Sr. Oliver: Bueno, pues lo primero, señora presidenta, buenas tardes señoras y señores concejales. Un profundo respeto a todos ustedes, pues la verdad tienen un trabajo bastante difícil. Quiero darle primero las gracias a la Asociación Cultural Falla de la Malvarrosa por darnos esta oportunidad no solo de estar aquí, sino encima de que se nos escuche. Porque hace falta que nos escuchen todos. Yo os lo pido por favor, a vosotros y a vosotras.\nVamos a ver, mi nombre es Miguel Oliver y represento a la Sociedad Marina Auxiliante. Y ustedes dirán, ¿y qué es la Marina Auxiliante? Bueno, pues vamos a ver, ya no es lo que es la Marina Auxiliante, sino la gente que compone esa Marina Auxiliante. Son cientos de familias valencianas que formamos y hemos formado la columna vertebral de los poblados marítimos.\nVivimos desde hace décadas bajo la sombra de una profunda inseguridad jurídica. Nuestros hogares, construidos con el esfuerzo de incontables horas, el trabajo, el cariño trasmitido a lo largo de generaciones, se asienta sobre un terreno cuya propiedad es del Ayuntamiento de València y que ahora puede reclamarlo como suyo. Esta situación sería insostenible si lo reclamaran de esta forma. Representaría un ataque directo a la vida, a la historia y a la dignidad de quienes hemos forjado y mantenido esta comunidad, que hemos vivido en el Cabanyal, que hemos aguantado todos los embistes.\nPero claro, ahora tenemos una reciente declaración de caducidad de la concesión del 2018 y la confirmación judicial de la propiedad del suelo y del vuelo por parte del Ayuntamiento en abril del 2024. Nos hemos quedado sin nada. Hemos sido sistemáticamente ignorados. Nuestras solicitudes de compra del suelo han caído en un silencio administrativo sepulcral. Nos hemos enfrentado a bloqueos constantes de permisos de obra y de mantenimiento.\nSomos familias honradas, gente trabajadora. Nuestro apego al lugar es innegable. Y perderlo sería una amputación de nuestra propia identidad, de nuestra propia historia. ¿Qué hay de aquellos que con su esfuerzo y su arraigo han contribuido al crecimiento y la vitalidad de nuestras ciudades durante décadas? ¿Les expropiamos la vivienda porque ya es del Ayuntamiento? ¿Los dejamos sin vivienda?\nCuando fuimos a entregar las llaves de lo que era la concesión, fuimos a la Concejalía que nos toca que es Patrimonio. Y ahí nos encontramos a Juan Manuel Badenas y a la concejala de Responsabilidad Patrimonial, Cecilia Herrero. Ha sido un valioso rayo de esperanza porque nos han escuchado, nos han comprendido y encima nos quieren ayudar.\nEsperamos que entre todos se puedan encontrar una solución jurídica definitiva. Confiamos en que la moción que ha propuesto en este Pleno pueda otorgar una seguridad jurídica a los vecinos y vecinas. Es hora de que el Ayuntamiento reconozca el arraigo de nuestras familias y nos permita consolidar la propiedad del suelo. Ojalá se llegue a un acuerdo que finalmente se abra camino para que las familias de la Lonja y otras zonas afectadas que puedan regularizar la propiedad de sus viviendas. Y muchísimas gracias por escucharme.\nSr. Estrela: Bona vesprada a tots i a totes. Crec que em queda molt poc de temps. Vaig a canviar un poc el que anava a dir i resumir-ho. Primer, he sentir parlar fa molt poc de temps del tema de la vivenda. Ací del que es tracta ara és que 40 famílies que viuen en la Llotja de Pescadors que estan vivint més de cent anys. Jo sóc un propietari i ho he heretat del meu iaio. Va ser dels primers que varen construir la Llotja de Pescadors. Ara, en quina situació ens trobem? Després de la sentència n'hi ha un dubte total de què és el que va a passar. L'Ajuntament encara no ens ha dit res. Per tant, el que volem és reprendre una altra vegada les negociacions que teníem obertes per saber en quina situació ens trobem. La gent, les famílies tenen molta por i molta incertesa. No és lògic que després d'estar vivint cent anys, no cent anys seguits sinó escalonadament, ara es troben en una situació que possiblement els expropien. Expropien a unes famílies que han estat pagant impostos, IBI, llum, aigües, en una situació normal de viure. No seria lògic.\nDemanem a l'Ajuntament que als seus ciutadans, que els ha de protegir d'alguna manera, òbriga les negociacions i es puga arribar a un acord, que és el que nosaltres demanem. Però ja portem molts anys demanant-ho. És la compra del sòl. Estem disposats a pagar-ho, perquè el vol és nostre. És el que construïren els agüelos. Voldríem arribar a un nou consens amb l'Ajuntament, però que se'ns òbriga una taula de negociació clara per a poder tractar el tema. Torne a repetir, les famílies tenen molta por. És gent humil i és gent major. Si el dia que siga això s'acabara, diguen vostés on van a viure, quina vida els espera quan no han fet res realment per a perdre la propietat de la vivenda.\nMoltes gràcies per escoltar-me.",
        "temes": ["habitatge", "patrimoni", "barris"],
        "text_cas": "Sr. Oliver: Bueno, pues lo primero, señora presidenta, buenas tardes señoras y señores concejales. Un profundo respeto a todos ustedes, pues la verdad tienen un trabajo bastante difícil. Quiero darle primero las gracias a la Asociación Cultural Falla de la Malvarrosa por darnos esta oportunidad no solo de estar aquí, sino encima de que se nos escuche.\nMi nombre es Miguel Oliver y represento a la Sociedad Marina Auxiliante. Son cientos de familias valencianas que formamos y hemos formado la columna vertebral de los poblados marítimos. Vivimos desde hace décadas bajo la sombra de una profunda inseguridad jurídica. Nuestros hogares, construidos con el esfuerzo de generaciones, se asientan sobre un terreno cuya propiedad es del Ayuntamiento de València. Tenemos una reciente declaración de caducidad de la concesión del 2018 y la confirmación judicial de la propiedad del suelo por parte del Ayuntamiento en abril del 2024. Nos hemos quedado sin nada. Hemos sido sistemáticamente ignorados. Nuestras solicitudes de compra del suelo han caído en un silencio administrativo sepulcral.\nSomos familias honradas, gente trabajadora. Perder nuestros hogares sería una amputación de nuestra propia identidad. Esperamos que se pueda encontrar una solución jurídica definitiva. Es hora de que el Ayuntamiento reconozca el arraigo de nuestras familias y nos permita consolidar la propiedad. Muchísimas gracias por escucharme.\nSr. Estrela: Buenas tardes a todos y a todas. Creo que me queda muy poco tiempo. Voy a cambiar un poco lo que iba a decir y resumirlo. Aquí de lo que se trata ahora es que 40 familias que viven en la Lonja de Pescadores que llevan viviendo más de cien años. Yo soy propietario y lo he heredado de mi abuelo. Fue de los primeros que construyeron la Lonja de Pescadores. ¿En qué situación nos encontramos? Después de la sentencia hay una duda total de qué es lo que va a pasar. El Ayuntamiento todavía no nos ha dicho nada. Lo que queremos es retomar las negociaciones que teníamos abiertas. Las familias tienen mucho miedo e incertidumbre. No es lógico que después de estar viviendo cien años, ahora se encuentren en una situación en que posiblemente les expropien. A unas familias que han estado pagando impuestos, IBI, luz, agua, en una situación normal de vivir.\nPedimos al Ayuntamiento que abra las negociaciones y se pueda llegar a un acuerdo. Es la compra del suelo. Estamos dispuestos a pagarlo, porque el vuelo es nuestro. Las familias tienen mucho miedo. Es gente humilde y gente mayor. Si el día que sea esto se acabara, díganles dónde van a vivir.\nMuchas gracias por escucharme.",
        "text_val": "Sr. Oliver: Bé, doncs el primer de tot, senyora presidenta, bona vesprada senyores i senyors regidors. Un profund respecte a tots vostés, la veritat tenen un treball bastant difícil. Vull donar-li primer les gràcies a l'Associació Cultural Falla de la Malvarrosa per donar-nos esta oportunitat no sols d'estar ací, sinó a més que se'ns escolte.\nEl meu nom és Miguel Oliver i represente la Societat Marina Auxiliant. Són centenars de famílies valencianes que formem i hem format la columna vertebral dels poblats marítims. Vivim des de fa dècades sota l'ombra d'una profunda inseguretat jurídica. Les nostres llars, construïdes amb l'esforç de generacions, s'assenten sobre un terreny la propietat del qual és de l'Ajuntament de València. Tenim una recent declaració de caducitat de la concessió del 2018 i la confirmació judicial de la propietat del sòl per part de l'Ajuntament a l'abril del 2024. Ens hem quedat sense res. Hem sigut sistemàticament ignorats. Les nostres sol·licituds de compra del sòl han caigut en un silenci administratiu sepulcral.\nSom famílies honrades, gent treballadora. Perdre les nostres llars seria una amputació de la nostra pròpia identitat. Esperem que es puga trobar una solució jurídica definitiva. És hora que l'Ajuntament reconega l'arrelament de les nostres famílies i ens permeta consolidar la propietat. Moltíssimes gràcies per escoltar-me.\nSr. Estrela: Bona vesprada a tots i a totes. Crec que em queda molt poc de temps. Vaig a canviar un poc el que anava a dir i resumir-ho. Ací del que es tracta ara és que 40 famílies que viuen en la Llotja de Pescadors que estan vivint més de cent anys. Jo sóc un propietari i ho he heretat del meu iaio. Va ser dels primers que varen construir la Llotja de Pescadors. Ara, en quina situació ens trobem? Després de la sentència n'hi ha un dubte total de què és el que va a passar. L'Ajuntament encara no ens ha dit res. El que volem és reprendre les negociacions. Les famílies tenen molta por i molta incertesa. No és lògic que després d'estar vivint cent anys ara possiblement els expropien.\nDemanem a l'Ajuntament que òbriga les negociacions i es puga arribar a un acord. És la compra del sòl. Estem disposats a pagar-ho, perquè el vol és nostre. Les famílies tenen molta por. És gent humil i gent major. Si el dia que siga això s'acabara, diguen vostés on van a viure.\nMoltes gràcies per escoltar-me.",
        "resum_cas": "Familias de la Lonja de Pescadores piden seguridad jurídica y la compra del suelo donde viven desde hace generaciones, tras perder la concesión y la propiedad judicial del vuelo a favor del Ayuntamiento.",
        "resum_val": "Famílies de la Llotja de Pescadors demanen seguretat jurídica i la compra del sòl on viuen des de fa generacions, després de perdre la concessió i la propietat judicial del vol a favor de l'Ajuntament.",
    },
    {
        "id": "2025-07-22-100",
        "pleno_id": "2025-07-22",
        "ordre": 3,
        "intervinient": "Boutaina El Hadri El Gmili, Nadia Tabib Chouitar",
        "entitat": "Jóvenes hacia la Solidaridad y el Desarrollo / Casa Marruecos",
        "tipus_entitat": "ong",
        "barri_o_zona": "València",
        "punts_ordre_dia": "Discursos de odio",
        "idioma_original": "mixt",
        "text_original": "Sra. El Hadri: Muchas gracias a todos y a todas, buenas tardes. Vinimos aquí en representación de Casa Marruecos y Jovesólides, organizaciones que trabajan por la justicia social, la inclusión y los derechos humanos en nuestra ciudad. Un espacio como este, el Pleno del Ayuntamiento de València, es, debería ser, la casa del pueblo. Vinimos aquí, una vez más, con respeto, pero con una verdad que no se puede seguir ignorando. Ya hemos estado aquí varias veces. Vinimos cuando denunciamos el genocidio en Gaza, volvimos tras los ataques racistas que sufrieron las personas migradas durante la dana. Y cada vez lamentablemente salimos con la misma sensación, decepción. Y, sin embargo, seguimos viniendo, porque seguimos creyendo en la política.\nPero lo que está ocurriendo no se puede seguir escondiendo. No es puntual lo que estamos viviendo muchas personas migradas, especialmente personas marroquíes y musulmanas magrebíes es grave, muy grave. Y está creciendo y se llama racismo, se llama morofobia, se llama islamofobia. Lo que pasó en Torre Pacheco no debería pasar en ningún lugar, pero la verdad es que vemos que podía pasar aquí.\nLa islamofobia y la morofobia son una realidad y lo más preocupante es que ya no se ocultan. Se expresan abiertamente, se difunden en las redes, se repiten en los medios de comunicación y en ocasiones se insinúan desde las instituciones.\nSeñores de Vox, dejen de engañar a la sociedad, no somos una amenaza, no somos delincuentes, no somos un riesgo. Somos parte de este pueblo, somos ciudadanas, somos personas. Sin las personas migrantes este país y esta ciudad no se sostienen. Estamos aquí y no nos vamos a ir. Somos casi el 20 % de la sociedad valenciana.\nSeñora alcaldesa, en campaña nos reunimos con usted. Le preguntamos si iba a pactar con la ultraderecha, si iba a protegernos de los discursos de odio. Usted dijo que sí, que gobernaría para todas las personas. Hoy, con tristeza lo decimos: no nos sentimos protegidas. El discurso tiene consecuencias. Cuando se siembra la sospecha, se está legitimando el miedo, el rechazo y la violencia. Si no hay una postura clara, si se sigue tolerando el relato del odio, puede que pase una tragedia.\nSra. Tabib: Sí, és curtet. Bona vesprada. Jo vaig nàixer ací, sóc valenciana i estic orgullosa. Però també sóc mora i orgullosa. I no vull eixir pel carrer amb por per portar un hijab. No vull tindre por per ser qui sóc. Em negue a viure amb por. Cada dia lluite contra això, per mi, per la meua mare, pel meu germà menut, per les meues veïnes, per les meues amigues, per totes vosaltres.\nPerò no hauria de ser la meua lluita. Eixa és la vostra responsabilitat, protegir-nos i assegurar-vos que cap persona com jo haja d'aprendre a resistir només per existir. Perquè tindre por per ser un mateix no hauria de formar part de créixer en aquesta ciutat. Per això hui exigim: Que es reconega de manera pública l'augment de la islamofòbia, morofòbia i racisme a la nostra ciutat. Que es condemne sense ambigüitats qualsevol discurs que vincule immigració amb delinqüència. Que es desenvolupen polítiques valentes d'inclusió social i convivència real. Que es protegisca a qui viu amb por i no s'atreveix a denunciar. Que es defensen amb claredat els drets humans, no com a consigna sinó com a pràctica institucional.\nVolem viure sense por. Volem caminar pels nostres carrers sense mirades sospitoses. Volem poder parlar, vestir, resar, viure, sense haver de justificar la nostra existència. Estem ací, seguirem ací i no ens callarem, perquè el silenci no ens protegeix, perquè la por no ens paralitza, perquè la dignitat no es negocia.\nDes de València, amb veu ferma diem: stop morofòbia, stop islamofòbia, stop racisme. Moltes gràcies.",
        "temes": ["igualtat", "participacio_ciutadana", "seguretat"],
        "text_cas": "Sra. El Hadri: Muchas gracias a todos y a todas, buenas tardes. Vinimos aquí en representación de Casa Marruecos y Jovesólides, organizaciones que trabajan por la justicia social, la inclusión y los derechos humanos en nuestra ciudad. Vinimos aquí, una vez más, con respeto, pero con una verdad que no se puede seguir ignorando. Ya hemos estado aquí varias veces. Vinimos cuando denunciamos el genocidio en Gaza, volvimos tras los ataques racistas que sufrieron las personas migradas durante la dana. Y cada vez salimos con la misma sensación, decepción.\nPero lo que está ocurriendo no se puede seguir escondiendo. Lo que estamos viviendo muchas personas migradas, especialmente personas marroquíes y musulmanas magrebíes, es grave, muy grave. Y está creciendo y se llama racismo, morofobia, islamofobia.\nLa islamofobia y la morofobia ya no se ocultan. Se expresan abiertamente, se difunden en las redes y en ocasiones se insinúan desde las instituciones. Señores de Vox, dejen de engañar a la sociedad. Somos parte de este pueblo. Sin las personas migrantes este país no se sostiene. Somos casi el 20 % de la sociedad valenciana.\nSeñora alcaldesa, en campaña nos reunimos con usted. Le preguntamos si iba a pactar con la ultraderecha. Usted dijo que gobernaría para todas las personas. Hoy no nos sentimos protegidas. El discurso tiene consecuencias. Si se sigue tolerando el relato del odio, puede que pase una tragedia.\nSra. Tabib: Sí, es cortito. Buenas tardes. Yo nací aquí, soy valenciana y estoy orgullosa. Pero también soy mora y orgullosa. Y no quiero salir por la calle con miedo por llevar un hijab. No quiero tener miedo por ser quien soy. Me niego a vivir con miedo. Cada día lucho contra eso, por mí, por mi madre, por mi hermano pequeño, por mis vecinas, por mis amigas, por todas vosotras.\nPero no debería ser mi lucha. Esa es vuestra responsabilidad, protegernos y aseguraros de que ninguna persona como yo tenga que aprender a resistir solo por existir. Por eso hoy exigimos: Que se reconozca de manera pública el aumento de la islamofobia, morofobia y racismo. Que se condene sin ambigüedades cualquier discurso que vincule inmigración con delincuencia. Que se desarrollen políticas valientes de inclusión social y convivencia real. Que se proteja a quien vive con miedo. Que se defiendan con claridad los derechos humanos.\nQueremos vivir sin miedo. Queremos caminar por nuestras calles sin miradas sospechosas. Estamos aquí, seguiremos aquí y no nos callaremos. Desde València decimos: stop morofobia, stop islamofobia, stop racismo. Muchas gracias.",
        "text_val": "Sra. El Hadri: Moltes gràcies a tots i a totes, bona vesprada. Vam vindre ací en representació de Casa Marroc i Jovesòlides, organitzacions que treballen per la justícia social, la inclusió i els drets humans a la nostra ciutat. Vam vindre ací, una vegada més, amb respecte, però amb una veritat que no es pot seguir ignorant. Ja hem estat ací diverses vegades. Vam vindre quan vam denunciar el genocidi a Gaza, vam tornar després dels atacs racistes que van patir les persones migrades durant la dana. I cada vegada eixim amb la mateixa sensació, decepció.\nPerò el que està ocorrent no es pot seguir amagant. El que estem vivint moltes persones migrades, especialment persones marroquines i musulmanes magrebines, és greu, molt greu. I està creixent i es diu racisme, morofòbia, islamofòbia.\nLa islamofòbia i la morofòbia ja no s'amaguen. S'expressen obertament, es difonen a les xarxes i de vegades s'insinuen des de les institucions. Senyors de Vox, deixen d'enganyar la societat. Som part d'este poble. Sense les persones migrants este país no es sosté. Som quasi el 20 % de la societat valenciana.\nSenyora alcaldessa, en campanya ens vam reunir amb vosté. Li vam preguntar si anava a pactar amb la ultradreta. Vosté va dir que governaria per a totes les persones. Hui no ens sentim protegides. El discurs té conseqüències. Si es segueix tolerant el relat de l'odi, pot passar una tragèdia.\nSra. Tabib: Sí, és curtet. Bona vesprada. Jo vaig nàixer ací, sóc valenciana i estic orgullosa. Però també sóc mora i orgullosa. I no vull eixir pel carrer amb por per portar un hijab. No vull tindre por per ser qui sóc. Em negue a viure amb por. Cada dia lluite contra això, per mi, per la meua mare, pel meu germà menut, per les meues veïnes, per les meues amigues, per totes vosaltres.\nPerò no hauria de ser la meua lluita. Eixa és la vostra responsabilitat, protegir-nos i assegurar-vos que cap persona com jo haja d'aprendre a resistir només per existir. Per això hui exigim: Que es reconega de manera pública l'augment de la islamofòbia, morofòbia i racisme. Que es condemne sense ambigüitats qualsevol discurs que vincule immigració amb delinqüència. Que es desenvolupen polítiques valentes d'inclusió social i convivència real. Que es protegisca a qui viu amb por. Que es defensen amb claredat els drets humans.\nVolem viure sense por. Volem caminar pels nostres carrers sense mirades sospitoses. Estem ací, seguirem ací i no ens callarem. Des de València diem: stop morofòbia, stop islamofòbia, stop racisme. Moltes gràcies.",
        "resum_cas": "Denuncian el aumento del racismo, la morofobia y la islamofobia en València. El Hadri recuerda a la alcaldesa su promesa de gobernar para todas las personas. Tabib, joven valenciana de origen marroquí, exige no tener que vivir con miedo por llevar hijab.",
        "resum_val": "Denuncien l'augment del racisme, la morofòbia i la islamofòbia a València. El Hadri recorda a l'alcaldessa la seua promesa de governar per a totes les persones. Tabib, jove valenciana d'origen marroquí, exigeix no haver de viure amb por per portar hijab.",
    },
    # ── 2025-09-11: Orriols en Lucha joint intervention (Martinez Escot + Cebral Olcina) ──
    {
        "id": "2025-09-11-028",
        "pleno_id": "2025-09-11",
        "ordre": 28,
        "intervinient": "Pilar Martinez Escot, Sergio Cebral Olcina",
        "entitat": "Asociación Plataforma Orriols en Lucha",
        "tipus_entitat": "plataforma",
        "barri_o_zona": "Orriols",
        "punts_ordre_dia": "Debate sobre el estado de la ciudad",
        "idioma_original": "castellano",
        "text_original": "Sra. Martinez: Buenas tardes a todos y todas.\nSeñora alcaldesa, señoras y señores concejales, esperamos que hayan disfrutado de sus vacaciones. Decirles que nos ha sorprendido la precipitación en la convocatoria del debate sobre el estado de la ciudad. Y como es un tema que nos afecta tanto, no hemos querido dejar pasar la oportunidad de manifestar nuestra preocupación. Desgraciadamente, desde Orriols no tenemos una visión tan positiva. En Orriols en Lucha nos hemos aferrado a la esperanza. Creemos que es una actitud activa que se dirige a la búsqueda de metas específicas con la idea de conseguir un futuro mejor, a pesar de las dificultades y asumiendo responsabilidades que nos restan tiempo y disfrute de la vida.\nEn contraste, parece que el optimismo de este gobierno va más enfocado a la creencia pasiva de que todo saldrá bien en general, sin que necesariamente haya que ejercer alguna acción. Esta creencia puede llevar a la frustración a los ciudadanos porque no se cumplen los compromisos adquiridos.\nEn la asamblea del miércoles 3 de septiembre, con participación de vecinos, vecinas y asociaciones de Orriols, hicimos análisis de la situación del barrio y de los hechos que hemos vivido este verano. Queremos transmitirle la profunda preocupación y en muchos casos indignación que sentimos. La impotencia que transmitían los más afectados.\nEn algunas zonas del barrio sigue produciéndose ocupación masiva del espacio público, en muchos casos por parte de personas incívicas que consumen alcohol y sustancias estupefacientes. Dejan cantidad de basura a su alrededor y no permiten el descanso a los vecinos. Hay venta de alcohol hasta altas horas de la madrugada, incluso desde algún domicilio particular. Los vecinos llaman repetidas veces a la Policía Local, que por la noche no aparece. Se permite el aparcamiento y la circulación en zonas peatonalizadas e incluso encima de las aceras, sin ningún respeto por los peatones y sin que apreciemos actuaciones policiales. Hemos observado la presencia de adolescentes y jóvenes sin ningún tipo de control que se dedican a actividades ilícitas. Desafortunadamente, en Orriols no contamos con actividades culturales y sociosaludables que puedan interesar a esta población, algo muy necesario dadas las características del barrio. La vulnerabilidad y la marginalidad es mucha y en nuestra opinión sigue en aumento.\nSr. Cebral: Buenas tardes a todas y a todos.\nVemos que no avanzamos en ninguno de nuestros proyectos y por ello se los vamos a recordar. Sabemos que les suenan, pero ante la falta de soluciones nuestra repetición. El polideportivo un año después de su cierre sigue igual, cerrado. Esperamos que la ansiada reparación de la cubierta llegue pronto. En cuanto a la biblioteca, después de la última reunión que tuvimos con usted, señora alcaldesa, se nos prometió una solución que hoy en día ya no es posible. Vemos que la nueva solución es la reparación de la alquería. ¿Cuánto tiempo se tarda en reparar una alquería? ¿Se ha comenzado ya con ese plan de redacción?\nLos servicios sociales también son un tema candente en Orriols. Están colapsados. Prometieron un centro de servicios sociales exclusivo para Orriols, disponible en 2024. Y ahora parece que no existe. Tardará años, si es que llega. Seguimos esperando la plantación de 130 árboles, pendiente desde hace años de que llegue un informe. ¿Dónde está ese informe de Patrimonio? Cuando se tiene interés por agilizar algo, se agiliza, se tira para adelante, se agilizan todos esos trámites. Parece que en este caso no se tiene interés. No tenemos noticias de la remodelación de la plaza de Esteban Dolz. Las calles continúan sucias y llenas de trastos. Estamos cansados de decir que tiene que haber intervenciones de otro tipo, además de la limpieza.\nEs necesario educar y concienciar. Las campañas en redes sociales pueden ser útiles, pero creemos que no sirven exclusivamente para combatir el incivismo que padecemos en Orriols. Mientras personas problemáticas siguen ocupando viviendas, algunas de nuestras buenas familias se les sigue expulsando de sus pisos por el abusivo precio de los alquileres. Eso, señora alcaldesa, es clase media y economía familiar. Y en efecto, sin clase media y economía no hay cohesión ni democracia.\nComo llevamos repitiendo desde hace años, nuestro barrio necesita de intervenciones integrales: urbanísticas, sociales, culturales. Si de verdad queremos que Orriols sea un barrio habitable a la altura de nuestra ciudad y de las personas que lo habitamos, tenemos, tienen que tomárselo en serio. No se puede poner tiritas donde hace falta quirófano. Es por todo eso que seguimos reivindicando las mesas interconcejalías como elemento necesario. Los concejales y concejalas están al servicio de la ciudadanía y no al revés. Necesitamos que esta herramienta sea útil para avanzar en la resolución de los problemas de Orriols. Desde Orriols en Lucha aportamos la colaboración para poder trabajar conjuntamente, pero también exigimos seriedad y máxima contundencia en las acciones para la mejora de nuestro barrio. Como todos y todas sabemos, los entornos pueden modificar los comportamientos y la vida de las personas.\nMuchas gracias.",
        "temes": ["seguretat", "barris", "participacio_ciutadana", "joventut", "cultura", "serveis_socials", "infraestructures", "habitatge"],
        "text_cas": "",
        "text_val": "Sra. Martinez: Bona vesprada a tots i totes.\nSenyora alcaldessa, senyores i senyors regidors, esperem que hagen gaudit de les seues vacances. Dir-los que ens ha sorprés la precipitació en la convocatòria del debat sobre l'estat de la ciutat. I com és un tema que ens afecta tant, no hem volgut deixar passar l'oportunitat de manifestar la nostra preocupació. Desgraciadament, des d'Orriols no tenim una visió tan positiva. A Orriols en Lluita ens hem aferrat a l'esperança. Creiem que és una actitud activa que es dirigeix a la cerca de metes específiques amb la idea d'aconseguir un futur millor, malgrat les dificultats i assumint responsabilitats que ens resten temps i gaudi de la vida.\nEn contrast, sembla que l'optimisme d'este govern va més enfocat a la creença passiva que tot eixirà bé en general, sense que necessàriament s'haja d'exercir alguna acció. Esta creença pot portar a la frustració als ciutadans perquè no es complixen els compromisos adquirits.\nA l'assemblea del dimecres 3 de setembre, amb participació de veïns, veïnes i associacions d'Orriols, vam fer anàlisi de la situació del barri i dels fets que hem viscut este estiu. Volem transmetre-li la profunda preocupació i en molts casos indignació que sentim. La impotència que transmetien els més afectats.\nEn algunes zones del barri continua produint-se ocupació massiva de l'espai públic, en molts casos per part de persones incíviques que consumixen alcohol i substàncies estupefaents. Deixen quantitat de fem al seu voltant i no permeten el descans als veïns. Hi ha venda d'alcohol fins a altes hores de la matinada, inclús des d'algun domicili particular. Els veïns criden repetides vegades a la Policia Local, que de nit no apareix. Es permet l'estacionament i la circulació en zones per a vianants i inclús damunt de les voreres, sense cap respecte pels vianants i sense que apreciem actuacions policials. Hem observat la presència d'adolescents i joves sense cap tipus de control que es dediquen a activitats il·lícites. Desafortunadament, a Orriols no comptem amb activitats culturals i sociosaludables que puguen interessar esta població, alguna cosa molt necessària donades les característiques del barri. La vulnerabilitat i la marginalitat és molta i en la nostra opinió continua en augment.\nSr. Cebral: Bona vesprada a totes i a tots.\nVeiem que no avancem en cap dels nostres projectes i per això els els recordarem. Sabem que els sonen, però davant la falta de solucions la nostra repetició. El poliesportiu un any després del seu tancament seguix igual, tancat. Esperem que l'ansiada reparació de la coberta arribe prompte. Quant a la biblioteca, després de l'última reunió que vam tindre amb vosté, senyora alcaldessa, se'ns va prometre una solució que hui en dia ja no és possible. Veiem que la nova solució és la reparació de l'alqueria. Quant de temps es tarda a reparar una alqueria? S'ha començat ja amb eixe pla de redacció?\nEls servicis socials també són un tema candent a Orriols. Estan col·lapsats. Van prometre un centre de servicis socials exclusiu per a Orriols, disponible en 2024. I ara sembla que no existix. Tardarà anys, si és que arriba. Continuem esperant la plantació de 130 arbres, pendent des de fa anys que arribe un informe. On està eixe informe de Patrimoni? Quan es té interés per agilitzar alguna cosa, s'agilitza, es tira avant, s'agilitzen tots eixos tràmits. Sembla que en este cas no es té interés. No tenim notícies de la remodelació de la plaça d'Esteban Dolz. Els carrers continuen bruts i plens de trastos. Estem cansats de dir que ha d'haver-hi intervencions d'un altre tipus, a més de la neteja.\nÉs necessari educar i conscienciar. Les campanyes en xarxes socials poden ser útils, però creiem que no servixen exclusivament per a combatre l'incivisme que patim a Orriols. Mentre persones problemàtiques continuen ocupant habitatges, a algunes de les nostres bones famílies se les continua expulsant dels seus pisos pel preu abusiu dels lloguers. Això, senyora alcaldessa, és classe mitjana i economia familiar. I en efecte, sense classe mitjana i economia no hi ha cohesió ni democràcia.\nCom portem repetint des de fa anys, el nostre barri necessita intervencions integrals: urbanístiques, socials, culturals. Si de veritat volem que Orriols siga un barri habitable a l'altura de la nostra ciutat i de les persones que l'habitem, tenen que prendre-s'ho seriosament. No es poden posar tirites on fa falta quiròfan. És per tot això que continuem reivindicant les taules interconcejalia com a element necessari. Els regidors i regidores estan al servici de la ciutadania i no al revés. Necessitem que esta ferramenta siga útil per a avançar en la resolució dels problemes d'Orriols. Des d'Orriols en Lluita aportem la col·laboració per a poder treballar conjuntament, però també exigim serietat i màxima contundència en les accions per a la millora del nostre barri. Com tots i totes sabem, els entorns poden modificar els comportaments i la vida de les persones.\nMoltes gràcies.",
        "resum_cas": "Orriols en Lucha denuncia la ocupación masiva del espacio público, el consumo de alcohol y drogas, y la falta de vigilancia policial en el barrio. Reclaman el polideportivo cerrado, la biblioteca prometida, servicios sociales colapsados, la plantación de 130 árboles y mesas interconcejalías para abordar los problemas de forma integral.",
        "resum_val": "Orriols en Lluita denuncia l'ocupació massiva de l'espai públic, el consum d'alcohol i drogues, i la falta de vigilància policial al barri. Reclamen el poliesportiu tancat, la biblioteca promesa, servicis socials col·lapsats, la plantació de 130 arbres i taules interconcejalia per a abordar els problemes de forma integral.",
    },
]

# Insert manual interventions or update existing ones
_existing_idx = {iv.get("id", ""): i for i, iv in enumerate(interventions)}
for miv in MANUAL_INTERVENTIONS:
    if miv["id"] not in _existing_idx:
        interventions.append(miv)
        print(f"  MANUAL INSERT: {miv['id']} {miv['intervinient']} ({miv['entitat']})")
    else:
        # Update existing entry with all fields from manual definition
        idx = _existing_idx[miv["id"]]
        interventions[idx].update(miv)
        print(f"  MANUAL UPDATE: {miv['id']} {miv['intervinient']} ({miv['entitat']})")

# ─── 6. TEXT MERGES — split speeches that should be one intervention ────────
# base_id keeps its metadata; text from merge_ids is appended in order.
# merge_ids are then deleted.
IV_TEXT_MERGES = [
    {
        "base_id": "2024-09-16-1-005",
        "merge_ids": ["2024-09-16-1-006", "2024-09-16-1-007"],
    },
    {
        "base_id": "2024-09-16-1-017",
        "merge_ids": ["2024-09-16-1-020"],
    },
    {
        "base_id": "2025-04-11-3-001",
        "merge_ids": ["2025-04-11-3-002", "2025-04-11-3-003", "2025-04-11-3-004"],
    },
]

# ─────────────────────────────────────────────────────────────────────────────

# Resolve merge_from entity IDs from match_texts via variant_map
for m in MERGES:
    found_ids = set()
    for text in m["match_texts"]:
        eid = variant_map.get(text.lower().strip())
        if eid:
            found_ids.add(eid)
    # Remove excluded entity IDs
    excluded_ids = set()
    for text in m.get("exclude_texts", []):
        eid = variant_map.get(text.lower().strip())
        if eid:
            excluded_ids.add(eid)
    m["_merge_from_ids"] = found_ids - excluded_ids
    if not found_ids:
        print(f"  WARNING: No entity IDs found for merge group '{m['canonical_id']}'")

# Build old_id → canonical_id remap
id_remap = {}
for m in MERGES:
    for old_id in m["_merge_from_ids"]:
        id_remap[old_id] = m["canonical_id"]

print(f"Built id_remap with {len(id_remap)} entries")

# Build new entities from merges
new_entities = {}
for m in MERGES:
    cid = m["canonical_id"]
    new_entities[cid] = {
        "id": cid,
        "nom_cas": m["nom_cas"],
        "nom_val": m["nom_val"],
        "tipus": m["tipus"],
        "variants": [],  # will be built from actual intervention texts
        "num_intervencions": 0,
        "barri": None,
        "temes_principals": [],
    }

# Copy unchanged entities (not in any merge group, not deleted)
merged_old_ids = set(id_remap.keys()) | {m["canonical_id"] for m in MERGES}
for eid, entity in entities.items():
    if eid not in merged_old_ids and eid not in DELETE_ENTITY_IDS:
        new_entities[eid] = entity

# Add newly created entities for re-attributed floors
new_entities["colectivo-fuera-tunel"] = {
    "id": "colectivo-fuera-tunel",
    "nom_cas": "Colectivo Fuera Túnel",
    "nom_val": "Col·lectiu Fora Túnel",
    "tipus": "plataforma",
    "variants": ["Colectivo Fuera Túnel"],
    "num_intervencions": 0, "barri": None, "temes_principals": [],
}
new_entities["av-cabanyal-canyamelar"] = {
    "id": "av-cabanyal-canyamelar",
    "nom_cas": "Asociación de Vecinos y Vecinas del Cabanyal-Canyamelar",
    "nom_val": "Associació de Veïns i Veïnes del Cabanyal-Canyamelar",
    "tipus": "av",
    "variants": ["Associació de Veïns i Veïnes del Cabanyal-Canyamelar"],
    "num_intervencions": 0, "barri": None, "temes_principals": [],
}
new_entities["asociacion-intercultural-mundo-solidario"] = {
    "id": "asociacion-intercultural-mundo-solidario",
    "nom_cas": "Asociación Intercultural Mundo Solidario",
    "nom_val": "Associació Intercultural Món Solidari",
    "tipus": "ong",
    "variants": ["Asociación Intercultural Mundo Solidario"],
    "num_intervencions": 0, "barri": None, "temes_principals": [],
}
new_entities["acdesa"] = {
    "id": "acdesa",
    "nom_cas": "Asociación Ciudadana para la Defensa de la Sanidad Pública del País Valencià (ACDESA)",
    "nom_val": "Associació Ciutadana per a la Defensa de la Sanitat Pública del País Valencià (ACDESA)",
    "tipus": "plataforma",
    "variants": ["ACDESA"],
    "num_intervencions": 0, "barri": None, "temes_principals": [],
}
new_entities.setdefault("asociacion-tdah-mas-16", {
    "id": "asociacion-tdah-mas-16",
    "nom_cas": "Asociación TDAH MAS 16 València",
    "nom_val": "Associació TDAH MAS 16 València",
    "tipus": "ong",
    "variants": ["Asociación TDAH MAS 16 València"],
    "num_intervencions": 0, "barri": None, "temes_principals": [],
})
new_entities["associacio-cultural-consumidors-patraix"] = {
    "id": "associacio-cultural-consumidors-patraix",
    "nom_cas": "Asociación Cultural y de Consumidores Patraix",
    "nom_val": "Associació Cultural i de Consumidors Patraix",
    "tipus": "cultural",
    "variants": ["Associació Cultural i de Consumidors Patraix"],
    "num_intervencions": 0, "barri": None, "temes_principals": [],
}
new_entities["avv-sant-marcelli"] = {
    "id": "avv-sant-marcelli",
    "nom_cas": "Asociación de Vecinos y Vecinas de Sant Marcel·lí",
    "nom_val": "Associació de Veïns i Veïnes de Sant Marcel·lí",
    "tipus": "av",
    "variants": ["AVV de Sant Marcel·lí"],
    "num_intervencions": 0, "barri": None, "temes_principals": [],
}
new_entities["caritas-diocesana"] = {
    "id": "caritas-diocesana",
    "nom_cas": "Cáritas Diocesana",
    "nom_val": "Càritas Diocesana",
    "tipus": "ong",
    "variants": ["Cáritas Diocesana"],
    "num_intervencions": 0, "barri": None, "temes_principals": [],
}
new_entities["asociacion-cruces-mayo-la-torre"] = {
    "id": "asociacion-cruces-mayo-la-torre",
    "nom_cas": "Asociación Cultural Cruces de Mayo La Torre",
    "nom_val": "Associació Cultural Creus de Maig La Torre",
    "tipus": "cultural",
    "variants": ["Asociación Cultural Cruces de Mayo La Torre"],
    "num_intervencions": 0, "barri": None, "temes_principals": [],
}
new_entities["sta-intersindical"] = {
    "id": "sta-intersindical",
    "nom_cas": "STA-Intersindical",
    "nom_val": "STA-Intersindical",
    "tipus": "sindical",
    "variants": ["STA-Intersindical"],
    "num_intervencions": 0, "barri": None, "temes_principals": [],
}
new_entities["san-juan-de-dios-servicios-sociales"] = {
    "id": "san-juan-de-dios-servicios-sociales",
    "nom_cas": "San Juan de Dios-Servicios Sociales",
    "nom_val": "San Joan de Déu-Serveis Socials",
    "tipus": "ong",
    "variants": ["San Juan de Dios-Servicios Sociales"],
    "num_intervencions": 0, "barri": None, "temes_principals": [],
}

# ─── Apply text merges (concatenate split speeches) ──────────────────────────
_iv_by_id = {iv.get("id", ""): iv for iv in interventions}
_merge_delete = set()
for tm in IV_TEXT_MERGES:
    base = _iv_by_id.get(tm["base_id"])
    if not base:
        print(f"  WARNING: merge base {tm['base_id']} not found")
        continue
    for mid in tm["merge_ids"]:
        src = _iv_by_id.get(mid)
        if not src:
            print(f"  WARNING: merge source {mid} not found")
            continue
        for field in ("text_cas", "text_val"):
            base_text = base.get(field) or ""
            src_text = src.get(field) or ""
            if src_text:
                base[field] = base_text + "\n" + src_text if base_text else src_text
        # Merge temes
        base_temes = set(base.get("temes") or [])
        base_temes.update(src.get("temes") or [])
        base["temes"] = sorted(base_temes)
        _merge_delete.add(mid)
        print(f"  TEXT_MERGE: {mid} -> {tm['base_id']}")
DELETE_IV_IDS.update(_merge_delete)

# Update interventions
new_interventions = []
for iv in interventions:
    iv_id = iv.get("id", "")

    if iv_id in DELETE_IV_IDS:
        print(f"  DELETE: {iv_id}")
        continue

    current_entitat = iv.get("entitat") or ""
    current_eid = text_to_eid(current_entitat)

    if current_eid in DELETE_ENTITY_IDS:
        print(f"  DELETE (spurious entity {current_eid}): {iv_id}")
        continue

    iv = dict(iv)

    # Apply field patches (name/entity corrections)
    if iv_id in IV_PATCHES:
        for field, value in IV_PATCHES[iv_id].items():
            old_val = iv.get(field, "")
            iv[field] = value
            print(f"  PATCH: {iv_id} {field}: {repr(old_val)} -> {repr(value)}")

    if iv_id in REASSIGN:
        new_entitat, canonical_eid = REASSIGN[iv_id]
        iv["entitat"] = new_entitat
        iv["_eid"] = canonical_eid
        print(f"  REASSIGN: {iv_id} -> {canonical_eid}")
    else:
        canonical_eid = id_remap.get(current_eid, current_eid)
        iv["_eid"] = canonical_eid

    new_interventions.append(iv)

# Recount using _eid
counts = defaultdict(int)
for iv in new_interventions:
    eid = iv.get("_eid") or ""
    if eid and eid != "desconegut":
        counts[eid] += 1

for eid in new_entities:
    new_entities[eid]["num_intervencions"] = counts.get(eid, 0)

# Keep only entities with interventions (except always-kept)
KEEP_ALWAYS = {"colectivo-fuera-tunel", "acdesa"}
final_entities = [e for e in new_entities.values()
                  if e["num_intervencions"] > 0 or e["id"] in KEEP_ALWAYS]
final_entities.sort(key=lambda e: -e["num_intervencions"])

# Build variant_map AND variants field from actual intervention texts (ground truth)
new_variant_map = {}
entity_actual_texts = defaultdict(set)
for iv in new_interventions:
    entitat = iv.get("entitat") or ""
    eid = iv.get("_eid") or ""
    if entitat and eid and eid != "desconegut":
        new_variant_map[entitat.lower().strip()] = eid
        entity_actual_texts[eid].add(entitat)
for entity in final_entities:
    new_variant_map.setdefault(entity["nom_cas"].lower().strip(), entity["id"])
    new_variant_map.setdefault(entity["nom_val"].lower().strip(), entity["id"])
    entity["variants"] = sorted(entity_actual_texts.get(entity["id"], set()))

# Remove temporary field before saving
for iv in new_interventions:
    iv.pop("_eid", None)

# Verify
entity_ids = {e["id"] for e in final_entities}
orphaned = set()
for iv in new_interventions:
    eid = new_variant_map.get((iv.get("entitat") or "").lower().strip())
    if eid and eid not in entity_ids and eid != "desconegut":
        orphaned.add(eid)

INTERVENTIONS_FILE.write_text(json.dumps(new_interventions, ensure_ascii=False, indent=2))
ENTITIES_FILE.write_text(json.dumps(final_entities, ensure_ascii=False, indent=2))
VARIANT_MAP_FILE.write_text(json.dumps(new_variant_map, ensure_ascii=False, indent=2))

print(f"\n=== Done ===")
print(f"  Interventions: {len(interventions)} -> {len(new_interventions)}")
print(f"  Entities: {len(entities)} -> {len(final_entities)}")
if orphaned:
    print(f"  WARNING orphaned entity_ids: {orphaned}")
else:
    print("  All entity_ids resolved OK")

print(f"\nTop 10 entities:")
for e in final_entities[:10]:
    print(f"  {e['num_intervencions']:3d}  {e['id']}")
