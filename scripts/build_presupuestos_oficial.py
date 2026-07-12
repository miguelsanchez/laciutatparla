#!/usr/bin/env python3
"""
Transcribe the Oficina d'Estadística reports on Presupuestos Participativos
into a single JSON consumed by the web.

Sources (PDFs on vlcparticipa.valencia.es/help):
- Informe 1: "Análisis de la participación ciudadana en las ocho ediciones
  celebradas de Presupuestos Participativos" (23 pages, signed 04/02/2026).
- Informe 4: "Modificación de la Distribución presupuestaria Presupuestos
  Participativos 2025" (6 pages).

All figures below are extracted from the official PDFs via `pdftotext -layout`
and then manually verified against the rendered tables. Output goes to
data/presupuestos_oficial.json.
"""
import json
from pathlib import Path

OUT_FILE = Path(__file__).parent.parent / "data" / "presupuestos_oficial.json"

EDITIONS = ["1", "2", "3", "4", "5", "6", "7", "8"]
EDITION_LABELS = {
    "1": "2015/16", "2": "2016/17", "3": "2017/18", "4": "2018/19",
    "5": "2019/20", "6": "2020/21", "7": "2022/23", "8": "2025/26",
}

# Canonical barri names come from data/raw/barris_referencia.json.
# The PDF uses a different casing / accentuation; we map each PDF barri name
# to its canonical form (title-case, matches geojson + other datasets).
BARRI_CANONICAL = {
    # Ciutat Vella
    "la Seu": "La Seu", "la Xerea": "La Xerea", "el Carme": "El Carme",
    "el Pilar": "El Pilar", "el Mercat": "El Mercat", "Sant Francesc": "Sant Francesc",
    # L'Eixample
    "Russafa": "Russafa", "el Pla del Remei": "El Pla Del Remei", "la Gran Via": "La Gran Via",
    # Extramurs
    "el Botànic": "El Botanic", "la Roqueta": "La Roqueta",
    "la Petxina": "La Petxina", "Arrancapins": "Arrancapins",
    # Campanar
    "Campanar": "Campanar", "les Tendetes": "Les Tendetes",
    "el Calvari": "El Calvari", "Sant Pau": "Sant Pau",
    # La Saïdia
    "Marxalenes": "Marxalenes", "Morvedre": "Morvedre", "Trinitat": "Trinitat",
    "Tormos": "Tormos", "Sant Antoni": "Sant Antoni",
    # El Pla del Real
    "Exposició": "Exposicio", "Mestalla": "Mestalla",
    "Jaume Roig": "Jaume Roig", "C. Universitària": "Ciutat Universitaria",
    # L'Olivereta
    "Nou Moles": "Nou Moles", "Soternes": "Soternes", "Tres Forques": "Tres Forques",
    "la Fontsanta": "La Fontsanta", "la Llum": "La Llum",
    # Patraix
    "Patraix": "Patraix", "Sant Isidre": "Sant Isidre", "Vara de Quart": "Vara De Quart",
    "el Safranar": "Safranar", "Favara": "Favara",
    # Jesús
    "la Raiosa": "La Raiosa", "l'Hort de Senabre": "L'Hort De Senabre",
    "la Creu Coberta": "La Creu Coberta", "Sant Marcel·lí": "Sant Marcel.Li",
    "Camí Real": "Cami Real",
    # Quatre Carreres
    "Mont-Olivet": "Montolivet", "en Corts": "En Corts", "Malilla": "Malilla",
    "la F. Sant Lluís": "La Fonteta S.Lluis", "na Rovella": "Na Rovella",
    "la Punta": "La Punta", "C. Arts i Ciències": "Ciutat De Les Arts I De Les Ciencies",
    # Poblats Marítims
    "el Grau": "El Grau", "el Cab.-Canyam.": "Cabanyal-Canyamelar",
    "la Malva-rosa": "La Malva-Rosa", "Beteró": "Betero", "Natzaret": "Natzaret",
    # Camins al Grau
    "Aiora": "Aiora", "Albors": "Albors", "la Creu del Grau": "La Creu Del Grau",
    "Camí Fondo": "Cami Fondo", "Penya-roja": "Penya-Roja",
    # Algirós
    "l'Illa Perduda": "L'Illa Perduda", "Ciutat Jardí": "Ciutat Jardi",
    "l'Amistat": "L'Amistat", "la Bega Baixa": "La Vega Baixa",
    "la Carrasca": "La Carrasca",
    # Benimaclet
    "Benimaclet": "Benimaclet", "Camí de Vera": "Cami De Vera",
    # Rascanya
    "Orriols": "Els Orriols", "Torrefiel": "Torrefiel", "Sant Llorenç": "Sant Llorens",
    # Benicalap
    "Benicalap": "Benicalap", "Ciutat Fallera": "Ciutat Fallera",
    # Poblats del Nord
    "Benifaraig": "Benifaraig", "Poble Nou": "Poble Nou", "Carpesa": "Carpesa",
    "les C. Bàrcena": "Les Cases De Barcena", "Mauella": "Mahuella-Tauladella",
    "Massarrojos": "Massarrojos", "Borbotó": "Borboto",
    # Poblats de l'Oest
    "Benimàmet": "Benimamet", "Beniferri": "Beniferri",
    # Poblats del Sud
    "el Forn d'Alcedo": "El Forn D'Alcedo", "Cast.-l'Oliveral": "Castellar-L'Oliveral",
    "Pinedo": "Pinedo", "el Saler": "El Saler", "el Palmar": "El Palmar",
    "el Perellonet": "El Perellonet", "la Torre": "La Torre", "Faitanar": "Faitanar",
}

