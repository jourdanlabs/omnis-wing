# OMNIS WING · production-cutover leg · READY_FOR_GATE

**Builder:** Videl  
**Independent gate:** Bulma  
**Date:** 2026-08-07  
**Verdict:** `READY_FOR_GATE` (never self-CLEAR)  
**Scope:** production signer wiring + private ledger + agent-flag non-trust on the WING fork  
**Not:** full TERMINUS ABSOLUTE · not live Hermes cutover · no Keychain mutation in this gate

## Pins (exact — do not collapse)

| Item | Value |
|---|---|
| Branch | `omnis-wing/v0-admission` |
| **Implementation commit** (signer attach runtime) | `9608a6851fc7f674a10c4c2ee7c7849b27d94811` |
| **Handoff commit** (docs pin of that tip) | `f66e073e5c20ac1fb1e30e854b8f044077071071` |
| **HOLD repair commit** (this packet) | *(filled at commit)* |
| Prior completion CLEAR | `b25eecbea7e0b45bcecc69d6ee8ce69ebe8f4399` |
| Live Hermes (untouched) | `2213ea9fa73ab06cf667c1bfb1e99c8de3541589` |
| Captain Keychain tag | `ai.jourdanlabs.omnis-wing.terminus.r4` |

Do **not** call the implementation commit the handoff tip, or the handoff tip the implementation.

## Bulma HOLD repairs addressed

### 1. Handoff identity
Table above separates `9608a685…` (implementation) from `f66e073…` (handoff docs). Repair tip is a third pin.

### 2. Production ledger private + fail closed
- New ledger dirs: `0700`
- New ledger files: `0600`
- Refuse pre-existing group/world-accessible ledger_dir (no chmod repair)
- Refuse symlink ledger_dir / ledger file
- Refuse wrong owner on controlled paths
- Config file `ledger_dir` is authoritative (ambient `OMNIS_WING_LEDGER_DIR` does not override file)
- Unsafe ledger → `UnavailableSigner` / REFUSE before provider (`client 0`)

### 3. Production does not trust mutable agent flags
In `OMNIS_WING_SIGNER_MODE=production`:
- Always rebuild from explicit production config (force attach)
- `wing_runtime_attached`, `wing_evidence_session`, `wing_ledger_path` cannot permit a send
- Planted test signer/session → REFUSE_POLICY_INVALID, client 0
- Test evidence only via explicit `OMNIS_WING_SIGNER_MODE=test`

## Cold command / output

```sh
cd ~/projects/omnis-wing && ./scripts/run_omnis_wing_v0_tests.sh
# Ran 92 tests in ~59s
# OK (skipped=1)
```

### Can-fail (this leg + HOLD)

| Control | Result |
|---|---|
| production, no config | REFUSE, client 0 |
| keychain, bridge missing | REFUSE, client 0 |
| P-256 enrolled + private ledger | client 1; chain valid; fp + algorithm in health |
| terminal fsync fail after send | client 1; OUTCOME_UNKNOWN |
| auto_enroll true in config | ProductionConfigError |
| explicit test mode | permit with test signer |
| preexisting **0755** ledger dir | REFUSE, client 0; mode unchanged |
| **symlink** ledger_dir | REFUSE, client 0 |
| fresh production ledger | dir **0700**, file **0600** |
| planted test session + attached=True in production | REFUSE, client 0 |

## Operator commands (no auto-enroll on startup)

```bash
cd ~/projects/omnis-wing && export PYTHONPATH=.

python -m omnis_wing.operator_cli compile-bridge --out-dir .omnis-wing-build

python -m omnis_wing.operator_cli status \
  --backend keychain \
  --tag ai.jourdanlabs.omnis-wing.terminus.r4 \
  --bridge .omnis-wing-build/omnis_wing_keychain

# EXPLICIT enroll only when Captain authorizes (mutates Keychain — not run here):
# python -m omnis_wing.operator_cli enroll --backend keychain \
#   --tag ai.jourdanlabs.omnis-wing.terminus.r4 \
#   --bridge .omnis-wing-build/omnis_wing_keychain

python -m omnis_wing.operator_cli health \
  --backend keychain \
  --tag ai.jourdanlabs.omnis-wing.terminus.r4 \
  --bridge .omnis-wing-build/omnis_wing_keychain \
  --ledger ~/.omnis-wing/ledgers/production/wing-production-ledger.jsonl \
  --root .

python -m omnis_wing.operator_cli coverage
```

Production chat (after enroll + config copy):

```bash
export OMNIS_WING_PRODUCTION_CONFIG=/path/to/production.yaml
export OMNIS_WING_SIGNER_MODE=production
./scripts/hermes-wing-prod chat
```

## Non-claims

- Live `~/.hermes/hermes-agent` not modified
- No live provider in cold suite
- No Keychain enroll/delete/rotate/export by builder
- Not full TERMINUS ABSOLUTE / whole-tree / Chinese-model safety cert

## Builder statement

`READY_FOR_GATE` for Bulma on **production-cutover + HOLD repairs only**.

🫡 + 🔑 — Videl
