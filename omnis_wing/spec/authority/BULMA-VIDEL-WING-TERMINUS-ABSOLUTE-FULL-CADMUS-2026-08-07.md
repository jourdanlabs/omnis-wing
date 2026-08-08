# CADMUS FULL BUILD CONTRACT · OMNIS WING × TERMINUS ABSOLUTE 1.0

**Captain outcome:** one shippable WING deployment in which every **WING-owned,
supported AI transmission** is decided locally before its first outbound byte;
disallowed payloads/destinations refuse; permitted bytes are bound to a precise
destination; evidence is independently verifiable and secret-free.

**This is a WING-only completion contract.** It does not claim protection over
the IDE, terminal, browser, Git, third-party extensions, the whole workstation,
or the untouched live Hermes install until a separately evidenced boundary
covers each of those.

**Builder:** Videl  
**Independent gate:** Bulma  
**Authority source:** `BULMA-TERMINUS-ABSOLUTE-1.0.md`  
**Supersedes as a build brief:** `BULMA-VIDEL-WING-ABSOLUTE-FINISH-BBB-2026-08-07.md`  
**Starting implementation:** R5–R7 `b5a668f52c3c6462204560d2262f937768cc3b12`  
**Starting branch head:** `8b65e15eafa9ac1152c0eb450a293a071e1d5479`  
**Live Hermes:** `~/.hermes/hermes-agent@2213ea9…` — immutable during build.

---

## 0. Non-negotiable truth

- Remote providers receive whatever is sent to them. Therefore raw
  project/protected/credential material is **not** safe to send to a Chinese
  remote model merely because WING logged it. Policy must refuse, retain it
  locally, or offer a local redacted preview followed by a fresh user action.
- There is no Captain-facing “sensitive mode.” Classification and enforcement
  are automatic. Missing provenance, unsupported content, scanner error, or
  policy error fail closed.
- `GOVERNED` means the real route uses the broker. `DISABLED` means product
  refuses it and is not functional. A disabled route is never counted as a
  governed modality in the completion claim.
- Never send, inspect, export, rotate, delete, or enroll Captain credentials
  during build/gates without a new immediate authorization. No live provider
  request is an incidental test.

---

## 1. Fixed completion claims

The final release may say only:

> TERMINUS governs every supported OMNIS WING-controlled AI transmission before
> the first outbound byte, refuses disallowed payloads and destinations, and
> produces independently verifiable secret-free evidence of what was
> authorized, refused, attempted, and completed.

It may not say “all workstation traffic,” “all Hermes traffic,” “safe to send
raw protected code to Chinese models,” “hardware attested” without attestation,
or “anchored” without a working external anchor.

The glass must say `AI EGRESS GOVERNED`, list governed modalities, show the
coverage boundary, and visibly turn red for unavailable signer, invalid chain,
stale/invalid policy, missing anchor when an anchor is required, or an
ungoverned registered route.

---

## 2. Milestones — build in this order

Each milestone requires a frozen CADMUS input digest, commit pin, clean-tree
status, cold command/output, planted can-fail, and honest scope statement.
Later milestones must retain all prior controls.

### M1 · Complete source-taint graph

**Build**

1. Introduce canonical `SourceProvenance` at every WING file/context read:
   workspace-relative path, content digest, classification, protected-root and
   crown-jewel matches, and included byte ranges.
2. Mark `.env`, private keys/certificates with private material, credential
   stores, connection strings, and Keychain exports protected independently of
   a filename supplied to the model.
3. Propagate taint through concatenation, summary, tool result, attachment,
   memory retrieval, system prompt, message construction, and SDK extensions.
   A transformed protected fragment remains protected.
4. Bind repo breadth/file-count/byte ceilings and operator globs/fingerprints
   to signed policy. Unknown source provenance refuses under mandatory policy.
5. Make all body fields scanable, including `messages`, `system`, `tools`,
   tool results, `extra_body`, attachments, and provider-specific fields.

**Prove**

- Protected content with the filename omitted, paraphrased/concatenated,
  summarized, or present in a tool result refuses with zero provider calls.
- A secret split across fields or represented in required encoded forms refuses.
- Scanner crash, timeout, unknown encoding, unsupported payload type, and
  missing provenance refuse with zero provider calls.
- A whole receipt/ledger/log/exception/output tree scan has zero cleartext
  test-secret instances and no bare reversible digest of low-entropy marker.
- Frozen benign-code corpus remains below a declared refusal budget.

**Exit:** no payload-string heuristic is the sole source-protection authority.

### M2 · Exhaustive WING route inventory and real broker joins

**Build**

