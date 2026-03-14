#!/usr/bin/env bash
set -euo pipefail

if [[ -f deploy/.env.scanner ]]; then
  set -a
  source deploy/.env.scanner
  set +a
fi

python -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
