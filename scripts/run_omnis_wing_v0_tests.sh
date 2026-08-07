#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export OMNIS_WING_SIGNER_MODE="${OMNIS_WING_SIGNER_MODE:-test}"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
if command -v python3.11 >/dev/null 2>&1; then PY=python3.11
elif command -v python3.12 >/dev/null 2>&1; then PY=python3.12
else PY=python3; fi
echo "using $PY ($($PY --version 2>&1))"
exec "$PY" -m unittest \
  tests.omnis_wing.test_admission_v0 \
  tests.omnis_wing.test_absolute_r1 \
  tests.omnis_wing.test_r2_chat_path \
  tests.omnis_wing.test_r3_evidence_spine \
  tests.omnis_wing.test_r4_production_signer_health \
  tests.omnis_wing.test_completion_routes \
  tests.omnis_wing.test_completion_disabled \
  tests.omnis_wing.test_completion_p0_repair \
  tests.omnis_wing.test_production_cutover \
  tests.omnis_wing.test_r5_r6_r7_convergence \
  -v