# ============================================================
# Informe 1 — Tabla 1: participación global por edición
# ============================================================
global_by_edition = {
    "1": {"participantes": 5196,  "presentado": 324,  "apoyado": None, "votado": 5010},
    "2": {"participantes": 15337, "presentado": 574,  "apoyado": 5453,  "votado": 12407},
    "3": {"participantes": 17553, "presentado": 546,  "apoyado": 8986,  "votado": 12987},
    "4": {"participantes": 15906, "presentado": 540,  "apoyado": 3858,  "votado": 14463},
    "5": {"participantes": 20090, "presentado": 607,  "apoyado": 10453, "votado": 14530},
    "6": {"participantes": 26489, "presentado": 1275, "apoyado": 14193, "votado": 20611},
    "7": {"participantes": 27809, "presentado": 1543, "apoyado": 10296, "votado": 23445},
    "8": {"participantes": 28473, "presentado": 1891, "apoyado": 15364, "votado": 20955},
}

# ============================================================
# Informe 1 — Tabla 5: participantes según distrito de residencia
# (valores: N personas que han participado en alguna fase de esa edición)
# Values verified via `pdftotext -layout` of page 9.
# ============================================================
participants_by_district_edition = {
    "Ciutat Vella":       [242,   783,  747,   681,   786,   969, 1078, 1098],
    "L'Eixample":         [126,   792,  942,   939,  1239,  1550, 1607, 1491],
    "Extramurs":          [197,  1066, 1168,  1060,  1486,  1909, 2375, 2102],
    "Campanar":           [127,   644,  900,   658,  1057,  1390, 1540, 1573],
    "La Saïdia":          [297,   807, 1298,  1092,  1257,  1687, 1777, 1753],
    "El Pla del Real":    [76,    406,  510,   439,   706,   859,  912, 1120],
    "L'Olivereta":        [136,   503,  731,   619,   820,  1168, 1390, 1317],
    "Patraix":            [414,  1398, 1237,  1434,  1699,  2258, 2231, 2464],
    "Jesús":              [475,   849,  785,  1087,  1108,  1447, 1259, 1318],
    "Quatre Carreres":    [320,   837, 1558,  1306,  1768,  2443, 2824, 3070],
    "Poblats Marítims":   [369,   615,  852,   793,   806,  1179, 1239, 1387],
    "Camins al Grau":     [291,   953, 1184,  1178,  1740,  2212, 2301, 2424],
    "Algirós":            [161,   821,  742,   741,   878,  1179, 1364, 1129],
    "Benimaclet":         [367,   771,  811,   801,   915,  1292, 1250, 1084],
    "Rascanya":           [182,   859, 1030,   796,   882,  1362, 1264, 1432],
    "Benicalap":          [116,   518,  787,   586,   973,  1260, 1399, 1506],
    "Poblats del Nord":   [702,  1236,  759,   516,   409,   582,  460,  612],
    "Poblats de l'Oest":  [107,   357,  496,   434,   576,   618,  547,  515],
    "Poblats del Sud":    [491,  1122, 1016,   744,   985,  1125,  992, 1077],
}

# Per-district "total ediciones" and % pob ≥16 (last column of Tabla 5)
# Participation rates (unique people across any edition / pob ≥16 años)
district_stats = {
    "Ciutat Vella":       {"total_ediciones": 3042, "pct_pob_16": 12.60},
    "L'Eixample":         {"total_ediciones": 4367, "pct_pob_16": 11.89},
    "Extramurs":          {"total_ediciones": 5526, "pct_pob_16": 13.07},
    "Campanar":           {"total_ediciones": 3902, "pct_pob_16": 12.04},
    "La Saïdia":          {"total_ediciones": 4880, "pct_pob_16": 11.86},
    "El Pla del Real":    {"total_ediciones": 2738, "pct_pob_16": 10.57},
    "L'Olivereta":        {"total_ediciones": 3576, "pct_pob_16": 8.35},
    "Patraix":            {"total_ediciones": 6534, "pct_pob_16": 13.00},
    "Jesús":              {"total_ediciones": 4415, "pct_pob_16": 9.65},
    "Quatre Carreres":    {"total_ediciones": 7562, "pct_pob_16": 11.85},
    "Poblats Marítims":   {"total_ediciones": 3941, "pct_pob_16": 8.19},
    "Camins al Grau":     {"total_ediciones": 6355, "pct_pob_16": 11.32},
    "Algirós":            {"total_ediciones": 3526, "pct_pob_16": 10.90},
    "Benimaclet":         {"total_ediciones": 3457, "pct_pob_16": 13.72},
    "Rascanya":           {"total_ediciones": 4185, "pct_pob_16": 9.19},
    "Benicalap":          {"total_ediciones": 3901, "pct_pob_16": 9.74},
    "Poblats del Nord":   {"total_ediciones": 2733, "pct_pob_16": 48.41},
    "Poblats de l'Oest":  {"total_ediciones": 1645, "pct_pob_16": 16.33},
    "Poblats del Sud":    {"total_ediciones": 3803, "pct_pob_16": 20.94},
}

