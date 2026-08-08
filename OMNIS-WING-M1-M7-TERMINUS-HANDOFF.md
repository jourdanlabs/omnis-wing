# OMNIS WING × TERMINUS ABSOLUTE · M1–M7 build pass · READY_FOR_GATE

**Builder:** Videl  
**Independent gate:** Bulma  
**Verdict:** `READY_FOR_GATE` — **not** self-CLEAR  
**Not claimed:** `TERMINUS ABSOLUTE COMPLETE`

## Authority

| Doc | Path | SHA-256 |
|---|---|---|
| TA 1.0 | `omnis_wing/spec/authority/BULMA-TERMINUS-ABSOLUTE-1.0.md` | `51c7a364fcdd2c73cdd052f31adbdbcef703a8d42ca4d02bf21e303e9f08f77f` |
| FULL CADMUS | `omnis_wing/spec/authority/BULMA-VIDEL-WING-TERMINUS-ABSOLUTE-FULL-CADMUS-2026-08-07.md` | `01394e6ab916bb901ceb72d632422b9767bcf271a3317abab6f043765acefb6f` |
| Finish BBB (superseded brief) | `omnis_wing/spec/authority/BULMA-VIDEL-WING-ABSOLUTE-FINISH-BBB-2026-08-07.md` | `0aea3d2d2e6c5cd21119f9c58e0bab18ff41b6a4c47d418db2cac24a6d524adf` |
| M1–M7 CADMUS input | `omnis_wing/spec/omnis-wing-m1-m7-terminus-absolute.cadmus-input.json` | `0f578b80374aeb1d78c1604071dfc814e2e26037e6501ce28d61b4abe589b2ad` |

## Pins

| Item | Value |
|---|---|
| Branch | `omnis-wing/v0-admission` |
| Starting impl (R5–R7) | `b5a668f52c3c6462204560d2262f937768cc3b12` |
| Starting head | `8b65e15eafa9ac1152c0eb450a293a071e1d5479` |
| **This implementation** | *(filled at commit)* |
| Live Hermes | `2213ea9fa73ab06cf667c1bfb1e99c8de3541589` **untouched** |

## Cold

```sh
cd ~/projects/omnis-wing && ./scripts/run_omnis_wing_v0_tests.sh
# Ran 133 tests · OK (skipped=1)
```

## Milestone delivery (built + cold-proved)

| M | Module(s) | Proven can-fails |
|---|---|---|
| **M1** | `source_taint.py` + join wiring | secret w/o filename; protected fragment; concat/summary inherit; split-secret reform; repo breadth; `.env` read taint |
| **M2** | `transport_broker.py` | broker chat path; manifest only GOVERNED\|DISABLED |
| **M3** | evaluator + envelope (prior R5–R7 retained) | CN project zero bytes; destination mutation; decision grammar + `REFUSE_REPO_BREADTH` |
| **M4** | `redact.py` | local preview strips secrets; `sends_nothing=True`; confirm body is new request only |
| **M5** | `external_anchor.py` | `REMOTE_ANCHOR_NOT_CONFIGURED` honest; local double catches ledger replacement |
| **M6** | `signed_policy.py` + `glass.py` | enforce default; `off` forbidden; glass RED without signer; policy digest in health |
| **M7** | `preflight.py` | test-mode preflight OK; `deny_all` blocks |

## Fixed claim language (allowed)

> TERMINUS-oriented controls on this WING fork decide supported AI transmissions before the first outbound byte on governed joins, refuse disallowed payloads/destinations, and produce secret-free evidence — **within the WING-owned route manifest**.

## Exact non-claims / remaining ship-blockers vs full TA 1.0 matrix

These prevent saying **TERMINUS ABSOLUTE COMPLETE** from this pass:

1. **Not sealed install-artifact conformance** — cold suite runs against source tree / PYTHONPATH fork, not a packaged immutable artifact (M7 package/seal incomplete).
2. **Not every modality in zero-tolerance matrix** — image/embedding/audio end-to-end hostile corpus not fully GOVERNED as product features (many remain DISABLED side-doors by design; contract forbids flipping to DISABLED only to pass counts — product still does not ship those modalities as GOVERNED).
3. **Not live production cutover** — live Hermes untouched; no Captain-approved live smoke.
4. **Not remote anchor production** — anchor is honest NOT_CONFIGURED / local test double only.
5. **Not Secure Enclave attestation claim**.
6. **Not workstation/IDE/terminal/browser/Git governance**.
7. **Not “safe to send raw protected code to Chinese models”** — refuse/local/REDACT only.
8. **Scanner P50/P95/P99 + benign-corpus refusal budget** — not frozen/measured in this pass.
9. **Static whole-tree transport sweep CI gate** for any new provider client — partial (side-door arming + broker facade), not exhaustive AST ban of all HTTP clients.
10. **Builder is not sole judgment gate** — awaiting Bulma.

## Operator surfaces

```bash
cd ~/projects/omnis-wing && PYTHONPATH=. python -m omnis_wing.operator_cli coverage
PYTHONPATH=. python -m omnis_wing.operator_cli health --ledger ~/.omnis-wing/ledgers/wing-completion-ledger.jsonl --root . --backend test --tag ai.jourdanlabs.omnis-wing.test.r4
# glass + policy + remote_anchor fields present in health JSON
```

## Builder statement

M1–M7 **implementation spine + cold can-fails** are in-tree and green (133).  
This is **`READY_FOR_GATE`** for Bulma independent re-gate of the M1–M7 pass.  
**Not** `TERMINUS ABSOLUTE COMPLETE`. **Not** CLEAR.

🫡 + 🔑 — Videl
