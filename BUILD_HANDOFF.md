# BUILD_HANDOFF — OMNIS WING R4 production signer + operator health

**Final status: `READY_FOR_GATE`**

Builder: Videl  
Date: 2026-08-07  
Base: `13c5a7febc2d7593e4c3a8d3f4d2c134d634023e` (R3.1.1 CLEAR)  
HEAD: *(gate: `git rev-parse HEAD`)*

## CADMUS

Path: `omnis_wing/spec/omnis-wing-r4-production-signer-health.cadmus-input.json`  
SHA-256: `a54c70e866a137e9513db3f99f2859dc6bf37873205bc4e2326a3355b8b52c86`

## What shipped

1. **Production signer adapter contract** (`production_signer.py`)
   - `MacOSKeychainBackend` — subprocess to Swift Security bridge (operator-compiled)
   - `DisposableTestBackend` — cold tests only; refuses Captain production tag
   - `ProductionSignerAdapter` — Signer protocol; **no enroll in `__init__`/startup**

2. **Explicit enrollment**
   - `python -m omnis_wing.operator_cli enroll --backend test|keychain --tag <tag>`
   - `status` / `health` / `compile-bridge` subcommands
   - Startup / chat path never enrolls, rotates, deletes, or exports

3. **Selected path wiring**
   - Missing / not enrolled / sign failure → existing pre-send gate → `REFUSE_POLICY_INVALID`, client 0
   - R3.1.1 fsync pre-send still required after enroll

4. **Offline health/verifier** (`operator_health.py` + CLI `health`)
   - enrollment state, key_id, public fingerprint
   - chain valid/invalid, signed vs unsigned counts
   - coverage boundary
   - remote anchor **`NOT_CONFIGURED`** unless local fixture explicitly passed (never green remote)
   - `storage_state` honesty: no invented `hardware_backed: true`

5. **Swift bridge** committed as source (`omnis_wing_keychain.swift`) — Bulma probe seed. Captain tag `ai.jourdanlabs.omnis-wing.terminus.r4` **untouched** by tests.

## Operator commands

```sh
# cold / disposable
python -m omnis_wing.operator_cli status --backend test --tag ai.jourdanlabs.omnis-wing.test.r4
python -m omnis_wing.operator_cli enroll --backend test --tag ai.jourdanlabs.omnis-wing.test.r4
python -m omnis_wing.operator_cli health --backend test --tag ai.jourdanlabs.omnis-wing.test.r4 \
  --ledger /path/to/ledger.jsonl --root .

# production (explicit; operator machine)
python -m omnis_wing.operator_cli compile-bridge
python -m omnis_wing.operator_cli status --backend keychain --tag ai.jourdanlabs.omnis-wing.terminus.r4
# enroll only when Captain intentionally asks — not part of cold gate
python -m omnis_wing.operator_cli health --backend keychain --tag ai.jourdanlabs.omnis-wing.terminus.r4 \
  --ledger /path/to/ledger.jsonl --root .
```

## Cold proof

```sh
cd ~/projects/omnis-wing
./scripts/run_omnis_wing_v0_tests.sh
```

Builder: **56/56 OK**

| Can-fail | Observed |
|---|---|
| no enrolled signer | `REFUSE_POLICY_INVALID`, client 0 |
| signer error | `REFUSE_POLICY_INVALID`, client 0 |
| ledger mutation | health `verifier=INVALID`, chain_valid false |
| unconfigured anchor | `NOT_CONFIGURED`, never green remote |
| planted secret | absent from health/receipt/exception/filenames |
| Captain tag on test backend | refused at construct |
| R1–R3.1.1 | green |

## Non-claims

- Not live Keychain enrollment in tests; Captain key untouched  
- Not live Hermes wiring, package, push, network, remote anchor replication  
- Not full ABSOLUTE / whole-tree egress  
- Not claiming SE hardware from `UNVERIFIED_AT_READ`  
- Disposable test backend ≠ production Keychain  
- Bridge compile is operator-side; cold suite does not require swiftc  

**READY_FOR_GATE** (builder does not self-CLEAR)

🫡 + 🔑  
— Videl
