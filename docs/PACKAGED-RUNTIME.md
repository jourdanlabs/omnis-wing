# Packaged runtime build path

The headless packaged runtime (`~/.omnis-wing/wing-r4/omnis-wing-runtime` and
successors) is built from **this repository's `main`**. It is not built from
`~/.hermes/hermes-agent` and it is not built from a Nous tarball.

## What it is

A bin/ + CADUCEUS process tree. Headless by nature — it does not embed the
Ink TUI. The TUI lives in `ui-tui/` and is launched with `./wing --tui` from
this checkout.

## Build

From a clone of `jourdanlabs/omnis-wing` on `main`:

```bash
# 1. Python product tests (OMNIS layer)
./scripts/run_omnis_wing_v0_tests.sh

# 2. Path A cutover dry-run (does not write ~/.hermes/hermes-agent)
./scripts/omnis_wing_cutover_dry_run.sh

# 3. Verify plan
node scripts/omnis-wing-verify-plan.mjs

# or the wrapper:
node scripts/omnis-wing-build.mjs
```

CADUCEUS-gated dogfood chat (requires production + real-work config):

```bash
export OMNIS_WING_PRODUCTION_CONFIG=...
export OMNIS_WING_REAL_WORK_CONFIG=...
./scripts/wing-dogfood
```

Install the operator CLI from this tree, not from a second checkout:

```bash
uv sync
# entrypoints: wing, omnis-wing-operator, omnis-wing-distribution
```

## Pin

Record the git SHA of `main` that produced the package in the runtime
manifest. A packaged tree whose SHA is not on `origin/main` is not WING.
