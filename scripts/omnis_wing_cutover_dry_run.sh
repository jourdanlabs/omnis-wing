#!/usr/bin/env bash
# OMNIS WING real-work cutover preflight. Never edits live Hermes or this tree.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
VENV_PY="${OMNIS_WING_VENV_PY:-$HOME/.hermes/hermes-agent/venv/bin/python}"
cd "$ROOT"

if [[ ! -x "$VENV_PY" ]]; then
  echo "missing Python runtime: $VENV_PY" >&2
  exit 127
fi
if [[ -z "${OMNIS_WING_PRODUCTION_CONFIG:-}" ]]; then
  echo "OMNIS_WING_PRODUCTION_CONFIG is required" >&2
  exit 2
fi
if [[ -z "${OMNIS_WING_REAL_WORK_CONFIG:-}" ]]; then
  echo "OMNIS_WING_REAL_WORK_CONFIG is required" >&2
  exit 2
fi

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export OMNIS_WING_SIGNER_MODE=production

"$VENV_PY" - <<'PY'
from pathlib import Path
from omnis_wing.absolute.broker_guard import (
    assert_no_agent_governed_bypass,
    assert_real_work_local_transport_only,
)
from omnis_wing.absolute.real_work.admission import assert_contract_not_drifted

root = Path.cwd().resolve()
assert_contract_not_drifted()
assert_no_agent_governed_bypass(root)
assert_real_work_local_transport_only(root)
print("WING_SOURCE_GUARDS_OK")
PY

"$VENV_PY" -m omnis_wing.absolute.real_work.launcher ensure >/dev/null
"$VENV_PY" -m omnis_wing.absolute.real_work.launcher preflight >/dev/null
"$VENV_PY" -m omnis_wing.operator_cli coverage >/dev/null

echo "WING_DOGFOOD_PREFLIGHT_OK"
