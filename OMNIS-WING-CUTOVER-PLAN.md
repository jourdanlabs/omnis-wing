# OMNIS WING · cutover plan (post-CLEAR)

**Cleared completion pin:** `b25eecbea7e0b45bcecc69d6ee8ce69ebe8f4399`  
**Completion BBB:** `b1326dc57f4dde5922406e2033d14b0487dc387ab791e9fdecd3282907ad0bd6`  
**Date:** 2026-08-07  
**Builder:** Videl · **Cutover gate:** Bulma (separate from completion CLEAR)

## Boundary (non-negotiable)

- Completion CLEAR ≠ live cutover.
- Do **not** overwrite `~/.omnis-wing/omnis-wing` while it is dirty / divergent without explicit Captain order + backup.
- No live provider burn required for dry-run.
- Captain Keychain: enroll only on explicit command; never delete/rotate/export in automation.
- Product default without production signer **refuses** AI send — cutover must include signer enroll or an explicitly labeled dogfood test-signer mode.

## Forced choice

### Path A — Isolated dogfood (recommended first)
- Code: `~/projects/omnis-wing` @ cleared pin (or tip ≥ CLEAR).
- Runtime home: fresh `WING_HOME` under `~/.omnis-wing/omnis-wing-dogfood/` (not default profile).
- Launcher: `scripts/wing-dogfood` → venv python + `PYTHONPATH=omnis-wing` first.
- Signer: dogfood may use `OMNIS_WING_SIGNER_MODE=test` **only** under that home, labeled dogfood; production path uses Keychain enroll.
- Live `wing` CLI + `~/.omnis-wing/omnis-wing` **unchanged**.
- **Exit:** dry-run green + smoke refuse/permit controls → READY_FOR_GATE cutover packet for Bulma on Path A only.

### Path B — Parallel install directory
- Copy/sync cleared tree to `~/.omnis-wing/omnis-wing-agent/` (sibling of live repo).
- Own venv; profile `wing` points at it.
- Still does not replace live `omnis-wing`.
- Heavier; use if Path A PYTHONPATH overlay is insufficient.

### Path C — Replace live `~/.omnis-wing/omnis-wing`
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

- Path A/B: stop using launcher; live `wing` unchanged.
- Path C: restore from backup zip; re-point `~/.local/bin/wing`.


## Path A try-it (same UX as live Videl)

```bash
wing-dogfood chat          # interactive (profile ~/.omnis-wing/profiles/videl-wing)
wing-dogfood chat -q "hi"  # one-shot
```

- Code: `~/projects/omnis-wing` via PYTHONPATH
- Profile: copy of videl config/auth/SOUL under `videl-wing` (isolated sessions)
- Live `wing` + `videl` profile unchanged
- Default `OMNIS_WING_SIGNER_MODE=test` (dogfood). After Keychain enroll, run with `OMNIS_WING_SIGNER_MODE=` empty for production posture.
- Smoke observed: `wing-dogfood chat -Q -q ...` → `WINGOK`

## Track B — `wing pan` (Cursor-polish, 2026-08-23)

**Status:** built on branch `toph/real-work-contract-parity` — not CLEAR, not committed here.

- **Command:** `./scripts/wing pan` (identity) · `./scripts/wing pan verify` · `./scripts/wing pan chat`
- **Identity source:** MTS-sealed `soul_bb75a9fa2823` at `~/projects/mts/souls/` (override: `MTS_SOULS_DIR` / `OMNIS_SOULS_DIR`). Soul text is **not** copied into the repo; runtime loads + verifies bedrock/chain, then stages to `~/.omnis-wing/profiles/pan-wing/SOUL.md` for chat.
- **Refusal:** missing package or tampered bedrock → refuse (no WING bread fallback).
- **Tests:** `tests/omnis_wing/test_pan_identity.py` (load + missing + tampered fixture + CLI path).
- **Still open:** live LLM chat smoke under `wing pan chat` (needs provider keys); memory-bridge recall from chamber vault not wired yet.