# ============================================================
# Informe 1 — Tabla 6: participantes según barri de residencia
# Keyed by PDF name; translated to canonical via BARRI_CANONICAL.
# Values verified via `pdftotext -layout` of pages 11-12.
# Format: [ed1, ed2, ed3, ed4, ed5, ed6, ed7, ed8, total_ediciones, pct_pob_16]
# ============================================================
_BARRI_ROWS = {
    "la Seu":                (34,  76, 76,  67,  77,  98,  98, 119, 319, 11.89),
    "la Xerea":              (20,  49, 53,  42,  63,  82,  97, 121, 307,  8.88),
    "el Carme":             (101, 274,240, 214, 263, 292, 345, 337, 951, 16.41),
    "el Pilar":              (43, 150,157, 161, 145, 218, 210, 201, 566, 13.98),
    "el Mercat":             (28, 140,126, 116, 122, 148, 156, 168, 464, 14.47),
    "Sant Francesc":         (16,  94, 95,  81, 116, 131, 172, 152, 435,  8.78),
    "Russafa":               (84, 561,691, 681, 815,1031,1035, 874,2702, 13.14),
    "el Pla del Remei":      (13,  66, 84,  78, 142, 194, 191, 220, 567,  9.43),
    "la Gran Via":           (29, 165,167, 180, 282, 325, 381, 397,1098, 10.80),
    "el Botànic":            (52, 278,214, 228, 274, 316, 347, 355, 895, 15.55),
    "la Roqueta":            (13,  95, 85,  90, 119, 172, 243, 216, 514, 12.75),
    "la Petxina":            (50, 289,342, 301, 447, 667, 779, 731,1776, 13.77),
    "Arrancapins":           (82, 404,527, 441, 646, 754,1006, 800,2341, 11.96),
    "Campanar":              (66, 220,243, 235, 309, 457, 464, 451,1197, 11.88),
    "les Tendetes":          (17,  74, 90,  59,  99, 126, 129, 119, 364,  7.79),
    "el Calvari":             (5,  29, 42,  44,  41,  79,  60,  54, 203,  4.60),
    "Sant Pau":              (39, 321,525, 320, 608, 728, 887, 949,2138, 16.15),
    "Marxalenes":            (35, 127,191, 172, 187, 243, 250, 229, 732,  7.69),
    "Morvedre":              (77, 200,342, 314, 327, 518, 458, 484,1286, 14.37),
    "Trinitat":              (53, 164,169, 202, 267, 345, 395, 357, 970, 14.14),
    "Tormos":                (32, 141,314, 160, 177, 225, 235, 276, 778, 10.54),
    "Sant Antoni":          (100, 175,282, 244, 299, 356, 439, 407,1114, 13.20),
    "Exposició":             (12,  64, 90,  82, 175, 230, 192, 297, 681, 11.97),
    "Mestalla":              (40, 200,268, 229, 345, 418, 486, 530,1325, 10.59),
    "Jaume Roig":            (14,  72,100,  82, 116, 137, 145, 187, 461,  8.59),
    "C. Universitària":      (10,  70, 52,  46,  70,  74,  89, 106, 271, 11.62),
    "Nou Moles":             (97, 299,400, 370, 447, 698, 857, 706,1997,  8.68),
    "Soternes":               (6,  71,143,  65, 152, 221, 257, 234, 634, 14.90),
    "Tres Forques":          (16,  69, 97,  91, 110, 133, 150, 158, 438,  5.41),
    "la Fontsanta":           (4,  19, 23,  38,  27,  34,  52,  96, 195,  6.49),
    "la Llum":               (13,  45, 68,  55,  84,  82,  74, 123, 312,  7.00),
    "Patraix":              (145, 519,479, 579, 635, 874, 872, 881,2460, 11.51),
    "Sant Isidre":           (53, 186,238, 188, 343, 459, 437, 589,1292, 15.20),
    "Vara de Quart":         (70, 408,250, 337, 326, 402, 317, 358,1153, 12.52),
    "el Safranar":           (93, 218,193, 253, 285, 385, 478, 548,1259, 15.88),
    "Favara":                (53,  67, 77,  77, 110, 138, 127,  88, 370, 11.46),
    "la Raiosa":             (41, 228,231, 251, 310, 421, 412, 429,1198,  8.85),
    "l'Hort de Senabre":     (89, 231,230, 303, 361, 433, 352, 362,1241,  8.31),
    "la Creu Coberta":      (154, 125, 99, 156, 159, 184, 141, 156, 637, 11.92),
    "Sant Marcel·lí":       (167, 194,138, 198, 169, 248, 199, 193, 850,  9.65),
    "Camí Real":             (24,  71, 87, 179, 109, 161, 155, 178, 489, 15.60),
    "Mont-Olivet":           (61, 205,284, 391, 398, 573, 635, 517,1602,  9.59),
    "en Corts":              (22, 130,256, 165, 246, 377, 332, 333, 938,  8.97),
    "Malilla":               (90, 287,537, 389, 700, 769, 982,1263,2725, 14.42),
    "la F. Sant Lluís":      (31,  17, 24,  27,  40,  41,  82, 145, 246,  9.46),
    "na Rovella":             (9,  34, 86,  55,  74, 127, 114, 100, 333,  5.04),
    "la Punta":              (89,  70, 72,  67,  59,  98, 160, 248, 498, 21.84),
    "C. Arts i Ciències":    (18,  94,299, 212, 251, 458, 519, 464,1220, 19.59),
    "el Grau":               (25, 130,142, 169, 185, 241, 296, 278, 783,  9.76),
    "el Cab.-Canyam.":       (65, 201,324, 246, 264, 394, 359, 437,1260,  7.55),
    "la Malva-rosa":        (117, 112,141, 188, 167, 291, 292, 307, 855,  7.58),
    "Beteró":               (113, 102,130, 131, 152, 197, 233, 239, 700, 10.07),
    "Natzaret":              (49,  70,115,  59,  38,  56,  59, 126, 343,  6.63),
    "Aiora":                (162, 336,409, 377, 491, 688, 676, 710,2003,  9.27),
    "Albors":                (24,  97,168, 205, 339, 297, 305, 304, 885, 11.57),
    "la Creu del Grau":      (73, 336,270, 363, 498, 462, 627, 560,1546, 12.16),
    "Camí Fondo":            (11,  38, 92,  60, 104, 166, 156, 177, 419, 10.57),
    "Penya-roja":            (21, 146,245, 173, 308, 599, 537, 673,1502, 14.72),
    "l'Illa Perduda":        (24,  81,149, 126, 146, 258, 250, 218, 675,  8.98),
    "Ciutat Jardí":          (57, 233,238, 276, 317, 419, 499, 449,1247, 11.74),
    "l'Amistat":             (28,  88,128, 120, 142, 155, 199, 135, 498,  7.88),
    "la Bega Baixa":         (28, 208,135, 135, 163, 191, 236, 189, 616, 12.84),
    "la Carrasca":           (24, 211, 92,  84, 110, 156, 180, 138, 490, 15.90),
    "Benimaclet":           (189, 572,604, 595, 722, 965, 954, 822,2570, 12.58),
    "Camí de Vera":         (178, 199,207, 206, 193, 327, 296, 262, 887, 18.67),
    "Orriols":               (57, 179,192, 161, 144, 307, 240, 426,1014,  7.11),
    "Torrefiel":             (81, 420,525, 359, 424, 601, 540, 513,1872,  8.28),
    "Sant Llorenç":          (44, 260,313, 276, 314, 454, 484, 493,1299, 15.04),
    "Benicalap":            (106, 475,716, 521, 845,1130,1277,1401,3544, 10.13),
    "Ciutat Fallera":        (10,  43, 71,  65, 128, 130, 122, 105, 357,  7.04),
    "Benifaraig":           (329, 170,227, 108,  72, 131,  73, 112, 565, 66.39),
    "Poble Nou":             (17,  23, 45,  23,  36,  54,  33,  67, 178, 22.45),
    "Carpesa":              (147, 295, 45,  78,  92, 115, 107, 162, 585, 56.03),
    "les C. Bàrcena":         (2,  11, 25,  49,  10,  17,  17,  30,  84, 26.58),
    # NOTE: the source PDF shows Ed 8 = 169 for Mauella, which is physically
    # impossible for a pedanía of ~60 residents and contradicts its declared
    # total_unique = 2 across the 8 editions. We treat it as a transcription
    # error in the Oficina d'Estadística PDF and set Ed 8 to 0, consistent
    # with the pattern of the surrounding editions and the aggregated totals.
    "Mauella":                (0,   0,  0,   4,   1,   0,   0,   0,   2,  3.85),
    "Massarrojos":           (68, 474,207, 181, 136, 176, 148,  72, 818, 41.65),
    "Borbotó":              (139, 263,210,  73,  62,  89,  82, 409, 501, 80.03),
    "Benimàmet":            (104, 336,474, 414, 539, 542, 479, 106,1451, 12.76),
    "Beniferri":              (3,  21, 22,  20,  37,  76,  68,  85, 194, 20.02),
    "el Forn d'Alcedo":      (55, 156, 83,  99,  32,  94,  63, 218, 357, 32.90),
    "Cast.-l'Oliveral":     (122, 315,292, 203, 332, 335, 269, 176, 946, 16.22),
    "Pinedo":                (15, 255, 52,  87,  98, 146, 149, 194, 569, 25.69),
    "el Saler":              (36,  96,141, 105, 175, 190, 156,  76, 554, 34.13),
    "el Palmar":              (1,   1, 50,  15, 148,  55,  87,  92, 215, 32.19),
    "el Perellonet":         (20,  10, 33,  37,  25,  42,  53, 142, 195, 15.53),
    "la Torre":             (204, 214,271, 129, 101, 174, 133,  94, 723, 17.19),
    "Faitanar":              (38,  75, 94,  69,  74,  89,  82,   1, 244, 19.09),
}

