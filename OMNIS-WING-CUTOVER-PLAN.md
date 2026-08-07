# OMNIS WING · cutover plan (post-CLEAR)

**Cleared completion pin:** `b25eecbea7e0b45bcecc69d6ee8ce69ebe8f4399`  
**Completion BBB:** `b1326dc57f4dde5922406e2033d14b0487dc387ab791e9fdecd3282907ad0bd6`  
**Date:** 2026-08-07  
**Builder:** Videl · **Cutover gate:** Bulma (separate from completion CLEAR)

## Boundary (non-negotiable)

- Completion CLEAR ≠ live cutover.
- Do **not** overwrite `~/.hermes/hermes-agent` while it is dirty / divergent without explicit Captain order + backup.
- No live provider burn required for dry-run.
- Captain Keychain: enroll only on explicit command; never delete/rotate/export in automation.
- Product default without production signer **refuses** AI send — cutover must include signer enroll or an explicitly labeled dogfood test-signer mode.

## Forced choice

### Path A — Isolated dogfood (recommended first)
- Code: `~/projects/omnis-wing` @ cleared pin (or tip ≥ CLEAR).
- Runtime home: fresh `HERMES_HOME` under `~/.hermes/omnis-wing-dogfood/` (not default profile).
- Launcher: `scripts/hermes-wing` → venv python + `PYTHONPATH=omnis-wing` first.
- Signer: dogfood may use `OMNIS_WING_SIGNER_MODE=test` **only** under that home, labeled dogfood; production path uses Keychain enroll.
- Live `hermes` CLI + `~/.hermes/hermes-agent` **unchanged**.
- **Exit:** dry-run green + smoke refuse/permit controls → READY_FOR_GATE cutover packet for Bulma on Path A only.

### Path B — Parallel install directory
- Copy/sync cleared tree to `~/.hermes/omnis-wing-agent/` (sibling of live repo).
- Own venv; profile `wing` points at it.
- Still does not replace live `hermes-agent`.
- Heavier; use if Path A PYTHONPATH overlay is insufficient.

### Path C — Replace live `~/.hermes/hermes-agent`
- Full backup zip first.
- Only after Path A dogfood green **and** Captain explicit “replace live”.
- Highest blast radius (live tree is dirty + behind upstream).
- **Not default.**

**Builder vote:** Path A now. Path C only on explicit order after A is boring.

## Path A checklist

1. Pin code at CLEAR (or documented tip ≥ CLEAR).
2. `./scripts/run_omnis_wing_v0_tests.sh` green.
3. `./scripts/omnis_wing_cutover_dry_run.sh` green (no live tree writes).
4. Optional: Keychain production enroll via `python -m omnis_wing.operator_cli enroll --backend keychain ...` — **Captain-only, explicit**.
5. Dogfood chat smoke under isolated home (no claim of live replacement).
6. Handoff to Bulma: `OMNIS-WING-CUTOVER-HANDOFF.md` READY_FOR_GATE (cutover scope).

## Rollback

- Path A/B: stop using launcher; live `hermes` unchanged.
- Path C: restore from backup zip; re-point `~/.local/bin/hermes`.
