#!/usr/bin/env bash
set -euo pipefail

if [[ -f deploy/.env.trader ]]; then
  set -a
  source deploy/.env.trader
  set +a
fi

python -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