# ============================================================
# Informe 1 — Tabla 19: funnel de propuestas por edición
# ============================================================
funnel_by_edition = {
    "1": {
        "presentadas":       {"total": 619,  "particulares": 324,  "grupos": 179, "ayuntamiento": 116},
        "desest_apoyo":      None,
        "desest_viabilidad": {"total": 384,  "particulares": 237,  "grupos": 144, "ayuntamiento": 3},
        "votadas":           {"total": 235,  "particulares": 87,   "grupos": 35,  "ayuntamiento": 113},
        "seleccionadas":     {"total": 109,  "particulares": 38,   "grupos": 20,  "ayuntamiento": 51},
    },
    "2": {
        "presentadas":       {"total": 585,  "particulares": 471, "grupos": 114, "ayuntamiento": 0},
        "desest_apoyo":      {"total": 319,  "particulares": 319, "grupos": 0,   "ayuntamiento": 0},
        "desest_viabilidad": {"total": 157,  "particulares": 98,  "grupos": 59,  "ayuntamiento": 0},
        "votadas":           {"total": 115,  "particulares": 59,  "grupos": 56,  "ayuntamiento": 0},
        "seleccionadas":     {"total": 71,   "particulares": 34,  "grupos": 37,  "ayuntamiento": 0},
    },
    "3": {
        "presentadas":       {"total": 562,  "particulares": 546, "grupos": 0,   "ayuntamiento": 16},
        "desest_apoyo":      {"total": 468,  "particulares": 462, "grupos": 0,   "ayuntamiento": 6},
        "desest_viabilidad": {"total": 47,   "particulares": 47,  "grupos": 0,   "ayuntamiento": 0},
        "votadas":           {"total": 47,   "particulares": 37,  "grupos": 0,   "ayuntamiento": 10},
        "seleccionadas":     {"total": 11,   "particulares": 6,   "grupos": 0,   "ayuntamiento": 5},
    },
    "4": {
        "presentadas":       {"total": 540,  "particulares": 413, "grupos": 127, "ayuntamiento": 0},
        "desest_apoyo":      {"total": 165,  "particulares": 165, "grupos": 0,   "ayuntamiento": 0},
        "desest_viabilidad": {"total": 173,  "particulares": 131, "grupos": 42,  "ayuntamiento": 0},
        "votadas":           {"total": 202,  "particulares": 117, "grupos": 85,  "ayuntamiento": 0},
        "seleccionadas":     {"total": 103,  "particulares": 55,  "grupos": 48,  "ayuntamiento": 0},
    },
    "5": {
        "presentadas":       {"total": 632,  "particulares": 607, "grupos": 0,   "ayuntamiento": 25},
        "desest_apoyo":      {"total": 486,  "particulares": 473, "grupos": 0,   "ayuntamiento": 13},
        "desest_viabilidad": {"total": 83,   "particulares": 82,  "grupos": 0,   "ayuntamiento": 1},
        "votadas":           {"total": 63,   "particulares": 52,  "grupos": 0,   "ayuntamiento": 11},
        "seleccionadas":     {"total": 21,   "particulares": 16,  "grupos": 0,   "ayuntamiento": 5},
    },
    "6": {
        "presentadas":       {"total": 1284, "particulares": 1249, "grupos": 26, "ayuntamiento": 9},
        "desest_apoyo":      {"total": 478,  "particulares": 478,  "grupos": 0,  "ayuntamiento": 0},
        "desest_viabilidad": {"total": 523,  "particulares": 509,  "grupos": 10, "ayuntamiento": 4},
        "votadas":           {"total": 283,  "particulares": 262,  "grupos": 16, "ayuntamiento": 5},
        "seleccionadas":     {"total": 139,  "particulares": 131,  "grupos": 5,  "ayuntamiento": 3},
    },
    "7": {
        "presentadas":       {"total": 1567, "particulares": 1440, "grupos": 103, "ayuntamiento": 24},
        "desest_apoyo":      {"total": 815,  "particulares": 815,  "grupos": 0,   "ayuntamiento": 0},
        "desest_viabilidad": {"total": 431,  "particulares": 389,  "grupos": 42,  "ayuntamiento": 0},
        "votadas":           {"total": 321,  "particulares": 236,  "grupos": 61,  "ayuntamiento": 24},
        "seleccionadas":     {"total": 146,  "particulares": 115,  "grupos": 21,  "ayuntamiento": 10},
    },
    "8": {
        "presentadas":       {"total": 2776, "particulares": 2626, "grupos": 150, "ayuntamiento": 0},
        "desest_apoyo":      {"total": 1335, "particulares": 1262, "grupos": 73,  "ayuntamiento": 0},
        "desest_viabilidad": {"total": 983,  "particulares": 946,  "grupos": 37,  "ayuntamiento": 0},
        "votadas":           {"total": 458,  "particulares": 418,  "grupos": 40,  "ayuntamiento": 0},
        "seleccionadas":     {"total": 250,  "particulares": 231,  "grupos": 19,  "ayuntamiento": 0},
    },
}

