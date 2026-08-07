#!/usr/bin/env bash
# OMNIS WING cutover dry-run — Path A. Does NOT modify ~/.hermes/hermes-agent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LIVE_AGENT="${HERMES_LIVE_AGENT:-$HOME/.hermes/hermes-agent}"
DOGFOOD_HOME="${OMNIS_WING_DOGFOOD_HOME:-$HOME/.hermes/omnis-wing-dogfood}"
LEDGER_DIR="$DOGFOOD_HOME/ledgers"
STATE_DIR="$DOGFOOD_HOME/operator-state"
mkdir -p "$DOGFOOD_HOME" "$LEDGER_DIR" "$STATE_DIR"

if command -v python3.11 >/dev/null 2>&1; then PY=python3.11
elif command -v python3.12 >/dev/null 2>&1; then PY=python3.12
else PY=python3; fi
# Prefer live Hermes venv for import-heavy checks (deps present); suite still uses PY
VENV_PY="$LIVE_AGENT/venv/bin/python"
if [[ -x "$VENV_PY" ]]; then RUNTIME_PY="$VENV_PY"; else RUNTIME_PY="$PY"; fi

export WING_ROOT="$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export HERMES_HOME="$DOGFOOD_HOME"
export OMNIS_WING_LEDGER_DIR="$LEDGER_DIR"
unset OMNIS_WING_SIGNER_MODE || true

echo "== OMNIS WING cutover dry-run (Path A) =="
echo "ROOT=$ROOT"
echo "DOGFOOD_HOME=$DOGFOOD_HOME"
echo "LIVE_AGENT=$LIVE_AGENT (must not be written)"

# 1) live tree must remain non-target — record hash before/after
if [[ -d "$LIVE_AGENT/.git" ]]; then
  BEFORE="$(git -C "$LIVE_AGENT" rev-parse HEAD 2>/dev/null || echo none)"
  BEFORE_STAT="$(git -C "$LIVE_AGENT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  echo "live_HEAD_before=$BEFORE porcelain_lines=$BEFORE_STAT"
else
  BEFORE=missing
  BEFORE_STAT=0
  echo "live agent git missing — skip live hash check"
fi

# 2) cold suite
echo "== cold suite =="
./scripts/run_omnis_wing_v0_tests.sh

# 3) product default refuse (no test signer)
echo "== product default signer refuse =="
"$RUNTIME_PY" - <<'PY'
import os, sys, tempfile
from types import SimpleNamespace
sys.path.insert(0, os.environ["WING_ROOT"])
os.environ.pop("OMNIS_WING_SIGNER_MODE", None)
from omnis_wing.completion.side_doors import ensure_side_doors_armed
from omnis_wing.absolute.auto_provenance import resolve_evidence_session
from omnis_wing.absolute.receipt_spine import UnavailableSigner
from omnis_wing.absolute.hermes_chat_join import WingRefusal
from agent.chat_completion_helpers import interruptible_api_call

st = ensure_side_doors_armed()
assert st.complete, st.as_dict()
sess = resolve_evidence_session(None)
assert isinstance(sess.signer, UnavailableSigner), type(sess.signer)
assert sess.signer.available() is False

class C:
    is_fake = True
    def __init__(self):
        self.base_url = "https://ai.example.test/v1"
        self.create_calls = 0
        self.chat = self
    @property
    def completions(self):
        return self
    def create(self, **k):
        self.create_calls += 1
        return SimpleNamespace(id="x")
    def close(self):
        pass

class A:
    def __init__(self, c):
        self.api_mode = "chat_completions"
        self._client = c
        self._interrupt_requested = False
        self.log_prefix = "dry"
        self.provider = "stub"
        self.base_url = c.base_url
        self._codex_stream_last_event_ts = None
        self._codex_stream_last_progress_ts = None
    def _create_request_openai_client(self, **k):
        return self._client
    def _abort_request_openai_client(self, *a, **k):
        pass
    def _close_request_openai_client(self, *a, **k):
        pass
    def _compute_non_stream_stale_timeout(self, k):
        return 30.0
    def _touch_activity(self, m=""):
        pass
    def _buffer_status(self, m=""):
        pass

c = C()
try:
    interruptible_api_call(A(c), {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0})
    raise SystemExit("expected WingRefusal")
except WingRefusal as e:
    assert e.receipt.decision == "REFUSE_POLICY_INVALID", e.receipt.decision
assert c.create_calls == 0
print("PRODUCT_DEFAULT_REFUSE_OK")
PY

