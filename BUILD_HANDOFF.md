# BUILD_HANDOFF — OMNIS WING R2: one real chat path

**Final status: `READY_FOR_GATE`**

Builder: Videl  
Date: 2026-08-07  
Repo: `~/projects/omnis-wing`  
Base: `be071263da794a65b6dfd8b4e16ab9f9d3ba54e7` (R1.1)  
HEAD at handoff: *(gate: `git rev-parse HEAD`)*

---

## 1. CADMUS authority (R2)

| Field | Value |
|---|---|
| Path | `omnis_wing/spec/omnis-wing-r2-live-chat-path.cadmus-input.json` |
| SHA-256 | `c12e0cb582634fca8a5bec1f5468c50cb82cf80b9661287a602acfb96d7396dd` |

R1 authority unchanged: `b4dcb959ddda7a0ac488817e65fed255a31da6e077c20596d90d62fe0e121805`

---

## 2. Selected real call chain

Ordinary **non-streaming** OpenAI-compatible user chat path (default `api_mode` / `chat_completions`):

```text
AIAgent._interruptible_api_call  (run_agent.py forwarder)
  → agent.chat_completion_helpers.interruptible_api_call
    → _call() else-branch  # not codex / anthropic / bedrock
      → agent._create_request_openai_client(reason="chat_completion_request")
      → omnis_wing.absolute.hermes_chat_join.governed_chat_completions_create
           messages → canonical JSON bytes = OutboundEnvelope.payload_bytes
           → dispatch_outbound / decide_and_execute (R1.1 evaluator)
           → ChatCompletionsClientBroker.transmit
                → client.chat.completions.create(**api_kwargs with messages
                     re-loaded from envelope.payload_bytes ONLY)
```

**Not selected:** streaming (`interruptible_streaming_api_call`), `anthropic_messages`, `bedrock_converse`, `codex_responses`, auxiliary client, diagnostics-only helpers.

---

## 3. Files changed

| Path | Why |
|---|---|
| `omnis_wing/absolute/hermes_chat_join.py` | R2 sole join + fake-capable broker |
| `agent/chat_completion_helpers.py` | Replace direct `chat.completions.create` on selected branch with governed join |
| `omnis_wing/coverage/ai_egress_coverage_r1.json` | `governed_r2` + honest `outside_r2` labels |
| `omnis_wing/absolute/coverage.py` | Accept `outside_r2` status |
| `omnis_wing/transport_guard.py` | Guard R2 `omnis_wing/*` join module (not whole Hermes host file) |
| `omnis_wing/spec/omnis-wing-r2-live-chat-path.cadmus-input.json` | Admitted R2 authority |
| `tests/omnis_wing/test_r2_chat_path.py` | Real-path cold controls via `interruptible_api_call` |
| `tests/omnis_wing/test_absolute_r1.py` | Allow `outside_r2` in inherited statuses |
| `scripts/run_omnis_wing_v0_tests.sh` | python≥3.11 + R2 suite |
| `BUILD_HANDOFF.md` | This document |

Live `~/.hermes/hermes-agent`: **not modified**.

---

## 4. Payload equality boundary

**In claim:** `api_kwargs["messages"]` → compact UTF-8 JSON bytes = envelope payload = bytes re-delivered as `messages` to fake client.

**Outside R2 (explicitly not claimed equal):** HTTP/TLS framing, auth headers, `model` / `temperature` / `tools` / `extra_body` and other non-message kwargs, base_url path, provider SDK assembly.

---

## 5. Cold command + results

```sh
cd ~/projects/omnis-wing
./scripts/run_omnis_wing_v0_tests.sh
# uses python3.11+
```

Builder observation: **25/25 OK** (8 W0 + 11 R1/R1.1 + 6 R2).

| Control | Observed |
|---|---|
| protected project + CN via `interruptible_api_call` | `WingRefusal` / `REFUSE_RESIDENCY`, phase `NONE`, fake client **0** |
| missing provenance (no `wing_egress_context`) | `REFUSE_SOURCE_POLICY`, fake client **0** |
| generic + US destination | `PERMIT` path completes; fake client **1**; received message bytes == evaluated payload bytes |
| legacy direct `create` removed from selected branch | source assert; planted direct create is not the production join |
| R1.1 regression | all prior tests green |

Fake client evidence: `FakeClient.create_calls` and `received_messages_bytes` recorded in R2 tests.

---

## 6. Coverage delta

`governed_r2`:
- `omnis_wing/absolute/hermes_chat_join.py`
- `agent/chat_completion_helpers.py` (join site only; file still has upstream HTTP imports — import guard does **not** claim that file clean)

Everything else: `outside_r2` / inbound / ungoverned.  
`claims_all_hermes_chat_paths: false`  
`claims_whole_tree_ai_egress: false`

---

## 7. Non-claims (blunt)

- Not all Hermes chat paths, streaming, tools, MCP, images, retries, fallbacks.  
- Not live Videl/Hermes wiring, real providers, tokens, sessions.  
- Not TERMINUS ABSOLUTE complete; not receipt signing/chain.  
- Not full source-taint productization.  
- Not package/push.  
- Agent must set `wing_egress_context` with explicit provenance+destination; absent context refuses (by design on this path).

---

## 8. Live attestation

- Fork-only work under `~/projects/omnis-wing`.  
- `~/.hermes/hermes-agent` left dirty at base pin (pre-existing).  
- R2 tests set `HERMES_HOME` to a temp dir before imports so live profile is not used.

**READY_FOR_GATE**

🫡 + 🔑  
— Videl
