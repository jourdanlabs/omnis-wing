# STALE CANDIDATE BANNER — READ FIRST

**DO NOT GATE:** `e480339cce…` (old install) **nor** `30759cc880…` (builtins-hook-only arming)  
That tip still has blanket side-door install + `_INSTALLED=True` on partial failure. Bulma HOLD on that SHA is correct **for that SHA only**.

**GATE THIS TIP INSTEAD:** `69280700a57347f59e599f473aff6083eaaf941c`  
**P0-B mechanism commit:** `752559f326f74be9fc098ac2582d4f5a5352e3d0`  
**Authority BBB:** `b1326dc57f4dde5922406e2033d14b0487dc387ab791e9fdecd3282907ad0bd6`

On the gate tip:
- joins call `ensure_side_doors_armed()` with **no** install `except: pass`
- deny at `tools.registry.register` / `.dispatch`
- **`importlib.import_module` + `builtins.__import__` + `importlib.reload` wrapped** (product discovery path)
- module DISABLED routes eagerly patched or deny-stubbed; ARMED only when entrypoints refuse — **hook presence alone is not coverage**
- `complete` only when every declared DISABLED route is ARMED/NAMED_OK
- forced unresolved → `SideDoorArmingError`
- fresh process importlib of every module DISABLED route → refuse before provider
- P0-A product default signer refuse preserved
- Builder does **not** self-CLEAR

---

# OMNIS WING COMPLETION HANDOFF

**Builder verdict: `READY_FOR_GATE`** (never self-CLEAR)  
**HOLD repairs applied:** P0-A product default refuses without production signer (test signer opt-in only). P0-B side-door arming is fail-closed at `tools.registry` register/dispatch + **importlib.import_module** (not builtins-only); `ensure_side_doors_armed()` raises `SideDoorArmingError` if any declared DISABLED route is unresolved; no blanket except-pass; incomplete install never reports complete. P1 handoff hygiene + real IT command. Fresh-process can-fails included.
  
**Builder:** Videl  
**Independent gate:** Bulma  
**Date:** 2026-08-07  

## Authority

| Item | Value |
|---|---|
| Completion BBB | `omnis_wing/spec/OMNIS-WING-COMPLETION-BBB.md` |
| BBB SHA-256 | `b1326dc57f4dde5922406e2033d14b0487dc387ab791e9fdecd3282907ad0bd6` |
| Start pin | `89ccebae7922cab0645ecb4e8d145eb5d8a469c5` (R4.1 CLEAR) |
| Feature ship commit | `a8cd6c89e940bf2158d0ed3a73c1b0e1f97cdf7a` |
| P0-B mechanism commit | `69280700a57347f59e599f473aff6083eaaf941c` |
| Repo tip at handoff | `69280700a57347f59e599f473aff6083eaaf941c` |

## Captain outcome (plain English)

OMNIS WING now puts **one governed door** in front of the primary agent AI paths (chat completions non-stream + stream, Anthropic, Bedrock, Codex) with:

- automatic workspace provenance (no “sensitive mode” for Captain to remember);
- full-body canonical scan + real endpoint bind;
- signed + fsync pre-send evidence before provider call;
- terminal evidence or `OUTCOME_UNKNOWN`;
- algorithm-bound verify (Ed25519 test / P-256 production).

AI **side-doors** that were not safely fully wired (vision, TTS, transcription, MoA, image/video gen plugins, auxiliary fanout, CLI ad-hoc model calls, mini_swe, trajectory compressor) are **product-DISABLED** with an accurate `OMNIS_WING_ROUTE_DISABLED` refusal — not silent bypasses.

Messaging-platform HTTP and named health probes without user payload are listed in the manifest as non-model or named probes — not unexplained exemptions.

## Route manifest

Machine-readable: `omnis_wing/completion/route_manifest.json`

| State | Count (as shipped) |
|---|---|
| GOVERNED | 10 |
| DISABLED | 13 |

Forbidden states `outside` / `later` / unexplained exemption: **none**.

### GOVERNED (primary)

- `agent.interruptible.chat_completions.non_stream`
- `agent.interruptible.anthropic_messages.non_stream`
- `agent.interruptible.bedrock_converse.non_stream`
- `agent.interruptible.codex_responses.non_stream`
- `agent.interruptible_streaming.chat_completions`
- `agent.interruptible_streaming.bedrock_converse_stream` (folded → governed non-stream converse)
- `agent.interruptible_streaming.anthropic` (folded → governed non-stream)
- `agent.iteration_limit_summary`
- `agent.anthropic_adapter.create_message`
- `health.provider_probe_no_user_payload` (named; must not carry workspace content)

