#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

if [[ ! -f "app/static/dist/app.js" ]]; then
  if command -v npm >/dev/null 2>&1; then
    echo "Building frontend assets..."
    npm run build
  else
    echo "Frontend bundle missing and npm is not available." >&2
    exit 1
  fi
fi

export PYTHONUNBUFFERED=1
exec uvicorn app.main:create_app --factory --host "${AIRWAVE_HOST:-0.0.0.0}" --port "${AIRWAVE_PORT:-8000}" --reload --no-access-log
