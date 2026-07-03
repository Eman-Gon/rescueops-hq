#!/usr/bin/env bash
# Run the FastAPI backend and the React dev server together in one terminal.
# Ctrl-C stops both. Backend: http://localhost:8000  ·  Frontend: http://localhost:5173
set -euo pipefail
cd "$(dirname "$0")"

# Activate the Python venv if present so `uvicorn` resolves.
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Install frontend deps on first run.
if [ ! -d frontend/node_modules ]; then
  echo "▶ installing frontend deps…"
  (cd frontend && npm install)
fi

echo "▶ backend  → http://localhost:8000  (API at /api)"
uvicorn api.server:app --reload --port 8000 &
BACK=$!

echo "▶ frontend → http://localhost:5173"
(cd frontend && npm run dev) &
FRONT=$!

# Kill both children on exit / Ctrl-C.
trap 'kill "$BACK" "$FRONT" 2>/dev/null || true' EXIT INT TERM
wait
