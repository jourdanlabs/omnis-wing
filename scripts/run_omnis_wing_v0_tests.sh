#!/usr/bin/env bash
# Cold OMNIS WING tests — W0 + R1.1 + R2 chat path.
# No network, no credentials, no live Hermes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
if command -v python3.11 >/dev/null 2>&1; then
  PY=python3.11
elif command -v python3.12 >/dev/null 2>&1; then
  PY=python3.12
else
  PY=python3
fi
echo "using $PY ($($PY --version 2>&1))"
exec "$PY" -m unittest \
  tests.omnis_wing.test_admission_v0 \
  tests.omnis_wing.test_absolute_r1 \
  tests.omnis_wing.test_r2_chat_path \
  -v
