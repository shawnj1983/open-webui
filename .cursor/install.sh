#!/usr/bin/env bash
# Idempotent Cloud Agent setup for Open WebUI (SvelteKit frontend + FastAPI backend).
# Safe to run repeatedly: refreshes dependencies and generated state only.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &>/dev/null && pwd)"
cd "$REPO_ROOT"

# --- System packages -------------------------------------------------------
# The base image ships Node 22 and Python 3.12 but not the venv/build headers
# needed to build a few backend wheels. Install them when missing (a snapshot
# usually already contains them, so this is a no-op on rebuilds).
if ! python3 -m venv --help >/dev/null 2>&1 || ! command -v gcc >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-venv python3-dev build-essential
  fi
fi

# --- Frontend --------------------------------------------------------------
npm ci
# Fetch the Pyodide runtime assets the frontend bundles (also run by `npm run dev`).
node scripts/prepare-pyodide.js

# --- Backend ---------------------------------------------------------------
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
pip install -r backend/requirements.txt

# --- Dev signing key -------------------------------------------------------
# Generate a persistent local JWT signing key (gitignored) so the dev server
# does not need a secret baked into environment.json.
if [ ! -f backend/.webui_secret_key ]; then
  head -c 24 /dev/urandom | base64 > backend/.webui_secret_key
fi

echo "Open WebUI dev environment ready."