### DISABLED (product refuse before transport)

vision, tts, transcription, mixture_of_agents, image_generation_tool, image_gen plugins, video_gen, hermes_cli goals/kanban/profile model calls, mini_swe_runner, trajectory_compressor, auxiliary_client fanout, gateway messaging (not model AI egress).

## Cold suite

```sh
cd ~/projects/omnis-wing
./scripts/run_omnis_wing_v0_tests.sh
```

Builder observation: **82 tests, 1 skipped** (Keychain IT unless `OMNIS_WING_R4_KEYCHAIN_IT=1`).

### Can-fail table (completion + retained spine)

| Control | Result |
|---|---|
| Auto provenance chat_completions permit (US) | client 1 |
| Project/auto + CN | refuse, client 0 |
| Secret in extra_body | refuse, client 0 |
| Codex / Anthropic modes via universal door | governed, client 1 |
| Empty sources explicit | REFUSE_SOURCE_POLICY, client 0 |
| Signer unavailable | REFUSE_POLICY_INVALID, client 0 |
| Pre-send / terminal fsync fails | refuse / OUTCOME_UNKNOWN |
| P-256 + Ed25519 algorithm bind | verify OK; mutation INVALID |
| DISABLED route assert | WingRouteDisabled |
| Product default no production signer | UnavailableSigner; REFUSE_POLICY_INVALID, client 0 |
| Real side-door handlers (_handle_vision_analyze, text_to_speech_tool, …) | WingRouteDisabled |
| Handoff hygiene planted marker | absent; real IT path present |
| Registry dispatch disabled tools | WingRouteDisabled, transport 0 |
| Fresh subprocess no dep stubs | ensure arms; dispatch refuse |
| Forced unresolved DISABLED route | SideDoorArmingError; complete=False |
| Manifest no outside/later | pass |
| BBB digest | pass |
| R1–R4.1 regression | green |

### Opt-in Keychain

```sh
OMNIS_WING_R4_KEYCHAIN_IT=1 python3.11 -m unittest \
  tests.omnis_wing.test_r4_production_signer_health.R4ProductionSignerHealthTests.test_12_opt_in_real_keychain_if_enrolled -v
```

Uses Captain tag read-only; no enroll/delete. `UNVERIFIED_AT_READ` honesty preserved.


## Operator workflow (no secrets)

```text
python -m omnis_wing.operator_cli status --backend test|keychain --tag …
python -m omnis_wing.operator_cli enroll --backend test|keychain --tag …   # explicit only
python -m omnis_wing.operator_cli health --ledger PATH --root .
python -m omnis_wing.operator_cli verify --ledger PATH --root .
python -m omnis_wing.operator_cli coverage
python -m omnis_wing.operator_cli compile-bridge
```

`coverage` prints every route GOVERNED/DISABLED + reasons.  
`health`/`verify` never green-wash invalid chains or missing enrollment; remote anchor stays `NOT_CONFIGURED` unless a local fixture is explicitly passed.

## Coverage statement

On this fork, model-bound traffic that still runs goes through the governed universal/chat join with auto provenance and the R3.1.1 evidence spine, or it hits a **hard product disable**. Captain does not pick a safety mode. Foreign/CN destinations cannot receive protected/project-derived or secret-shaped payloads on covered routes. This is a **completion candidate for the WING fork**, not a claim that live `~/.hermes/hermes-agent` is already switched over.

## Non-claims (exact)

- Live Hermes install not modified, not cut over, not configured.
- No live provider calls during build; no API keys/tokens inspected.
- Captain Keychain tag not deleted/rotated/exported; no false SE attestation.
- Remote anchor replication not implemented (`NOT_CONFIGURED`).
- DISABLED side-doors are not “done governed” — they are product-off until a future governed join.
- Anthropic/Bedrock **streaming UX** is folded to governed non-stream (no silent stream bypass); not a claim of token-delta streaming under the gate.
- Gateway messaging HTTP is not claimed as AI egress governance.
- Not full TERMINUS/ABSOLUTE certification of the entire universe of tools.
- No push, no package.

## Builder statement

`READY_FOR_GATE` for Bulma independent re-gate against the Completion BBB.  
**Not** builder-CLEAR.

🫡 + 🔑  
— Videl
