# OMNIS WING · production-cutover leg · READY_FOR_GATE

**Builder:** Videl  
**Independent gate:** Bulma  
**Date:** 2026-08-07  
**Verdict:** `READY_FOR_GATE` (never self-CLEAR)  
**Scope:** production signer wiring on the WING fork — **not** full TERMINUS ABSOLUTE, **not** live Hermes cutover

## Pins

| Item | Value |
|---|---|
| Branch | `omnis-wing/v0-admission` |
| Tip | 9608a6851fc7f674a10c4c2ee7c7849b27d94811 |
| Completion CLEAR (prior) | `b25eecbea7e0b45bcecc69d6ee8ce69ebe8f4399` |
| Live Hermes (untouched) | `2213ea9fa73ab06cf667c1bfb1e99c8de3541589` |
| Captain Keychain tag | `ai.jourdanlabs.omnis-wing.terminus.r4` |

## What this leg builds

1. **Explicit operator config** (`OMNIS_WING_PRODUCTION_CONFIG` or env):
   - `backend: keychain`
   - `tag: ai.jourdanlabs.omnis-wing.terminus.r4`
   - `ledger_dir` explicit
   - `bridge_path` optional
   - `auto_enroll: false` required (startup never enrolls)
2. **Runtime attach** (`omnis_wing.absolute.runtime_attach`):
   - compile/read Keychain bridge path when configured
   - `MacOSKeychainBackend` + `ProductionSignerAdapter` (or cold `disposable_p256`)
   - attach `wing_production_signer` + `EvidenceSession`/ledger on agent at `init_agent` and before dispatch
3. **No test-signer fallback** in production mode
4. **hermes-wing-prod** requires production config; dogfood `hermes-wing` still defaults test only when no production config

## Cold command / output

```sh
cd ~/projects/omnis-wing && ./scripts/run_omnis_wing_v0_tests.sh
# Ran 88 tests · OK (skipped=1)
```

### Can-fail table (this leg)

| Control | Result |
|---|---|
| production mode, no config | REFUSE_POLICY_INVALID, client 0 |
| keychain config, bridge missing | refuse, client 0 |
| disposable P-256 enrolled (cold) | client 1; P-256 signed chain valid; health shows fingerprint + algorithm |
| terminal evidence fail after send | provider called; OUTCOME_UNKNOWN path |
| `auto_enroll: true` in config | ProductionConfigError |
| `OMNIS_WING_SIGNER_MODE=test` | explicit only; permit with test signer |

## Operator commands (no auto-enroll on startup)

```bash
cd ~/projects/omnis-wing
export PYTHONPATH=.

# 1) Compile Keychain bridge (operator machine)
python -m omnis_wing.operator_cli compile-bridge --out-dir .omnis-wing-build

# 2) Status (read-only; does not enroll)
python -m omnis_wing.operator_cli status \
  --backend keychain \
  --tag ai.jourdanlabs.omnis-wing.terminus.r4 \
  --bridge .omnis-wing-build/omnis_wing_keychain

# 3) EXPLICIT enroll only when Captain authorizes (mutates Keychain — not run by builder gate)
# python -m omnis_wing.operator_cli enroll \
#   --backend keychain \
#   --tag ai.jourdanlabs.omnis-wing.terminus.r4 \
#   --bridge .omnis-wing-build/omnis_wing_keychain

# 4) Health / verify (secret-free)
python -m omnis_wing.operator_cli health \
  --backend keychain \
  --tag ai.jourdanlabs.omnis-wing.terminus.r4 \
  --bridge .omnis-wing-build/omnis_wing_keychain \
  --ledger ~/.omnis-wing/ledgers/production/wing-production-ledger.jsonl \
  --root .

python -m omnis_wing.operator_cli verify \
  --backend keychain \
  --tag ai.jourdanlabs.omnis-wing.terminus.r4 \
  --bridge .omnis-wing-build/omnis_wing_keychain \
  --ledger ~/.omnis-wing/ledgers/production/wing-production-ledger.jsonl \
  --root .

python -m omnis_wing.operator_cli coverage
```

### Production config example

Copy `omnis_wing/config/production.example.yaml` → private path, then:

```bash
export OMNIS_WING_PRODUCTION_CONFIG=/path/to/production.yaml
export OMNIS_WING_SIGNER_MODE=production
# after explicit enroll:
./scripts/hermes-wing-prod chat
```

## Non-claims

- Live `~/.hermes/hermes-agent` not modified; not production-cut-over as default `hermes`
- No live provider calls in this leg’s cold suite
- No Keychain enroll/delete/rotate/export by builder automation
- Not full TERMINUS ABSOLUTE; not whole-tree AI egress; not Chinese-model safety cert
- Dogfood test signer remains opt-in via `OMNIS_WING_SIGNER_MODE=test` only

## Builder statement

`READY_FOR_GATE` for Bulma on **production-cutover wiring only**.

🫡 + 🔑 — Videl
