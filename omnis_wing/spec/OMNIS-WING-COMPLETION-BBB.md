# BULMA → VIDEL · OMNIS WING COMPLETION BBB

**Authority:** Captain’s instruction: *finish WING; do not stop after a leg.*  
**Start pin:** `omnis-wing@89ccebae7922cab0645ecb4e8d145eb5d8a469c5`  
**Existing spine:** R4.1 is clear for ordinary non-stream `chat.completions`, including explicit Keychain enrollment, P-256/Ed25519 algorithm-bound receipts, local fsync, and offline health.  
**Builder:** Videl · **Independent gate:** Bulma · **Do not push or touch live WING.**

## Captain outcome

Deliver a complete **OMNIS WING candidate** that lets Captain work normally with configured AI models while OMNIS, not Captain, automatically governs every model-bound payload.

There is no “sensitive mode” to remember. The system derives provenance from the workspace, scans every outbound body, binds the real destination, and either sends a governed request with durable evidence or refuses *before* any provider receives bytes. A foreign-hosted provider never receives protected source, secrets, or payloads with missing provenance on a covered route.

This is completion authority. Do not stop after a new R-number, a passing unit suite, an adapter, or a beautiful handoff. Continue the loop: inventory → wire → attack → repair → re-run until the definition of done below is met.

## The product contract

### 1. One outbound door

Every AI/provider egress path in the WING fork must reach one governed broker before transport. This includes, at minimum:

- ordinary and streaming chat/completions;
- OpenAI-compatible, Anthropic, Bedrock, Codex/OpenAI, MiniMax, Kimi/Moonshot, Qwen/Alibaba, Fireworks, and any configured custom OpenAI-compatible base URL;
- image, audio, embedding, file, batch, tool-result, MCP-originated, and agent-to-agent payloads where WING can send user/workspace-derived content;
- retry, fallback, resumable, background, and error-recovery sends.

An inventory is not documentation alone. Build a machine-readable route manifest with, for each route: source call site, modality, client/transport, broker join, destination derivation, provenance producer, receipt path, test control, and state (`GOVERNED` or `DISABLED`). `outside`, `later`, and unexplained exemptions are forbidden states.

If a route cannot be safely wired in this run, disable it in the product before its transport boundary. The user must see an accurate refusal. It may not remain a silent bypass.

### 2. Automatic protection, no Captain sorting

For every governed route:

- Construct canonical bytes from the **entire** outbound body; no original kwargs, headers carrying user content, attachments, or tool payload may ride around the envelope.
- Derive the destination from the actual configured endpoint/transport, not caller labels.
- Carry source provenance automatically from workspace/document/tool origin. Missing, malformed, or stale provenance is a pre-send refusal—not permission by ambiguity.
- Scan canonical payload bytes and relevant source-derived content for protected markers/secrets before broker invocation.
- Apply the residency/destination policy. Protected/project-derived content and secret-shaped data must refuse on disallowed/foreign destinations. Generic eligible work may proceed only when the route’s actual endpoint satisfies policy.
- Use local mediated tools for repository/file actions when a remote model does not receive the raw underlying content. Tool responses are themselves governed outbound payloads; they cannot become a side door.

Do not ask Captain to tag content, choose a safety mode, or move between “safe” and “unsafe” workflows. The enforcement belongs to WING.

### 3. Evidence that tells the truth

For every governed send/refusal:

- a canonical, secret-free receipt binds envelope digest, decision, phase, policy/coverage version, actual destination/provider/residency, source/finding correlation, previous digest, sequence, key ID, and signature algorithm;
- a signed and locally fsync’d `TRANSMISSION_STARTED` receipt exists before any provider call;
- terminal evidence is signed after send; inability to create it yields `OUTCOME_UNKNOWN`, never a flattering success;
- production Keychain P-256 and cold disposable Ed25519/P-256 paths verify through their bound algorithms; unknown/mismatched algorithms fail closed;
- operator health/verifier reports enrollment, key fingerprint, signed/unsigned counts, chain validity, outcome uncertainty, coverage, and anchor state honestly;
- no private key, prompt/source cleartext, planted secret, or bare digest of a low-entropy marker appears in receipts, ledger, health, exceptions, filenames, or logs.

Remote anchoring/replication may be `NOT_CONFIGURED`; it must never be called durable remote evidence until actually implemented and independently verified.

### 4. Key lifecycle