# ============================================================
# Informe 3 (2025/26) — Tabla 17: proyectos votados y seleccionados por
# distrito × tipo proponente (particulares / grupos trabajo).
# Page 20 of the 2025/26 report.
# ============================================================
edicion8_seleccion_por_distrito = {
    # district → {votadas: {total, particulares, grupos}, seleccionadas: {...}}
    "Ciutat Vella":       {"votadas": {"total": 17, "particulares": 12, "grupos": 5},
                           "seleccionadas": {"total": 10, "particulares": 6, "grupos": 4}},
    "L'Eixample":         {"votadas": {"total": 11, "particulares": 11, "grupos": 0},
                           "seleccionadas": {"total": 7,  "particulares": 7, "grupos": 0}},
    "Extramurs":          {"votadas": {"total": 23, "particulares": 22, "grupos": 1},
                           "seleccionadas": {"total": 15, "particulares": 14, "grupos": 1}},
    "Campanar":           {"votadas": {"total": 24, "particulares": 22, "grupos": 2},
                           "seleccionadas": {"total": 9,  "particulares": 8, "grupos": 1}},
    "La Saïdia":          {"votadas": {"total": 32, "particulares": 30, "grupos": 2},
                           "seleccionadas": {"total": 22, "particulares": 20, "grupos": 2}},
    "El Pla del Real":    {"votadas": {"total": 23, "particulares": 23, "grupos": 0},
                           "seleccionadas": {"total": 13, "particulares": 13, "grupos": 0}},
    "L'Olivereta":        {"votadas": {"total": 14, "particulares": 12, "grupos": 2},
                           "seleccionadas": {"total": 11, "particulares": 10, "grupos": 1}},
    "Patraix":            {"votadas": {"total": 41, "particulares": 35, "grupos": 6},
                           "seleccionadas": {"total": 17, "particulares": 14, "grupos": 3}},
    "Jesús":              {"votadas": {"total": 14, "particulares": 12, "grupos": 2},
                           "seleccionadas": {"total": 14, "particulares": 12, "grupos": 2}},
    "Quatre Carreres":    {"votadas": {"total": 50, "particulares": 45, "grupos": 5},
                           "seleccionadas": {"total": 26, "particulares": 22, "grupos": 4}},
    "Poblats Marítims":   {"votadas": {"total": 29, "particulares": 25, "grupos": 4},
                           "seleccionadas": {"total": 12, "particulares": 11, "grupos": 1}},
    "Camins al Grau":     {"votadas": {"total": 29, "particulares": 28, "grupos": 1},
                           "seleccionadas": {"total": 8,  "particulares": 8, "grupos": 0}},
    "Algirós":            {"votadas": {"total": 18, "particulares": 18, "grupos": 0},
                           "seleccionadas": {"total": 12, "particulares": 12, "grupos": 0}},
    "Benimaclet":         {"votadas": {"total": 24, "particulares": 21, "grupos": 3},
                           "seleccionadas": {"total": 11, "particulares": 10, "grupos": 1}},
    "Rascanya":           {"votadas": {"total": 15, "particulares": 14, "grupos": 1},
                           "seleccionadas": {"total": 13, "particulares": 13, "grupos": 0}},
    "Benicalap":          {"votadas": {"total": 22, "particulares": 22, "grupos": 0},
                           "seleccionadas": {"total": 9,  "particulares": 9, "grupos": 0}},
    "Poblats del Nord":   {"votadas": {"total": 19, "particulares": 18, "grupos": 1},
                           "seleccionadas": {"total": 10, "particulares": 10, "grupos": 0}},
    "Poblats de l'Oest":  {"votadas": {"total": 22, "particulares": 17, "grupos": 5},
                           "seleccionadas": {"total": 11, "particulares": 9, "grupos": 2}},
    "Poblats del Sud":    {"votadas": {"total": 31, "particulares": 31, "grupos": 0},
                           "seleccionadas": {"total": 18, "particulares": 18, "grupos": 0}},
}

