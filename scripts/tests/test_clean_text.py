"""Tests for NOISE_PATTERNS and clean_text (script 04)."""


# ── Fixtures: realistic fragments from actual actes ──────────────────────────

PAGE_HEADER_VAL = "PLE - ACTA DE LA SESSIÓ ORDINÀRIA DE 28 DE GENER DE 2025"
PAGE_HEADER_CAS = "PLENO - ACTA DE LA SESIÓN ORDINARIA DE 28 DE ENERO DE 2025"
COPIA_INFORMATIVA = "CÒPIA INFORMATIVA"
ID_DOCUMENT = "Id. document: A_00001_20250128_00001"

GDPR_VAL = (
    "En aquest document s'han suprimit les dades de caràcter personal\n"
    "que han sigut omesos d'acord amb la normativa de protecció de dades\n"
    "en aplicació del Reglament General de Protecció de Dades (UE) 2016/679."
)
GDPR_CAS = (
    "En este documento se han suprimido los datos de carácter personal\n"
    "que han sido omitidos conforme a la normativa de protección de datos\n"
    "en aplicación del Reglamento General de Protección de Datos (UE) 2016/679."
)

DIGITAL_SIG_VAL = (
    "Signat electrònicament per:\n"
    "SECRETARI GENERAL\n"
    "HILARIO LLAVADOR CIFUENTES\n"
    "Data: 2025-02-10\n"
    "Emissor cert: ACCVCA-120\n"
    "Núm. sèrie cert: 16898817\n"
)
DIGITAL_SIG_CAS = "Firmado electrónicamente por el Secretario General en fecha 2025-02-10"

PAGE_NUMBER_STANDALONE = "\n   42   \n"
CERT_SERIAL = "\n98765432101234567\n"

REAL_CONTENT = (
    "La representant de l'Associació de Veïns de Benicalap pren la paraula per "
    "exposar la problemàtica del trànsit al carrer Major."
)


def test_page_header_val_removed(mod_04):
    result = mod_04.clean_text(f"{PAGE_HEADER_VAL}\n\n{REAL_CONTENT}")
    assert "PLE - ACTA" not in result
    assert REAL_CONTENT in result


def test_page_header_cas_removed(mod_04):
    result = mod_04.clean_text(f"{PAGE_HEADER_CAS}\n\n{REAL_CONTENT}")
    assert "PLENO - ACTA" not in result
    assert REAL_CONTENT in result


def test_copia_informativa_removed(mod_04):
    result = mod_04.clean_text(f"{COPIA_INFORMATIVA}\n\n{REAL_CONTENT}")
    assert "CÒPIA INFORMATIVA" not in result


def test_id_document_removed(mod_04):
    result = mod_04.clean_text(f"{ID_DOCUMENT}\n\n{REAL_CONTENT}")
    assert "Id. document:" not in result


def test_gdpr_val_removed(mod_04):
    result = mod_04.clean_text(f"{GDPR_VAL}\n\n{REAL_CONTENT}")
    assert "(UE) 2016/679" not in result


def test_gdpr_cas_removed(mod_04):
    result = mod_04.clean_text(f"{GDPR_CAS}\n\n{REAL_CONTENT}")
    assert "(UE) 2016/679" not in result


def test_digital_signature_val_removed(mod_04):
    result = mod_04.clean_text(f"{REAL_CONTENT}\n\n{DIGITAL_SIG_VAL}")
    assert "Signat electrònicament" not in result
    assert REAL_CONTENT in result


def test_digital_signature_cas_removed(mod_04):
    result = mod_04.clean_text(f"{REAL_CONTENT}\n\n{DIGITAL_SIG_CAS}")
    assert "Firmado electrónicamente" not in result


def test_standalone_page_number_removed(mod_04):
    text = f"{REAL_CONTENT}{PAGE_NUMBER_STANDALONE}{REAL_CONTENT}"
    result = mod_04.clean_text(text)
    assert "   42   " not in result


def test_cert_serial_removed(mod_04):
    result = mod_04.clean_text(f"{REAL_CONTENT}{CERT_SERIAL}")
    assert "98765432101234567" not in result


def test_content_preserved_through_cleaning(mod_04):
    """Noise removal must not eat actual intervention text."""
    noise = "\n".join([
        PAGE_HEADER_VAL,
        ID_DOCUMENT,
        REAL_CONTENT,
        GDPR_VAL,
        PAGE_NUMBER_STANDALONE,
        REAL_CONTENT,
    ])
    result = mod_04.clean_text(noise)
    assert result.count(REAL_CONTENT) == 2


def test_multiple_blank_lines_collapsed(mod_04):
    text = "primera part\n\n\n\n\nsegona part"
    result = mod_04.clean_text(text)
    assert "\n\n\n" not in result
    assert "primera part" in result
    assert "segona part" in result
