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
    if ! npm run build; then
      echo "Frontend build failed; attempting npm install and retrying..." >&2
      npm install
      npm run build
    fi
  else
    echo "Frontend bundle missing and npm is not available." >&2
    exit 1
  fi
fi

export PYTHONUNBUFFERED=1
exec uvicorn app.main:create_app --factory --no-access-log --log-level warning --host "${AIRWAVE_HOST:-0.0.0.0}" --port "${AIRWAVE_PORT:-8000}" --reload