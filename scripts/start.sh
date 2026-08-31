#!/usr/bin/env bash
# SentinelIQ production launcher (Linux / macOS).
#   ./scripts/start.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "$ROOT/.env" ]]; then
  echo "[start] .env not found - copy .env.example to .env and configure it."
fi

if [[ ! -d "$ROOT/venv" ]]; then
  echo "[start] creating virtualenv..."
  python3 -m venv "$ROOT/venv"
  "$ROOT/venv/bin/pip" install -U pip
  "$ROOT/venv/bin/pip" install -r "$ROOT/requirements.txt"
fi

echo "[start] launching SentinelIQ (single worker)..."
cd "$ROOT"
exec "$ROOT/venv/bin/python" run.py