#!/bin/bash
# Publica una snapshot filtrada al repo público.
# Usa rama huérfana: el repo público no tiene historial con archivos privados.
set -e

MAIN_COMMIT=$(git rev-parse main)

git diff-index --quiet HEAD -- || { echo "Hay cambios sin commitear. Haz commit primero."; exit 1; }

cleanup() {
  git checkout -f main 2>/dev/null || true
  git branch -D _public_release 2>/dev/null || true
}
trap cleanup EXIT

echo "Creando snapshot público (rama huérfana)..."
git checkout --orphan _public_release
git rm -rf --cached . --quiet

# Añadir solo lo que es público (referenciar main por hash, no HEAD)
git checkout "$MAIN_COMMIT" -- scripts/ web/ CLAUDE.md .gitignore push-public.sh

# Añadir data/ excluyendo archivos privados/voluminosos
git checkout "$MAIN_COMMIT" -- data/
git rm -r --cached \
    data/raw/pdfs/ \
    data/raw/texts/ \
    data/raw/interventions_raw.json \
    --quiet 2>/dev/null || true

git commit -m "Public snapshot $(date +%Y-%m-%d)" -q

echo "Publicando en github.com/miguelsanchez/laciutatparla..."
git push public _public_release:main --force

echo "Listo."
