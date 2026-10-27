#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/.venv/bin/python"

if [ ! -x "$PY" ]; then
  "$ROOT/setup_env.sh"
fi

"$PY" "$ROOT/run_pipeline.py" --root "$ROOT" "$@"