- Enrollment is an explicit operator command only. Startup, chat, recovery, and health never create, rotate, delete, export, or silently choose a key.
- The Captain tag `ai.jourdanlabs.omnis-wing.terminus.r4` is read-only to automated tests. It is never deleted, rotated, or exported.
- A missing, locked, unavailable, ambiguous, or signing-failed production key causes a pre-send refusal with provider calls `0`.
- Never claim Secure Enclave attestation from a missing Keychain attribute. Preserve `UNVERIFIED_AT_READ` unless a separately verified platform attestation is available.

## Completion gates

### A. Egress closure gate

1. Generate the route manifest from source plus a human-reviewed inventory. It must enumerate every provider-bearing client/transport and all direct socket/HTTP/subprocess escape paths.
2. Add import-level and call-site gates that catch aliases, re-exports, destructuring, wrappers, `requests`, `httpx`, `urllib`, `aiohttp`, `socket`, WebSocket clients, SDK transports, and shell-outs such as `curl` when they can carry payload. A governed broker may hold the narrow transport permission; no route module may.
3. Each planted bypass must break the gate. Each manifest row must have a matching test or a product-disabled refusal test.
4. There may be no user-payload egress exemption. Health probes without user payload may be ungoverned only if named in the manifest with destination and purpose.

### B. Modalities and failure gate

For every manifest route/modality, prove with a fake provider that:

- protected project source to a foreign/CN endpoint: refused before provider call;
- missing provenance: refused before provider call;
- planted secret in every body-bearing field/attachment/tool result: refused before provider call and absent from evidence;
- actual endpoint mutation: refused before provider call;
- permitted generic/local policy control: exact canonical bytes reach provider once, and receipt is terminally verifiable;
- streaming cancellation, retry, fallback, timeout, provider exception, and terminal-evidence exception never falsely report completed/sent;
- disabled routes refuse before their old transport call.

### C. Real-machine proof gate

Without using Captain’s API tokens or sending a real provider request:

- compile the native Keychain bridge from source;
- use the pre-existing Captain tag read-only, only behind an explicit opt-in integration flag;
- sign/verify a fake-provider selected-path receipt with P-256;
- mutate receipt bytes and algorithm label independently; both must fail verification;
- prove enrollment is not invoked by startup or any normal governed call.

### D. Operator acceptance gate

The operator surface must supply one clear workflow:

```text
omnis-wing status
omnis-wing enroll                 # explicit and idempotent
omnis-wing health --ledger …
omnis-wing verify --ledger …
omnis-wing coverage
```

It must tell Captain what is active, what is disabled, which routes are governed, what would be refused, and when a record is uncertain. No green umbrella label may hide an invalid chain, unsigned history, uncovered route, missing anchor, or missing enrollment.

## Autoloop rules

1. Start with a source inventory and commit it.
2. Implement the smallest vertical slice that closes the next uncovered route class.
3. Run the entire completion suite plus new can-fails.
4. If a test, source scan, fake provider, or real-machine opt-in exposes a hole, fix it; add the regression; repeat from step 3.
5. Continue until every manifest route is `GOVERNED` or product-`DISABLED`, all required can-fails are observed, and Bulma independently re-gates it.
6. Do not send a `READY_FOR_GATE` after intermediate legs. Send only a final completion packet—or a concrete external authority request that cannot be resolved from the fork (for example, Captain must complete OAuth). Never substitute a placeholder green for that authority.

## Safety and workspace boundaries

- Work in `~/projects/omnis-wing` only; commit locally as you close cohesive units, but do not push.
- Do not modify, stop, start, or reconfigure `~/.omnis-wing/omnis-wing`; it remains the untouched upstream/live instance.
- Do not inspect, copy, print, or transmit API keys, OAuth tokens, session data, browser data, project content, or private Keychain material.
- Do not call live model providers during this build. Fake endpoints and harmless test fixtures only. Live model onboarding is an explicit Captain action after the completed candidate is independently gated.
- Do not retro-sign old ledger history or call old unsigned rows signed.

## Final handoff required

One `OMNIS-WING-COMPLETION-HANDOFF.md`, not a sequence of victory laps. It must include:

- final commit and exact CADMUS/BBB authority hash;
- route manifest and every `GOVERNED`/`DISABLED` disposition;
- cold suite command and count; can-fail table; opt-in Keychain proof;
- operator workflow and output examples using no secrets;
- coverage statement written in plain English;
- exact remaining non-claims, if any;
- statement that builder is `READY_FOR_GATE`, never self-`CLEAR`.

**Completion is not “we added another leg.” Completion is a candidate where no model-bound user/workspace payload can leave through an ungoverned route. Build until that is true.**

— Bulma