1. Discover and enumerate every WING-owned outbound AI-capable path: chat,
   streaming, image, embedding, audio/transcription/TTS, file/batch, tools,
   MCP, agent fanout, CLI model calls, SDK wrappers, provider auth/health, and
   dynamically loaded/re-exported adapters.
2. Machine-readable manifest requires every discovered route to be exactly
   `GOVERNED`, `DISABLED`, or `OUTSIDE_BOUNDARY`; the latter must have a
   concrete non-AI-payload reason.
3. Make every supported product AI route `GOVERNED` before claiming WING full
   completion. Move no route to `DISABLED` simply to make a count pass.
4. Create the single `TransportBroker` ownership rule. No module other than
   broker may own an outbound provider socket/client.
5. Enforce static and runtime checks over imports, aliases, re-exports,
   wrappers, dynamic/importlib/reload, HTTP/SDK/WebSocket APIs, late imports,
   registry dispatch, and callback/plugin paths. Inbound listener permissions
   are separate and narrowly declared.

**Prove**

- One harmless fake-provider test per manifest route verifies exact route
  state, canonical body, and broker traversal.
- Plant each known bypass shape; static or runtime gate fails.
- A newly introduced provider transport without manifest/conformance entry
  fails the build.
- Health/auth traffic is either brokered with lower classification or explicitly
  outside WING AI payload scope—never invisible.

**Exit:** manifest reports zero unresolved WING-owned supported AI routes and
all supported modalities are GOVERNED.

### M3 · Canonical envelope, deterministic inspection, and transport binding

**Build**

1. Ensure every broker call accepts one immutable `OutboundEnvelope` covering
   modality, lane, exact canonical payload bytes, complete sources, policy /
   coverage class, and intended destination.
2. Broker reconstructs the provider request only from the scanned canonical
   bytes. No original kwargs, SDK default, hidden tool field, or later
   mutation rides along unscanned.
3. Bind authorization to actual scheme + hostname + port + endpoint class +
   provider + operator-signed residency. Derive actual destination from the
   transport/client; context declarations cannot override it.
4. Enforce external HTTPS, exact host allowlist, redirect-disabled/manual
   re-evaluation, no cross-redirect credential forwarding, and deployment-
   appropriate DNS/IP validation.
5. Implement exact decision grammar: `PERMIT`, `REFUSE_SECRET`,
   `REFUSE_CROWN_JEWEL`, `REFUSE_SOURCE_POLICY`, `REFUSE_REPO_BREADTH`,
   `REFUSE_DESTINATION`, `REFUSE_RESIDENCY`, `REFUSE_UNSUPPORTED`,
   `REFUSE_SCANNER_FAILURE`, `REFUSE_POLICY_INVALID`. No warning-and-continue.

**Prove**

- Post-authorization destination/body mutation, unknown body field, redirect,
  changed hostname/port/path class, and stale policy refuse before body/credential
  forwarding.
- Actual bytes received by fake provider equal envelope bytes for every modality.
- CN remote receives zero bytes for protected/project/credential/unknown source
  material. Generic policy-permitted content follows the signed destination
  policy, not provider marketing metadata.

**Exit:** every permit is a permit for precisely the bytes and destination
actually used.

### M4 · REDACT correctly or leave it unavailable

**Build**

1. Build a local deterministic redaction preview carrying provenance and
   redaction reasons.
2. A redaction action sends nothing. It requires an explicit fresh user
   request. That request receives a new envelope ID, canonicalization, full
   source scan, decision, and evidence.
3. If no faithful safe redactor is ready for a format/modality, policy refuses;
   it must not silently degrade or auto-resubmit.

**Prove**

- Original request yields zero provider calls.
- Preview contains no secret/protected original where policy requires removal.
- Confirmed new request has a new envelope/receipt and only its exact bytes can
  reach the fake provider.

**Exit:** no code path mutates and forwards the original request.

### M5 · Evidence, signing, chain, and external anchor

**Build**

1. Preserve pre-send signed + flushed + fsync’d `TRANSMISSION_STARTED` before
   provider call and precise terminal states: `AUTHORIZED`, `STARTED`,
   `COMPLETED`, `FAILED_BEFORE_TRANSMISSION`, `FAILED_AFTER_TRANSMISSION_STARTED`,
   `OUTCOME_UNKNOWN`.
2. Receipt includes envelope digest, decision, enforcement state, policy
   version/digest, coverage, intended/actual destination, provider/residency,
   scanner codes, keyed finding-correlation digest, previous digest, sequence,
   key ID, algorithm, and verifiable signature—never matched material.
3. Production signer defaults fail closed; explicit Keychain/Secure Enclave
   enrollment only. Test signer cannot become a production fallback.
4. Build independent public-key verifier and chain manifest. Do not retro-sign
   legacy rows.
