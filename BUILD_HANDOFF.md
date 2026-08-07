# BUILD_HANDOFF — OMNIS WING R1 ABSOLUTE-shaped host slice

**Final status: `READY_FOR_GATE`**

Builder: Videl  
Date: 2026-08-07  
Repo: `~/projects/omnis-wing`  
Prior gate: W0 ADMISSION PROTOTYPE CLEAR @ `a9baf33a`; TERMINUS ABSOLUTE HOST was HOLD (H1–H5)

This is **not** full TERMINUS ABSOLUTE certification. It is the next provable host slice Bulma ordered.

---

## 1. CADMUS authority (R1)

| Field | Value |
|---|---|
| Path | `omnis_wing/spec/omnis-wing-r1-absolute.cadmus-input.json` |
| SHA-256 | `b4dcb959ddda7a0ac488817e65fed255a31da6e077c20596d90d62fe0e121805` |
| Scope bind | ABSOLUTE-shaped R1 seam only — does not imply full ABSOLUTE certification |

W0 authority `b92d45d7…` remains historical for the admission prototype.

---

## 2. Base / fork

| Field | Value |
|---|---|
| Upstream | `https://github.com/NousResearch/Hermes-Agent.git` |
| Base commit | `2213ea9fa73ab06cf667c1bfb1e99c8de3541589` |
| W0 intro fork_commit | `204a6a302af5e47d63de7e948e735f97a7d84e44` |
| HEAD at handoff | *(gate: `git rev-parse HEAD`)* |
| Live Hermes | **untouched** (`~/.hermes/hermes-agent` still dirty at base pin) |

---

## 3. What R1 added

| Path | Role |
|---|---|
| `omnis_wing/absolute/envelope.py` | Immutable `OutboundEnvelope` + source provenance + destination |
| `omnis_wing/absolute/scanner.py` | Deterministic local scan of **exact** payload bytes |
| `omnis_wing/absolute/evaluator.py` | ABSOLUTE decisions + phase machine + `RecordingBroker` |
| `omnis_wing/absolute/host.py` | Sole R1 host entry |
| `omnis_wing/absolute/coverage.py` | Coverage manifest loader |
| `omnis_wing/coverage/ai_egress_coverage_r1.json` | Honest governed vs outside_r1 map |
| `omnis_wing/transport_guard.py` | Extended to all R1-governed modules |
| `tests/omnis_wing/test_absolute_r1.py` | Required cold controls |
| `scripts/run_omnis_wing_v0_tests.sh` | Runs W0 + R1 |

### Decision grammar (H1)

`PERMIT`, `REFUSE_RESIDENCY`, `REFUSE_SOURCE_POLICY`, `REFUSE_SECRET`, `REFUSE_SCANNER_FAILURE`, `REFUSE_DESTINATION`, `REFUSE_POLICY_INVALID`, `REFUSE_CROWN_JEWEL`

### Phase grammar (separate)

`AUTHORIZED` → `TRANSMISSION_STARTED` → `TRANSMISSION_COMPLETED`  
Failures: `FAILED_AFTER_TRANSMISSION_STARTED`, `OUTCOME_UNKNOWN`  
Refusals: `phase=NONE`, provider calls **0**

### Envelope (H2)

`envelope_id`, modality, lane, canonical `payload_bytes` + `payload_digest`, sources (classification, content digest, protected_root, crown_jewel, byte_range/whole_content), intended_destination (provider, scheme, hostname, port, path_class, residency), policy_version, coverage_class.

---

## 4. Cold commands + results

```sh
cd ~/projects/omnis-wing
./scripts/run_omnis_wing_v0_tests.sh
```

Builder observation: **18/18 OK** (8 W0 + 10 R1).

| Control | Observed |
|---|---|
| protected project → CN | `REFUSE_RESIDENCY`; stub 0 |
| missing/invalid provenance | `REFUSE_SOURCE_POLICY`; stub 0 |
| planted secret in payload | `REFUSE_SECRET`; no cleartext/bare-sha in receipt; stub 0 |
| injected scanner failure | `REFUSE_SCANNER_FAILURE`; stub 0 |
| allowed generic | evaluated bytes == broker bytes; phases reach `TRANSMISSION_COMPLETED` after stub return |
| destination mutation after auth | `REFUSE_DESTINATION`; stub 0 |
| planted direct `httpx` import | governed-module guard fails |
| coverage manifest | all governed R1 modules listed+present; inherited Hermes transport `outside_r1`/`inbound`/`ungoverned`; `claims_whole_tree_ai_egress=false` |

---

## 5. Scope map / glass

Active boundary string for R1:

- `AI EGRESS GOVERNED (R1 seam only)`
- Also true: `WORKSTATION EGRESS NOT GOVERNED`
- IDE-owned egress: not claimed

Inherited Hermes tree still contains many HTTP/provider imports (**not** auto-defects). Manifest labels them outside R1. No “sole outbound entry for the whole fork” claim.

---

## 6. Non-claims (blunt)

- **Not** TERMINUS ABSOLUTE complete / certified host.  
- **Not** receipt signing, hash chain, or external anchor (H5 still open).  
- **Not** full source-taint propagation through tool graphs / crown-jewel product corpus beyond R1 flags.  
- **Not** fork-wide AI egress coverage (669 imports remain unclassified).  
- **Not** live Hermes/Videl wiring, real providers, credentials, package, push.  
- **Not** workstation DLP.  
- W0 `SENT` grammar remains historical on the admission prototype path; R1 path does not use `SENT` as a decision.

---

## 7. Gate re-run

```sh
cd ~/projects/omnis-wing
git status --short
git rev-parse HEAD
git merge-base --is-ancestor 2213ea9fa73ab06cf667c1bfb1e99c8de3541589 HEAD && echo base_ok
./scripts/run_omnis_wing_v0_tests.sh
# optional
python3 - <<'PY'
from pathlib import Path
from hashlib import sha256
p=Path('omnis_wing/spec/omnis-wing-r1-absolute.cadmus-input.json')
t=p.read_text(encoding='utf-8').replace('\r\n','\n').replace('\r','\n')
if t.startswith('\ufeff'): t=t[1:]
print(sha256(t.encode()).hexdigest())
PY
# expect b4dcb959ddda7a0ac488817e65fed255a31da6e077c20596d90d62fe0e121805
```

**READY_FOR_GATE** for R1 ABSOLUTE-shaped slice only.

🫡 + 🔑  
— Videl
