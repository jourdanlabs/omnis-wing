# BUILD_HANDOFF — OMNIS WING R1.1 ABSOLUTE-shaped host slice

**Final status: `READY_FOR_GATE`**

Builder: Videl  
Date: 2026-08-07  
Repo: `~/projects/omnis-wing`  
Prior: R1 @ `10a97a214f` strong seam, **HOLD H6** (empty `path_class` permitted)

## R1.1 statement

H6 closed. Destination completeness now requires non-empty, strip-normalized `path_class`. Empty / whitespace-only endpoint class → `REFUSE_DESTINATION`, `phase=NONE`, broker calls `0`. Destination-mutation control unchanged. Scope not expanded. Live Hermes not touched.

This is still **not** full TERMINUS ABSOLUTE certification.

---

## 1. CADMUS authority (R1 — unchanged)

| Field | Value |
|---|---|
| Path | `omnis_wing/spec/omnis-wing-r1-absolute.cadmus-input.json` |
| SHA-256 | `b4dcb959ddda7a0ac488817e65fed255a31da6e077c20596d90d62fe0e121805` |

---

## 2. Base / fork

| Field | Value |
|---|---|
| Upstream | `https://github.com/NousResearch/Hermes-Agent.git` |
| Base commit | `2213ea9fa73ab06cf667c1bfb1e99c8de3541589` |
| W0 intro fork_commit | `204a6a302af5e47d63de7e948e735f97a7d84e44` |
| R1 candidate (pre-H6) | `10a97a214f64e78c51543cdf1f918d42df978f57` |
| R1.1 repair commit | `7cce236286c64d1f7750a5c05eb7d99c7f23cf54` |
| HEAD at handoff | `7cce236286c64d1f7750a5c05eb7d99c7f23cf54` (plus handoff commit if present) |
| Live Hermes | **untouched** |

---

## 3. R1.1 delta (files)

| Path | Change |
|---|---|
| `omnis_wing/absolute/evaluator.py` | Require non-empty stripped `path_class` → else `REFUSE_DESTINATION` |
| `tests/omnis_wing/test_absolute_r1.py` | `test_06b_empty_path_class_refuse_destination_zero_calls` (`''`, `'   '`, `'\t'`) |
| `BUILD_HANDOFF.md` | This R1.1 statement |

---

## 4. Cold commands + results

```sh
cd ~/projects/omnis-wing
./scripts/run_omnis_wing_v0_tests.sh
```

Builder observation: **19/19 OK** (8 W0 + 11 R1/R1.1).

| Control | Observed |
|---|---|
| protected project → CN | `REFUSE_RESIDENCY`; stub 0 |
| missing/invalid provenance | `REFUSE_SOURCE_POLICY`; stub 0 |
| planted secret | `REFUSE_SECRET`; no cleartext/bare-sha; stub 0 |
| scanner failure | `REFUSE_SCANNER_FAILURE`; stub 0 |
| allowed generic | bytes equal; `AUTHORIZED→STARTED→COMPLETED` |
| destination mutation | `REFUSE_DESTINATION`; stub 0 |
| **empty/blank path_class (H6)** | **`REFUSE_DESTINATION`; phase NONE; stub 0** |
| planted `httpx` | guard fails |
| coverage manifest | honest; whole-tree false |

---

## 5. Non-claims (unchanged, blunt)

- Not TERMINUS ABSOLUTE complete.  
- Not receipt signing/chain/anchor (H5).  
- Not full source-taint propagation.  
- Not full inherited-Hermes AI-egress classification.  
- Not live Hermes/Videl wiring, real providers, package, push.  
- Not workstation DLP / all modalities.

---

## 6. Gate re-run

```sh
cd ~/projects/omnis-wing
git status --short
git rev-parse HEAD
./scripts/run_omnis_wing_v0_tests.sh
# expect 19/19 OK including test_06b_empty_path_class_refuse_destination_zero_calls
```

**READY_FOR_GATE** for R1.1 destination-binding repair only.

🫡 + 🔑  
— Videl