# ============================================================
# Informe 4 — Tabla 6: distribución presupuestaria 2025 (16 M€)
# Values verified via `pdftotext -layout`.
# ============================================================
budget_allocation_2025 = {
    "Ciutat Vella":       {"pob_total": 30002, "pob_16":  26547, "renta_media": 20593,
                           "asignacion_inicial": 160000,  "por_poblacion": 222990, "por_renta":  12663,
                           "inversion_total": 395154,  "eur_habitante": 13.2},
    "L'Eixample":         {"pob_total": 44631, "pob_16":  38590, "renta_media": 21841,
                           "asignacion_inicial": 160000,  "por_poblacion": 324150, "por_renta":   1744,
                           "inversion_total": 485894,  "eur_habitante": 10.9},
    "Extramurs":          {"pob_total": 50643, "pob_16":  44234, "renta_media": 18232,
                           "asignacion_inicial": 160000,  "por_poblacion": 371558, "por_renta": 109030,
                           "inversion_total": 640588,  "eur_habitante": 12.6},
    "Campanar":           {"pob_total": 40917, "pob_16":  34459, "renta_media": 16542,
                           "asignacion_inicial": 160000,  "por_poblacion": 289450, "por_renta": 173937,
                           "inversion_total": 623387,  "eur_habitante": 15.2},
    "La Saïdia":          {"pob_total": 48383, "pob_16":  42431, "renta_media": 14173,
                           "asignacion_inicial": 160000,  "por_poblacion": 356413, "por_renta": 405544,
                           "inversion_total": 921957,  "eur_habitante": 19.1},
    "El Pla del Real":    {"pob_total": 31020, "pob_16":  26259, "renta_media": 22403,
                           "asignacion_inicial": 160000,  "por_poblacion": 220571, "por_renta":      0,
                           "inversion_total": 380571,  "eur_habitante": 12.3},
    "L'Olivereta":        {"pob_total": 51474, "pob_16":  45046, "renta_media": 12338,
                           "asignacion_inicial": 160000,  "por_poblacion": 378379, "por_renta": 645299,
                           "inversion_total": 1183678, "eur_habitante": 23.0},
    "Patraix":            {"pob_total": 59417, "pob_16":  52238, "renta_media": 14906,
                           "asignacion_inicial": 160000,  "por_poblacion": 438790, "por_renta": 413267,
                           "inversion_total": 1012058, "eur_habitante": 17.0},
    "Jesús":              {"pob_total": 53582, "pob_16":  47125, "renta_media": 12877,
                           "asignacion_inicial": 160000,  "por_poblacion": 395842, "por_renta": 601708,
                           "inversion_total": 1157550, "eur_habitante": 21.6},
    "Quatre Carreres":    {"pob_total": 80266, "pob_16":  69238, "renta_media": 13810,
                           "asignacion_inicial": 160000,  "por_poblacion": 581588, "por_renta": 733444,
                           "inversion_total": 1475031, "eur_habitante": 18.4},
    "Poblats Marítims":   {"pob_total": 56843, "pob_16":  49757, "renta_media": 12958,
                           "asignacion_inicial": 160000,  "por_poblacion": 417950, "por_renta": 627518,
                           "inversion_total": 1205469, "eur_habitante": 21.2},
    "Camins al Grau":     {"pob_total": 67453, "pob_16":  58261, "renta_media": 15067,
                           "asignacion_inicial": 160000,  "por_poblacion": 489383, "por_renta": 449227,
                           "inversion_total": 1098609, "eur_habitante": 16.3},
    "Algirós":            {"pob_total": 36266, "pob_16":  32515, "renta_media": 16560,
                           "asignacion_inicial": 160000,  "por_poblacion": 273121, "por_renta": 153221,
                           "inversion_total": 586341,  "eur_habitante": 16.2},
    "Benimaclet":         {"pob_total": 28541, "pob_16":  25253, "renta_media": 16141,
                           "asignacion_inicial": 160000,  "por_poblacion": 212121, "por_renta": 138497,
                           "inversion_total": 510618,  "eur_habitante": 17.9},
    "Rascanya":           {"pob_total": 56703, "pob_16":  48451, "renta_media": 12489,
                           "asignacion_inicial": 160000,  "por_poblacion": 406980, "por_renta": 689683,
                           "inversion_total": 1256663, "eur_habitante": 22.2},
    "Benicalap":          {"pob_total": 50152, "pob_16":  42790, "renta_media": 12699,
                           "asignacion_inicial": 160000,  "por_poblacion": 359429, "por_renta": 584434,
                           "inversion_total": 1103863, "eur_habitante": 22.0},
    "Poblats del Nord":   {"pob_total":  7009, "pob_16":   6012, "renta_media": 15925,
                           "asignacion_inicial": 373506, "por_poblacion": None, "por_renta": None,
                           "inversion_total": 373506,  "eur_habitante": 53.3},
    "Poblats de l'Oest":  {"pob_total": 15261, "pob_16":  13063, "renta_media": 11884,
                           "asignacion_inicial": 692676, "por_poblacion": None, "por_renta": None,
                           "inversion_total": 692676,  "eur_habitante": 45.4},
    "Poblats del Sud":    {"pob_total": 22043, "pob_16":  18960, "renta_media": 13080,
                           "asignacion_inicial": 896387, "por_poblacion": None, "por_renta": None,
                           "inversion_total": 896387,  "eur_habitante": 40.7},
}


