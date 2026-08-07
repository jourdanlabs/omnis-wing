# BUILD_HANDOFF — OMNIS WING R4.1 algorithm-bound receipt verification

**Final status: `READY_FOR_GATE`**

Builder: Videl  
Prior HOLD: `dccf6c4ce2be2a001e67db1091b817fcc0b5c731`  
HEAD: *(gate: `git rev-parse HEAD`)*

## CADMUS (unchanged)

`a54c70e866a137e9513db3f99f2859dc6bf37873205bc4e2326a3355b8b52c86`

## P0 closed — production algorithm verifies

1. Receipt canonical body includes **`signature_algorithm`** (bound by digest+sig).
2. `verify_signed_receipt` / `verify_chain` dispatch by that field; unknown → fail-closed.
3. `ed25519-test` → pure Ed25519 (R3 + disposable backend).
4. `ecdsa-p256-x962-sha256` → P-256 ECDSA-SHA256 DER verify (`p256_crypto` / openssl).
5. Cold: `DisposableP256Backend` (openssl, not Keychain) → client 1, 2 entries, `chain_valid=True`, mutation → `INVALID`, remote anchor `NOT_CONFIGURED`.
6. Opt-in real Keychain IT (`OMNIS_WING_R4_KEYCHAIN_IT=1`): uses existing enrolled Captain tag only; no enroll/delete; builder observed **OK** on this machine.

## Cold

```sh
./scripts/run_omnis_wing_v0_tests.sh
# 59 tests, 1 skipped (Keychain IT) unless OMNIS_WING_R4_KEYCHAIN_IT=1
```

Builder: **58 OK + 1 skipped** (default cold); Keychain IT **OK** when opted in.

## Non-claims

Unchanged from R4. `UNVERIFIED_AT_READ` honesty preserved. Captain key not rotated/exported. Live Hermes untouched. Not full ABSOLUTE.

**READY_FOR_GATE**

🫡 + 🔑  
— Videl
