#!/usr/bin/env bash
# Cold OMNIS WING tests — W0 admission + R1 ABSOLUTE-shaped controls.
# No network, no credentials, no live Hermes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest tests.omnis_wing.test_admission_v0 tests.omnis_wing.test_absolute_r1 -v
