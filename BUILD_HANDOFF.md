# BUILD_HANDOFF — OMNIS WING R2.1 ABSOLUTE P0 repair

**Final status: `READY_FOR_GATE`**

Builder: Videl  
Date: 2026-08-07  
Repo: `~/projects/omnis-wing`  
Prior R2 head: `b6df780f1734e919cedb54e45a493ec3765431f6`  
HEAD at handoff: *(gate: `git rev-parse HEAD`)*

## R2.1 statement

Closed Bulma P0-A and P0-B on the selected non-stream `chat_completions` join only.

| P0 | Repair |
|---|---|
| **A** unscanned body fields | Envelope payload = deterministic canonical JSON of **entire** allowlisted provider request body. Broker reconstructs `create(**body)` from evaluated bytes only. Unknown fields → `REFUSE_UNSUPPORTED`. Secrets in `tools` / `extra_body` → `REFUSE_SECRET`, client 0. |
| **B** declared route bless | Destination derived from **actual** `client.base_url` + controlled `HOSTNAME_POLICY` (provider/residency). Optional `declared_destination` must match derived or `REFUSE_DESTINATION`. Claimed US + `api.moonshot.cn` → refuse, client 0. |

R2 CADMUS SHA **unchanged** (scope not expanded):  
`c12e0cb582634fca8a5bec1f5468c50cb82cf80b9661287a602acfb96d7396dd`

---

## Selected call chain (unchanged entry)

```text
interruptible_api_call → governed_chat_completions_create
  → canonical_provider_request_body(api_kwargs)  # ALL body fields
  → derive_destination_from_client(client.base_url)
  → OutboundEnvelope → dispatch_outbound
  → broker: create(**json.loads(envelope.payload_bytes))
```

---

## Cold proof

```sh
cd ~/projects/omnis-wing
./scripts/run_omnis_wing_v0_tests.sh
```

Builder: **32/32 OK** (W0 + R1.1 + R2 + R2.1 P0 controls).

| Control | Observed |
|---|---|
| protected + actual CN base_url | `REFUSE_RESIDENCY`, client 0 |
| missing provenance | `REFUSE_SOURCE_POLICY`, client 0 |
| generic + US base_url | client 1; **full body** bytes equal |
| secret in `tools` | `REFUSE_SECRET`, client 0, no cleartext/bare-sha leak |
| secret in `extra_body` | `REFUSE_SECRET`, client 0, no leak |
| unknown body field | `REFUSE_UNSUPPORTED`, client 0 |
| claimed US dest + moonshot.cn base_url | `REFUSE_DESTINATION`, client 0 |
| R1.1 regression | green |

---

## Files touched (R2.1 delta)

- `omnis_wing/absolute/hermes_chat_join.py` — full-body canon + endpoint bind  
- `omnis_wing/absolute/evaluator.py` — `REFUSE_UNSUPPORTED` in Decision  
- `tests/omnis_wing/test_r2_chat_path.py` — P0-A/B controls  
- `omnis_wing/coverage/ai_egress_coverage_r1.json` — R2.1 notes  
- `BUILD_HANDOFF.md` — this document  

Live Hermes: **untouched**.

---

## Non-claims (unchanged, blunt)

Not streaming / Anthropic / Bedrock / Codex paths. Not whole-tree egress. Not signing/chain. Not live wiring/providers. Not package/push. Not full ABSOLUTE certification. HTTP/TLS/auth headers still outside body equality claim.

**READY_FOR_GATE**

🫡 + 🔑  
— Videl