5. Build configurable external anchor with durable pending queue/retry and
   health truth. Until configured/successfully verified it says
   `REMOTE_ANCHOR_NOT_CONFIGURED` or failure, never anchored.

**Prove**

- One-byte receipt mutation, signature malleability/algorithm substitution,
  ledger reorder/rewrite, and anchor replacement fail verification.
- Pre-send signing/fsync failure refuses with provider calls = 0; terminal
  evidence failure becomes `OUTCOME_UNKNOWN`, never a flattering success.
- Full state scan contains no cleartext test secret. Private ledger permissions
  reject unsafe owner/mode/symlink without repairing or proceeding.
- External-anchor test double independently catches whole-ledger replacement.

**Exit:** “signed,” “completed,” “uncertain,” and “anchored” are each backed by
the fact the UI claims.

### M6 · Operator policy and glass

**Build**

1. Signed policy load/verify with `enforce`, `local_only`, and `deny_all`.
   Production has no `off`. Unauthorized developer bypass visibly prints
   `UNENFORCED — PAYLOAD NOT INSPECTED` and cannot resemble healthy enforcement.
2. Operator status/enroll/health/verify/coverage commands expose signer
   enrollment/fingerprint, policy digest, chain state, remote anchor, counted
   signed/unsigned legacy rows, each route/modality state, and outside-boundary
   copy.
3. WING UI glass reflects all receipt phases and refusal decisions; no
   `SENT`/`COMPLETED` claim from an authorization or a crash.

**Prove**

- Missing signer, stale/broken policy, invalid signature/chain, unavailable
  anchor when policy requires it, and ungoverned route render visibly red.
- UI model/provider failure leaves no stuck generating state and no duplicate
  retry after terminal refusal.
- Copy scan rejects overclaims beyond manifest.

**Exit:** an operator can verify the boundary and its limits without source
access or a misleading calm UI.

### M7 · controlled production cutover and sealed release

**Build**

1. Leave dirty live Hermes untouched. Produce a clean pinned deployment target
   and explicit production config/install/attach path.
2. Require startup preflight: signed policy valid, production signer available,
   private ledger valid, coverage manifest complete, and required anchor state.
   Failure must deny model egress.
3. Run all conformance tests against the installed/sealed WING artifact, not
   source only. Package only after independent gate.

**Prove before any live provider request**

- Every supported modality passes fake-provider conformance through the
  installed artifact.
- Protected/project/secret hostile corpus refuses with zero provider calls.
- Existing environment does not revive an old direct client or test signer.
- Recovery/rollback leaves no ungoverned production window.

**Final controlled live smoke:** only with Captain’s immediate approval, one
synthetic harmless prompt to an explicitly policy-permitted route; capture the
secret-free receipt/verification. It is not a default test.

**Exit:** independent Bulma gate records exact commit, policy digest, signer
state, artifact identity, coverage manifest, test evidence, and claim boundary.

---

## 3. Zero-tolerance release matrix

All must pass in the installed artifact:

1. Chat secret refuses, signed, absent everywhere.
2. Image secret behaves identically.
3. Same hostile corpus runs across every registered modality.
4. Crown-jewel content refuses without filename hint.
5. Source taint survives paraphrase/concatenation.
6. Split secret refuses.
7. Redirect attack refuses before forwarding.
8. Destination mutation cannot replay authorization.
9. Scanner fault refuses without provider call.
10. Ledger state contains no cleartext test secret.
11. Low-entropy marker leaves no reversible bare digest.
12. Receipt mutation fails signature verification.
13. Whole ledger rewrite fails external-anchor verification.
14. Disabled/unavailable enforcement cannot look clean.
15. Coverage glass visibly names terminal/browser/etc. outside WING boundary.
16. Static and runtime transport sweeps find no external provider transport
    outside broker.
17. Frozen benign corpus stays within refusal budget.
18. Scanner P50/P95/P99 overhead stays within declared frozen budget.
19. Every critical invariant has a planted weakening can-fail.
20. Builder is not sole judgment gate.

Any failure below is a ship blocker: a bypass, secret leakage, unknown policy
permit, unverified “signed” claim, overbroad UI claim, clean-looking disabled
boundary, or missing independent gate.

---

## 4. Builder operating rules

- Work only in `~/projects/omnis-wing`; do not touch `~/.hermes/hermes-agent`.
- Do not push/publish/package, mutate Keychain, or make live provider calls.
- Do not weaken tests, exclude routes, or turn routes into `DISABLED` to claim
  completion.
- Return a handoff only after **all seven** milestones are complete, or return a
  bounded blocker stating the exact unfinished acceptance condition. Never say
  `TERMINUS ABSOLUTE COMPLETE` from a partial milestone.
- Bulma independently re-gates the candidate. Builder never self-CLEARs.
