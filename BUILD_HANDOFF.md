# BUILD_HANDOFF — OMNIS WING R3.1 evidence integrity repair

**Final status: `READY_FOR_GATE`**

Builder: Videl  
Date: 2026-08-07  
Repo: `~/projects/omnis-wing`  
Prior HOLD candidate: `89fcf619ca0a57ba788b1e20e64495ed9490a8b7`  
HEAD: *(gate: `git rev-parse HEAD`)*

## CADMUS (unchanged)

`omnis_wing/spec/omnis-wing-r3-evidence-spine.cadmus-input.json`  
SHA-256: `6f7563d2bfe9f3dc752c5d395ed153a6fb944332ad5f56ae84bc64a4af202f23`

## P0-A closed — non-canonical Ed25519 rejected

`ed25519_pure.verify` now rejects `S >= L` before the group equation (RFC 8032).

Can-fail: valid signature mutated with `S' = S + L` → `verify == False` and `verify_signed_receipt == False`.

## P0-B closed — no unrecorded provider call

Selected path flow:

1. Signer available + ledger `ensure_appendable` (else `REFUSE_POLICY_INVALID`, client 0)
2. Evaluate ABSOLUTE decision (no client)
3. On PERMIT: durable signed **pre-send** receipt `phase=TRANSMISSION_STARTED`, append ledger (else refuse, client 0)
4. `broker.transmit` / client.create
5. Durable signed **terminal** `TRANSMISSION_COMPLETED`
6. If terminal sign/append fails after step 4 → `OutcomeUnknownError` (not success): client 1, pre-send remains verifiable, `ledger_outcome_report` → `OUTCOME_UNKNOWN` / `terminal_missing=true`. No fabricated SENT/COMPLETED.

Can-fails:

| Case | Observed |
|---|---|
| `available()` True, `sign()` raises pre-send | `REFUSE_POLICY_INVALID`, client 0, empty ledger |
| Ledger not appendable pre-send | `REFUSE_POLICY_INVALID`, client 0 |
| Provider returns, terminal sign fails | `OutcomeUnknownError`, client 1, pre-send signed, report OUTCOME_UNKNOWN |
| Prior R3 can-fails | retained green |

## Cold

```sh
./scripts/run_omnis_wing_v0_tests.sh
```

Builder: **44/44 OK**.

## Anchor wording

Local `write_anchor` remains a **test-fixture external-anchor file**, not a production independent witness / HSM enrollment. Non-claim unchanged.

## Non-claims (unchanged)

Selected non-stream chat path only. No live Hermes, provider, Keychain, network, production HSM, package, push, or full ABSOLUTE verdict. Pure-Python Ed25519 is offline test spine, not SE.

**READY_FOR_GATE**

🫡 + 🔑  
— Videl
