# OMNIS WING · R5–R7 TERMINUS convergence · READY_FOR_GATE

**Builder:** Videl  
**Independent gate:** Bulma  
**Date:** 2026-08-07  
**Verdict:** `READY_FOR_GATE` (never self-CLEAR)  

## Pins

| Item | Value |
|---|---|
| Branch | `omnis-wing/v0-admission` |
| **R5–R7 implementation** | `b5a668f52c3c6462204560d2262f937768cc3b12` |
| **R5–R7 handoff tip** | branch HEAD after this docs set — `git rev-parse HEAD` |
| Prior base | `acce399e12130b09be31728ad452148630b7c47e` |
| Live Hermes | `2213ea9fa73ab06cf667c1bfb1e99c8de3541589` **untouched** |
| CADMUS R5–R7 | `omnis_wing/spec/omnis-wing-r5-r7-terminus-convergence.cadmus-input.json` |
| CADMUS SHA-256 | `7cf045442eb4112eea7d9bfe7b4dff59087062ac30740801ad23e31fd5c42e79` |

## What shipped

### R5 — Automatic source policy (payload authority)
- New `omnis_wing/absolute/payload_policy.py`
- Every string field in the outbound body is walked and classified (messages, system, tools, extra_body, …)
- Content signals: secrets/credentials, protected markers, project/source-code/path fragments, unknown
- **Not** workspace folder-name theater as sole permit authority
- Wired into `build_envelope_for_chat` + `governed_callable_transmit`
- Unknown / project / protected / credential → refuse before provider
- Generic operator text still permits on allowlisted US/EU/LOCAL destinations
- Receipts/health hygiene: planted secret markers must not appear in receipt JSON

### R6 — Primary paths GOVERNED (or would be DISABLED — all five are GOVERNED joins)
| Path | Join |
|---|---|
| OpenAI-compatible non-stream | `governed_chat_completions_create` |
| OpenAI-compatible streaming | `governed_streaming_create` (pre-send ledger before provider call proven) |
| Anthropic | `governed_callable_transmit` |
| Bedrock | `governed_callable_transmit` |
| Codex | `governed_callable_transmit` |

Each: full-body canonicalize → payload policy → destination bind → signed+fsync pre-send → transmit → terminal; terminal fail → OUTCOME_UNKNOWN.

### R7 — Coverage / operator truth / adversarial
- Manifest routes only `GOVERNED` \| `DISABLED` (no omitted/unknown state)
- Health includes route_manifest summary + remote_anchor NOT_CONFIGURED + coverage boundary
- Adversarial: side-door reload, planted agent attrs in production, unsafe 0755 ledger

## Cold

```sh
cd ~/projects/omnis-wing && ./scripts/run_omnis_wing_v0_tests.sh
# Ran 112 tests · OK (skipped=1)
```

### Can-fails observed
| Control | Result |
|---|---|
| Secret in extra_body / message | REFUSE_SECRET, client 0 |
| Project/source in system or tools | REFUSE_SOURCE_POLICY, client 0 |
| Unknown provenance | REFUSE_SOURCE_POLICY, client 0 |
| Scanner failure inject | REFUSE_SCANNER_FAILURE |
| Destination mutation after auth | refuse, broker 0 |
| Stream secret | REFUSE, provider 0 |
| Stream pre-send before provider | ledger TRANSMISSION_STARTED before create |
| Anthropic/Bedrock/Codex joins | permit once under test signer |
| Planted production agent session | REFUSE, client 0 |
| Unsafe ledger dir 0755 | REFUSE, client 0 |
| Side-door after reload | still refuses |

## Route coverage table (primary AI)

| route_id | state |
|---|---|
| agent.interruptible.chat_completions.non_stream | GOVERNED |
| agent.interruptible_streaming.chat_completions | GOVERNED |
| agent.interruptible.anthropic_messages.non_stream | GOVERNED |
| agent.interruptible.bedrock_converse.non_stream | GOVERNED |
| agent.interruptible.codex_responses.non_stream | GOVERNED |
| agent.interruptible_streaming.anthropic | GOVERNED |
| agent.interruptible_streaming.bedrock_converse_stream | GOVERNED |
| (+ side doors) | DISABLED |

## Exact non-claims (what still blocks full TERMINUS ABSOLUTE)

1. **Not full TERMINUS ABSOLUTE** — selected WING fork surface only  
2. **Not live Hermes cutover** — `~/.hermes/hermes-agent` untouched  
3. **Not whole-tree / IDE / workstation egress governance**  
4. **Protected material is not safe to send to a Chinese remote provider** — WING refuses project/protected/credential on CN and refuses non-generic sources on the permit path; a separate **REDACT** path is not built; never silently forward protected bytes  
5. **No Keychain mutation / no live provider** in this cold suite  
6. **Messaging platforms / health probes** named out of model-payload AI claim  
7. **Dogfood test signer** still opt-in via `OMNIS_WING_SIGNER_MODE=test`

## Builder statement

`READY_FOR_GATE` for Bulma on **R5–R7 convergence only**.

🫡 + 🔑 — Videl