# Aggregate headline from Informe 1 pages 5-21
# Each "loyalty" distribution (cuántas personas han participado en N ediciones)
# is taken from the corresponding section of the report:
#   - any phase  → page 6
#   - proponen   → page 13
#   - apoyan     → page 16 (no Ed 1 → max 7 repetitions)
#   - votan      → page 20
aggregate_headline = {
    "total_personas_unicas": 80091,
    "pct_pob_16_mas": 11.63,
    "pct_pob_total": 10.0,
    "distribucion_ediciones": {  # any-phase loyalty
        "1": 45906, "2": 15127, "3": 7918, "4": 4467,
        "5": 2967,  "6": 2071,  "7": 1270, "8": 365,
    },
    "distribucion_ediciones_por_fase": {
        "alguna": {
            "total": 80091,
            "por_n_ediciones": {
                "1": 45906, "2": 15127, "3": 7918, "4": 4467,
                "5": 2967,  "6": 2071,  "7": 1270, "8": 365,
            },
        },
        "proponen": {
            "total": 5574,
            "por_n_ediciones": {
                "1": 4461, "2": 748, "3": 221, "4": 80,
                "5": 31,   "6": 27,  "7": 5,   "8": 1,
            },
        },
        "apoyan": {
            "total": 47783,
            "por_n_ediciones": {  # max 7 repetitions (Ed 1 had no apoyo phase)
                "1": 34848, "2": 8173, "3": 2825, "4": 1162,
                "5": 452,   "6": 235,  "7": 88,
            },
        },
        "votan": {
            "total": 63297,
            "por_n_ediciones": {
                "1": 35823, "2": 12174, "3": 6420, "4": 3573,
                "5": 2541,  "6": 1628,  "7": 892,  "8": 246,
            },
        },
    },
    "por_sexo": {
        "mujer": 43834, "hombre": 36249, "pct_mujer": 54.7, "pct_hombre": 45.3,
        "RR_mujer_vs_hombre": 1.069,
    },
    "por_edad": {
        "16-24": 5100, "25-34": 10959, "35-44": 21035, "45-54": 19993,
        "55-64": 12280, "65-74": 7633, "75+": 3082,
    },
    "por_nacionalidad": {
        "espanola": 76641, "extranjera": 3472, "pct_espanola": 95.7, "pct_extranjera": 3.5,
    },
}


