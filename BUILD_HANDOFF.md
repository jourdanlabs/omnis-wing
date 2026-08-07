# BUILD_HANDOFF — OMNIS WING R3.1.1 durable pre-send (fsync)

**Final status: `READY_FOR_GATE`**

Builder: Videl  
Date: 2026-08-07  
Prior HOLD: `c69e69638fce8129ed19aa4ef683f75fd3395cbf`  
HEAD: *(gate: `git rev-parse HEAD`)*

## CADMUS (unchanged)

SHA-256: `6f7563d2bfe9f3dc752c5d395ed153a6fb944332ad5f56ae84bc64a4af202f23`

## Repair

`EvidenceLedger.append()` now:
1. writes the signed receipt line  
2. `flush()`  
3. **`os.fsync(fileno)`** before return  

Pre-send path cannot reach `broker.transmit()` until that `fsync` returns successfully.

On fsync/append OSError:
- process-visible write is **truncated-rolled-back** to prior size (no flattering buffered-only pre-send left in-file for this process)
- raises `EvidencePersistError` → join maps pre-send fail to `REFUSE_POLICY_INVALID` / client 0; terminal fail to `OutcomeUnknownError` / client 1 with durable pre-send retained

`ensure_appendable()` probes write+fsync capability early; **authority remains the actual pre-send append+fsync**.

## Can-fails

| Inject | Observed |
|---|---|
| fsync fail on pre-send (call 1) | `REFUSE_POLICY_INVALID`, client 0, ledger entries `[]` |
| fsync fail on terminal (call 2) | `OutcomeUnknownError`, client 1, one `TRANSMISSION_STARTED`, report `OUTCOME_UNKNOWN` |

Prior R3/R3.1 can-fails retained. Cold **46/46 OK**.

## Non-claims

Unchanged: selected non-stream path only; fixture anchor not production witness; no live Hermes/Keychain/network/HSM/package; fsync is local filesystem durability not remote replication.

**READY_FOR_GATE**

🫡 + 🔑  
— Videl
