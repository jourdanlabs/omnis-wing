# Upstream policy

Canonical product tree: **this repository**, `jourdanlabs/omnis-wing`, branch `main`.

Not the product tree:

- `~/.hermes/hermes-agent` (Nous checkout the `hermes` command historically ran)
- `hermes-local` git remotes pointing at that checkout
- `hermes update` / any auto-pull from Nous into this working tree

## Remotes

| Remote | URL | Role |
|--------|-----|------|
| `origin` | `https://github.com/jourdanlabs/omnis-wing.git` | product |
| `upstream` | `https://github.com/NousResearch/hermes-agent.git` | Nous, **read-only** |

`upstream` stays. That is the attribution remote and the source of deliberate cherry-picks.

Do not add a remote that fetches Nous into `main` automatically. Do not rebase this tree onto Nous `main`.

## Security fixes

When Nous publishes a security fix:

1. `git fetch upstream`
2. Identify the commit(s).
3. `git cherry-pick <sha>` onto `main` (or a named branch, then merge).
4. Resolve conflicts as WING, not as a silent "take theirs".
5. Run the TUI launch check and the omnis_wing tests before pushing.

If a cherry-pick does not apply, stop. Do not `git merge upstream/main`.

## Updates users run

`./wing` in this repo. `git pull` from `origin`. There is no `hermes update` path that writes Nous HEAD into the product tree.

## Packaged runtime

`~/.omnis-wing/wing-r4/` (and later packaged builds) must be produced from this `main`. See `docs/PACKAGED-RUNTIME.md`.