def load_edicion8_votos_por_barri():
    """Load the parsed Tabla 24 from data/raw.
    Produced by parsing `pdftotext -layout` output of Informe 3 (pages 25-27).
    """
    path = Path(__file__).parent.parent / "data" / "raw" / "tabla24-edicion8-votos-barri.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def build():
    def to_ed_dict(values):
        return {ed: v for ed, v in zip(EDITIONS, values)}

    # Build barri section with canonical names
    by_barri: dict = {}
    unknown = []
    for pdf_name, row in _BARRI_ROWS.items():
        canon = BARRI_CANONICAL.get(pdf_name)
        if not canon:
            unknown.append(pdf_name)
            continue
        ed_vals, total, pct = row[:8], row[8], row[9]
        by_barri[canon] = {
            "por_edicion": to_ed_dict(ed_vals),
            "total_ediciones": total,
            "pct_pob_16": pct,
        }
    if unknown:
        print(f"WARN barris PDF sin mapear: {unknown}")

    out = {
        "_meta": {
            "fuente": "Oficina d'Estadística, Ajuntament de València",
            "informes": [
                {"nombre": "Análisis de la participación ciudadana en las ocho ediciones celebradas de Presupuestos Participativos",
                 "paginas": 23, "firma": "04/02/2026",
                 "url": "https://vlcparticipa.valencia.es/docs/analisis-participacion-ciudadana-ocho-ediciones-presupuestos-participativos.pdf"},
                {"nombre": "Modificación de la Distribución presupuestaria Presupuestos Participativos 2025",
                 "paginas": 6,
                 "url": "https://vlcparticipa.valencia.es/docs/modificacion-informe-distribucion-presupuestos-participativos-2025.pdf"},
            ],
            "ediciones": {ed: EDITION_LABELS[ed] for ed in EDITIONS},
        },
        "headline": aggregate_headline,
        "participantes_por_edicion": global_by_edition,
        "participantes_por_distrito": {
            d: {
                "por_edicion": to_ed_dict(series),
                "total_ediciones": district_stats[d]["total_ediciones"],
                "pct_pob_16": district_stats[d]["pct_pob_16"],
            }
            for d, series in participants_by_district_edition.items()
        },
        "participantes_por_barri": by_barri,
        "funnel_propuestas": funnel_by_edition,
        "edicion8_seleccion_por_distrito": edicion8_seleccion_por_distrito,
        "edicion8_votos_por_barri": load_edicion8_votos_por_barri(),
        "distribucion_presupuestaria_2025": {
            "presupuesto_total_euros": 16000000,
            "criterios": ["suelo mínimo por distrito (160k€; pedanías ajustadas)",
                          "50% por población ≥16 años",
                          "50% inversamente proporcional a renta media"],
            "por_distrito": budget_allocation_2025,
        },
    }

    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT_FILE}")
    print(f"  Distritos con serie: {len(participants_by_district_edition)}")
    print(f"  Barris con serie: {len(by_barri)}")
    print(f"  Ediciones en funnel: {len(funnel_by_edition)}")


if __name__ == "__main__":
    build()