# 4) dogfood test-signer permit (labeled) — fake client only
echo "== dogfood test-signer permit (fake client) =="
OMNIS_WING_SIGNER_MODE=test OMNIS_WING_FORCE_CLASSIFICATION=generic "$RUNTIME_PY" - <<'PY'
import os, sys
from types import SimpleNamespace
sys.path.insert(0, os.environ["WING_ROOT"])
os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"
from agent.chat_completion_helpers import interruptible_api_call

class C:
    is_fake = True
    def __init__(self):
        self.base_url = "https://ai.example.test/v1"
        self.create_calls = 0
        self.chat = self
        self.last = None
    @property
    def completions(self):
        return self
    def create(self, **k):
        self.create_calls += 1
        self.last = k
        return SimpleNamespace(id="ok", choices=[SimpleNamespace(message=SimpleNamespace(content="pong"))])
    def close(self):
        pass

class A:
    def __init__(self, c):
        self.api_mode = "chat_completions"
        self._client = c
        self._interrupt_requested = False
        self.log_prefix = "dry"
        self.provider = "stub"
        self.base_url = c.base_url
        self._codex_stream_last_event_ts = None
        self._codex_stream_last_progress_ts = None
    def _create_request_openai_client(self, **k):
        return self._client
    def _abort_request_openai_client(self, *a, **k):
        pass
    def _close_request_openai_client(self, *a, **k):
        pass
    def _compute_non_stream_stale_timeout(self, k):
        return 30.0
    def _touch_activity(self, m=""):
        pass
    def _buffer_status(self, m=""):
        pass

c = C()
resp = interruptible_api_call(A(c), {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0})
assert c.create_calls == 1, c.create_calls
assert resp is not None
print("DOGFOOD_TEST_SIGNER_PERMIT_OK")
PY

# 5) importlib side-door still refused under dogfood home
echo "== importlib side-door refuse =="
"$RUNTIME_PY" - <<'PY'
import os, sys, importlib
sys.path.insert(0, os.environ["WING_ROOT"])
from omnis_wing.completion.side_doors import ensure_side_doors_armed
from omnis_wing.completion.product_disable import WingRouteDisabled
ensure_side_doors_armed()
sys.modules.pop("tools.transcription_tools", None)
mod = importlib.import_module("tools.transcription_tools")
try:
    mod.transcribe_audio("/tmp/x.ogg")
    raise SystemExit("expected refuse")
except WingRouteDisabled:
    print("IMPORTLIB_SIDE_DOOR_REFUSE_OK")
PY

# 6) coverage surface
echo "== coverage =="
"$RUNTIME_PY" -m omnis_wing.operator_cli coverage | head -40

# 7) live tree unchanged
if [[ -d "$LIVE_AGENT/.git" ]]; then
  AFTER="$(git -C "$LIVE_AGENT" rev-parse HEAD 2>/dev/null || echo none)"
  AFTER_STAT="$(git -C "$LIVE_AGENT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  echo "live_HEAD_after=$AFTER porcelain_lines=$AFTER_STAT"
  if [[ "$BEFORE" != "$AFTER" ]]; then
    echo "FAIL: live hermes-agent HEAD changed during dry-run" >&2
    exit 1
  fi
  if [[ "$BEFORE_STAT" != "$AFTER_STAT" ]]; then
    echo "FAIL: live hermes-agent porcelain changed during dry-run" >&2
    exit 1
  fi
  echo "LIVE_HERMES_UNTOUCHED_OK"
fi

# 8) write dogfood launcher (does not replace ~/.local/bin/hermes)
LAUNCHER="$ROOT/scripts/hermes-wing"
VENV_PY="$LIVE_AGENT/venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  VENV_PY="$PY"
fi
cat > "$LAUNCHER" << LAUNCH
#!/usr/bin/env bash
# Dogfood launcher — Path A. Does not replace live hermes.
set -euo pipefail
ROOT="$ROOT"
export PYTHONPATH="\$ROOT\${PYTHONPATH:+:\$PYTHONPATH}"
export HERMES_HOME="\${HERMES_HOME:-$DOGFOOD_HOME}"
export OMNIS_WING_LEDGER_DIR="\${OMNIS_WING_LEDGER_DIR:-$LEDGER_DIR}"
# Product default: no disposable signer. For labeled dogfood only:
#   OMNIS_WING_SIGNER_MODE=test hermes-wing ...
exec "$VENV_PY" "\$ROOT/cli.py" "\$@"
LAUNCH
chmod +x "$LAUNCHER"
echo "wrote launcher $LAUNCHER"

echo ""
echo "DRY_RUN_OK path=A root=$ROOT dogfood=$DOGFOOD_HOME"
echo "Next: Keychain enroll is Captain-explicit; live replace is Path C only."
