#!/usr/bin/env python3
"""One-off: rebuild 2017-04-27-004 (Fernando del Molino + Iban Alcalá) with all 3 turns.

The block was extracted with only the first turn. Composing a full version manually.
Then re-generating the val translation via Haiku.
"""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path

import anthropic
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
_api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC")
if _api_key:
    os.environ["ANTHROPIC_API_KEY"] = _api_key

DATA = Path(__file__).parent.parent / "data" / "raw" / "interventions_raw.json"
client = anthropic.Anthropic(http_client=httpx.Client(trust_env=False))

# Composed text combining all 3 turns from 2017-04-27 block 4 (En quart lloc).
# Preserves literal transcript (including typo "particiar" in original).
FULL_TEXT = """Buenos días a todos.
Represento a la Federación del Taxi de Valencia y Stop Accidentes nos ha cedido el espacio porque estamos totalmente de acuerdo en la medida. Estoy totalmente en contra de muchas cosas de las que ha dicho porque **la Mesa de la Movilidad** si es algo es que tenemos posibilidad todos de intervenir y ahí se ha demostrado que **más del 90 % de las asociaciones** que intervienen, y no son pocas, estoy hablando de **50 o 60 asociaciones**, han solicitado esta medida.
**Creemos que la accesibilidad y la seguridad** de la ciudad está por encima de los intereses económicos de nadie y pensamos que **las personas con discapacidad, invidentes** y demás no pueden estar esperando a que un interés económico se ponga a ver si los políticos se ponen de acuerdo y están de acuerdo en quitar esta medida.
**La Ley de Seguridad Vial** es contundente. El art. 40.1 y 2 dicen que **no se puede estacionar ni parar en el carril exclusivo** del transporte público. **La inseguridad jurídica** que tiene esta ciudad con esta medida es total y espero que esto no se quede solo aquí y acabe modificando también la Ordenanza.
No quiero perder más tiempo porque también va a particiar el compañero.
Hola, buenos días.
Soy Iban Alcalá, presidente del **Comité de Empresa de EMT**, y lo primero, como ha dicho el compañero, agradecer a Stop Accidentes que nos ceda la palabra.
Y lo que sí que quería es, en nombre de los **trabajadores de la EMT**, apoyar al concejal de Movilidad de **evitar el aparcamiento en el carril bus de las líneas nocturnas** por motivos evidentes de evitar situaciones problemáticas y peligrosas para nuestros usuarios, en especial para aquellos con **movilidad reducida**. Me solidarizo con la compañera que ha estado hablando antes la cual ha comentado que prácticamente se tiene que jugar la vida para coger el autobús.
Entonces, lo que sí que le animamos a que siga actuando en la protección del resto de carriles bus, para poder dar mas y mejor servicio a los ciudadanos.
Muchas gracias.
Como queda espacio, quería añadir también que **no conozco ninguna ciudad de España ni de Europa que tenga esta medida**, porque además esto es una irregularidad que esto hay que solucionarlo. **Ningún plan de movilidad urbana**, ni ningún plan de accesibilidad, i normativa nacional ni europea está de acuerdo con esta norma.
Por favor, que reine un poco la cordura en este Pleno."""

NEW_RESUM_CAS = "Fernando del Molino y Iban Alcalá, en representación de Stop Accidents (con cesión del taxi y apoyo del comité de empresa de la EMT), defienden la prohibición de aparcar en el carril bus por motivos de seguridad y accesibilidad, especialmente para personas con movilidad reducida, y reclaman aplicar la Ley de Seguridad Vial."
NEW_RESUM_VAL = "Fernando del Molino i Iban Alcalá, en representació de Stop Accidents (amb cessió del taxi i suport del comité d'empresa de l'EMT), defenen la prohibició d'aparcar al carril bus per motius de seguretat i accessibilitat, especialment per a persones amb mobilitat reduïda, i reclamen aplicar la Llei de Seguretat Vial."


def translate_to_val(text: str) -> str:
    prompt = f"""Tradueix el següent text d'una intervenció ciutadana al valencià.

Regles estrictes:
- Mantén EXACTAMENT els mateixos paràgrafs (cada \\n del original és un \\n a la traducció).
- Mantén els marcadors de negreta **així** sobre les frases EQUIVALENTS.
- NO afegisques cap explicació. Respon NOMÉS amb el text traduït.

TEXT ORIGINAL:
---
{text}
---"""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8096,
        messages=[{"role": "user", "content": prompt}],
    )
    out = msg.content[0].text.strip()
    if out.startswith("```"):
        out = out.split("\n", 1)[1] if "\n" in out else out
        if out.endswith("```"):
            out = out.rsplit("```", 1)[0]
    return out.strip()


def main():
    raw = json.loads(DATA.read_text())
    target = None
    for iv in raw:
        if iv["id"] == "2017-04-27-004":
            target = iv
            break
    if not target:
        print("Entry 2017-04-27-004 not found")
        return

    print(f"Old: {target.get('intervinient')} ({target.get('entitat')}) — text_original={len(target.get('text_original') or '')}c")

    print(f"Translating to val ({len(FULL_TEXT)}c)...")
    val = translate_to_val(FULL_TEXT)
    print(f"Got text_val: {len(val)}c")

    target["intervinient"] = "Fernando del Molino Écija i Iban Alcalá Boix"
    target["entitat"] = "Associació Stop Accidents"
    target["tipus_entitat"] = "ong"
    target["text_original"] = FULL_TEXT
    target["text_cas"] = ""  # idioma is castellano
    target["text_val"] = val
    target["resum_cas"] = NEW_RESUM_CAS
    target["resum_val"] = NEW_RESUM_VAL
    target["idioma_original"] = "castellano"

    DATA.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    print(f"\nSaved: {target['intervinient']} ({target['entitat']})")


if __name__ == "__main__":
    main()
