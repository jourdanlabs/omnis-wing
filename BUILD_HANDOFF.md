# BUILD_HANDOFF — OMNIS WING R3: evidence spine

**Final status: `READY_FOR_GATE`**

Builder: Videl  
Date: 2026-08-07  
Repo: `~/projects/omnis-wing`  
Base: `2ede5a1b25fbc2763041cf1347a3f7b49cf98676` (R2.1)  
HEAD: *(gate: `git rev-parse HEAD`)*

## CADMUS

| Field | Value |
|---|---|
| Path | `omnis_wing/spec/omnis-wing-r3-evidence-spine.cadmus-input.json` |
| SHA-256 | `6f7563d2bfe9f3dc752c5d395ed153a6fb944332ad5f56ae84bc64a4af202f23` |

## What R3 adds

Fail-closed cryptographic evidence on the **already governed R2.1** non-stream chat path:

1. **Signer abstraction** — `Signer` protocol; `Ed25519TestSigner` (pure-Python Ed25519, test-only); `UnavailableSigner`.
2. **Missing signer** → `REFUSE_POLICY_INVALID` **before** broker/client call (fake client 0).
3. **Signed secret-free receipt** — envelope digest, decision, phase, policy/coverage, actual destination/provider/residency, findings correlation digest (IDs only), previous digest, sequence, key_id, receipt_digest, Ed25519 signature.
4. **Append-only ledger** — JSONL with sequence + previous-digest + signature verification.
5. **External anchor fixture** — binds chain head; whole-ledger replacement fails anchor verify.
6. **Integrated** into `governed_chat_completions_create` via `WingEgressContext.evidence` (`EvidenceSession`).

## Cold proof

```sh
cd ~/projects/omnis-wing
./scripts/run_omnis_wing_v0_tests.sh
```

Builder: **39/39 OK**.

| Can-fail | Observed |
|---|---|
| One-byte receipt/sig mutation | `verify_signed_receipt` false |
| Ledger replaced with fresh chain | `verify_anchor` → `anchor_head_mismatch` |
| Signer unavailable | `REFUSE_POLICY_INVALID`, client 0 |
| Planted secret | absent from exception, receipt, ledger, anchor; no bare SHA-256 marker |
| Protected CN + generic permit | still green **with signed evidence** on selected path |
| R1.1 / R2.1 regression | green |

## Files

| Path | Role |
|---|---|
| `omnis_wing/absolute/ed25519_pure.py` | Offline Ed25519 |
| `omnis_wing/absolute/receipt_spine.py` | Sign / ledger / anchor |
| `omnis_wing/absolute/hermes_chat_join.py` | Evidence session + fail-closed signer gate |
| `tests/omnis_wing/test_r3_evidence_spine.py` | R3 can-fails |
| `omnis_wing/spec/omnis-wing-r3-evidence-spine.cadmus-input.json` | Authority |
| coverage / runner / BUILD_HANDOFF | honesty + cold command |

Live Hermes / Keychain / network: **not touched**.

## Non-claims

- Not production Keychain / Secure Enclave enrollment.  
- Not retro-signing legacy rows; not “whole product ledger globally signed.”  
- Not streaming / other provider paths / full ABSOLUTE cert.  
- Not live Videl wiring, real providers, package, push.  
- Pure-Python Ed25519 is **test/offline spine**, not an HSM claim.

**READY_FOR_GATE**

🫡 + 🔑  
— Videl
