#!/usr/bin/env bash
set -euo pipefail

if [[ -f deploy/.env.strategy ]]; then
  set -a
  source deploy/.env.strategy
  set +a
fi

python -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
