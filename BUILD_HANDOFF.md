# BUILD_HANDOFF — OMNIS WING v0 admission harness

**Final status: `READY_FOR_GATE`**

Builder: Videl  
Date: 2026-08-07  
Repo: `~/projects/omnis-wing`  
Branch: `omnis-wing/v0-admission`

This is candidate evidence for an independent Bulma re-gate.  
It is **not** shipped, packaged, pushed, or a claim that TERMINUS / workstation protection is complete.

---

## 1. CADMUS input SHA-256

```
b92d45d70cef12e1e123504c9465088b67ad8158161a85172d726336f3850de4
```

Path (admitted in-tree): `omnis_wing/spec/omnis-wing-v0.cadmus-input.json`  
Authority source: `~/projects/pan-cc/cadmus-runs/2026-08-07-omnis-suite-full/wing-v0/omnis-wing-v0.cadmus-input.json`

---

## 2. Base source

| Field | Value |
|---|---|
| Upstream URL | `https://github.com/NousResearch/Hermes-Agent.git` |
| Base commit | `2213ea9fa73ab06cf667c1bfb1e99c8de3541589` |
| Acquisition | `git clone` of local `~/.hermes/hermes-agent` **object database only** → clean tree at pinned commit. Dirty live worktree files and untracked `.omniskey-runtime/` were **not** copied. |

---

## 3. Fork identity

| Field | Value |
|---|---|
| Introduction / fork_commit (admission) | `204a6a302af5e47d63de7e948e735f97a7d84e44` |
| HEAD at handoff | *(see `git rev-parse HEAD` in gate shell; must have fork_commit as ancestor)* |
| Branch | `omnis-wing/v0-admission` |
| `git status --short` at handoff | clean after commits below (re-check at gate) |

Admission manifest: `OMNIS_WING_ADMISSION.json`  
`fork_commit` = first commit introducing the harness (stable ancestor), **not** a self-hashing HEAD pin.

---

## 4. Files changed (vs base) and why

| Path | Why |
|---|---|
| `omnis_wing/boundary.py` | Action envelope, evaluate rules, `decide_and_maybe_call`, counting stub provider, receipts |
| `omnis_wing/host_dispatch.py` | Sole host entry that forwards to boundary |
| `omnis_wing/transport_guard.py` | AST import/transport guard for forbidden https/provider modules |
| `omnis_wing/__init__.py` | Package exports |
| `omnis_wing/spec/omnis-wing-v0.cadmus-input.json` | Admitted CADMUS authority copy |
| `tests/omnis_wing/test_admission_v0.py` | Cold controls: allow, CN refuse, missing provenance, bypass plant, admission identity |
| `scripts/run_omnis_wing_v0_tests.sh` | One cold command |
| `OMNIS_WING_ADMISSION.json` | Product / upstream / fork / CADMUS binding |
| `BUILD_HANDOFF.md` | This document |

No edits under live `~/.hermes/hermes-agent`.  
No `.env`, Keychain, sessions, profiles, or `.omniskey-runtime` content read or copied.

---

## 5. Cold commands + results

```sh
cd ~/projects/omnis-wing
./scripts/run_omnis_wing_v0_tests.sh
```

Observed (builder cold run):

```
test_00_cadmus_spec_digest ... ok
test_01_ordinary_allowed_generic_control ... ok
test_02_protected_cn_refusal_zero_provider_calls ... ok
test_03_protected_missing_provenance_zero_calls ... ok
test_04_transport_guard_clean_on_package ... ok
test_05_planted_direct_https_import_breaks_guard ... ok
test_06_fork_admission_manifest_identity ... ok
test_07_no_flattering_decision_language ... ok
Ran 8 tests ... OK
```

Proof shape:

| Control | Result |
|---|---|
| generic + allowed US route | `SENT`, stub calls **1** |
| protected + project source + CN | `REFUSED_BEFORE_SEND`, stub calls **0** |
| protected + missing provenance | `REFUSED_BEFORE_SEND`, stub calls **0** |
| planted `import httpx` | transport guard violations observed |
| admission identity | CADMUS sha, upstream commit, fork ancestor chain |

---

## 6. Can-fail controls actually observed

1. Protected CN project path never increments stub call counter.  
2. Missing project digest never increments stub call counter.  
3. Direct `httpx` plant produces guard failures.  
4. Wrong/missing CADMUS binding would fail `test_00` / `test_06`.  
5. Receipt decision language limited to `REFUSED_BEFORE_SEND` | `SENT` only.

---

## 7. Non-claims (blunt)

- **Not** a rename or replacement of the live Hermes/Videl environment.  
- **Not** TERMINUS-complete, not workstation-wide DLP, not all-plugin coverage.  
- **Not** wired into production Hermes conversation loop / real providers.  
- **Not** authorized to call MiniMax, Kimi, OpenAI, CADUCEUS, or any live router.  
- **Not** a credential, session, or memory migration.  
- **Not** packaged, notarized, published, or pushed to a public remote.  
- **Not** mobile approval, channel automation, or production readiness.  
- v0 **only** allows the explicit generic non-CN path through the stub; protected project traffic is refused even on non-CN until a later contract expands that allowlist honestly.

---

## Live tree attestation (builder)

After build, live `~/.hermes/hermes-agent` remained at  
`2213ea9fa73ab06cf667c1bfb1e99c8de3541589` with the same dirty paths  
(`cli.py`, `package-lock.json`, `tools/transcription_tools.py`, untracked `.omniskey-runtime/`).  
No clean/reset/copy was performed on that tree.

---

## Gate ask

Independent re-run:

```sh
cd ~/projects/omnis-wing
git status --short
git rev-parse HEAD
git merge-base --is-ancestor 2213ea9fa73ab06cf667c1bfb1e99c8de3541589 HEAD && echo base_ok
./scripts/run_omnis_wing_v0_tests.sh
```

Status for admission: **READY_FOR_GATE**.

🫡 + 🔑  
— Videl
