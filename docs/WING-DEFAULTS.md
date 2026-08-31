# OMNIS WING — shipped defaults

These are the defaults a fresh clone shows. Changing them is a product decision.

## Look

The shipped default Ink TUI / CLI skin is **WING blue**:

- Ink: `ui-tui/src/theme.ts` `DARK_THEME` (`#7eb8f6` on `#151C2F`)
- CLI: `wing_cli/skin_engine.py` built-in skin `default` (`description: "OMNIS WING — cool blue"`)

Gold-on-navy (`#FFD700` on `#1a1a2e`) is the optional **`gold`** skin. It is not the default. Captain signed the blue frame 2026-08-31.

## Model

First-run / TUI fallback is `moonshotai/kimi-k2.6` (`wing_constants.DEFAULT_INFERENCE_MODEL`).

Not Anthropic. Not `claude-sonnet-4`. When CADUCEUS is configured, the lane routes this via Fireworks US. A fresh profile without CADUCEUS still must not display a Claude slug.

## Named `hermes` / `nous` exceptions

`grep -ri 'hermes\|nous'` on a clean clone is allowed to hit only:

| Location | Why it stays |
|---|---|
| `LICENSE` | Upstream MIT copyright |
| `NOTICE` | Required attribution + legacy path names |
| README opening attribution paragraph + upstream URL | Required one-line credit |
| `docs/UPSTREAM-POLICY.md` | Names the forbidden auto-pull |
| `wing_constants.py` | Must name `~/.hermes` to migrate it |
| `tools/approval.py`, `tools/threat_patterns.py`, `tools/skills_guard.py` | Guard old operator scripts / attack paths |
| Raw model slugs (`openrouter/hermes3:70b`, `NousResearch/Wing-3-…`) | Changing them breaks inference |
| `scripts/release.py` contributor emails | Historical identities |
| `git remote upstream` → `NousResearch/hermes-agent` | Cherry-pick path |
| `portal.nousresearch.com` / `wing setup --portal` | Live OAuth host for the optional Portal provider |
| `wing_cli/model_switch.py` non-agentic warning | Warns about those upstream slugs |
