#!/usr/bin/env bash
# Cold OMNIS WING v0 admission tests — no network, no credentials, no live Hermes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m unittest tests.omnis_wing.test_admission_v0 -v
