#!/usr/bin/env bash
# Seal a local proving artifact of the WING fork (source tree subset) and run
# the omnis_wing cold suite against it. Not a notarized package. Not live install.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="${1:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)}"
OUT="${OMNIS_WING_SEAL_DIR:-$ROOT/.omnis-wing-build/sealed-$STAMP}"
rm -rf "$OUT"
mkdir -p "$OUT"

# Copy proving surface only — no .git secrets, no live profiles
rsync -a \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude '.omnis-wing-build' \
  --exclude '.pytest_cache' \
  --exclude '.env' \
  --exclude '*.pyc' \
  "$ROOT/omnis_wing" "$ROOT/tests/omnis_wing" "$ROOT/agent" "$ROOT/scripts" \
  "$ROOT/tools" "$ROOT/wing_cli" "$ROOT/gateway" "$ROOT/plugins" \
  "$ROOT/cron" \
  "$OUT/" 2>/dev/null || {
  # fallback without rsync
  for d in omnis_wing tests/omnis_wing agent scripts tools wing_cli gateway plugins cron; do
    if [[ -e "$ROOT/$d" ]]; then
      mkdir -p "$OUT/$(dirname "$d")"
      cp -R "$ROOT/$d" "$OUT/$d"
    fi
  done
}

# identity
{
  echo "schema=omnis-wing.sealed-artifact.v0"
  echo "source_root=$ROOT"
  echo "seal_dir=$OUT"
  echo "git_head=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "sealed_at_unix=$(date +%s)"
  echo "note=local_proving_artifact_not_notarized_not_live_install"
} >"$OUT/SEAL_IDENTITY.txt"

# content digest of omnis_wing tree (sorted paths)
(
  cd "$OUT"
  if command -v shasum >/dev/null 2>&1; then
    find omnis_wing -type f | LC_ALL=C sort | while read -r f; do
      shasum -a 256 "$f"
    done | shasum -a 256 | awk '{print $1}'
  else
    echo "no-shasum"
  fi
) >"$OUT/SEAL_TREE_SHA256.txt"

export OMNIS_WING_SIGNER_MODE="${OMNIS_WING_SIGNER_MODE:-test}"
export PYTHONPATH="$OUT${PYTHONPATH:+:$PYTHONPATH}"
export WING_HOME="${WING_HOME:-$(mktemp -d -t wing-seal-home)}"
export OMNIS_WING_LEDGER_DIR="${OMNIS_WING_LEDGER_DIR:-$WING_HOME/led}"

if command -v python3.11 >/dev/null 2>&1; then PY=python3.11
elif command -v python3.12 >/dev/null 2>&1; then PY=python3.12
else PY=python3; fi

echo "SEAL_DIR=$OUT"
echo "SEAL_TREE_SHA256=$(cat "$OUT/SEAL_TREE_SHA256.txt")"
echo "running cold suite against sealed artifact with $PY"

# Prefer full runner if present at source (uses source scripts paths)
cd "$ROOT"
if [[ -x "$ROOT/scripts/run_tests.sh" ]]; then
  # run tests from source paths but PYTHONPATH=sealed first so imports resolve to seal
  PYTHONPATH="$OUT:$ROOT" "$ROOT/scripts/run_tests.sh" tests/omnis_wing/ 2>&1 | tee "$OUT/SEAL_TEST_OUTPUT.txt"
else
  PYTHONPATH="$OUT:$ROOT" "$PY" -m unittest discover -s tests/omnis_wing -v 2>&1 | tee "$OUT/SEAL_TEST_OUTPUT.txt"
fi

echo "SEAL_OK path=$OUT"
