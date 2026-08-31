# BULMA → VIDEL · OMNIS WING TERMINUS ABSOLUTE finish program

**Authority:** Captain wants OMNIS WING to let them use models freely without
silently sending protected project material to a remote provider. No
"sensitive-mode" switch and no claim inflation.

**Starting point:** R5–R7 implementation
`b5a668f52c3c6462204560d2262f937768cc3b12`, branch head
`8b65e15eafa9ac1152c0eb450a293a071e1d5479`, CADMUS
`7cf045442eb4112eea7d9bfe7b4dff59087062ac30740801ad23e31fd5c42e79`.
It proves a substantial selected-fork layer. It is **not** full TERMINUS
ABSOLUTE, not live WING, and not authorization to transmit raw protected
material to a Chinese remote provider.

## The outcome to build

For every WING-owned AI egress path supported by the product, an immutable
canonical envelope with source taint reaches one TransportBroker before any
provider socket. TERMINUS either:

1. refuses before send and produces secret-free evidence;
2. permits only exact scanned bytes to an exact policy-bound destination; or
3. makes a **local** redacted preview and requires a brand-new user request.

It never silently redacts and sends, and it never treats a changed string as
un-tainted. This is AI-egress protection, **not** a claim over terminals,
browsers, Git, untrusted extensions, or the whole workstation.

## W8 — real source-taint graph, not only payload-string classification

Implement provenance at the file/context construction boundary:

- Track workspace-relative path, content digest, protected-root/crown-jewel
  rule, byte range, and classification for every file fragment read into agent
  context; mark env files, private keys, credential stores, and keychain
  exports protected independent of their names.
- Propagate taint through concatenation, summaries, tool outputs, memory
  recall, attachments, and message construction. A transformation does not
  clear taint.
- Unknown/unprovenanced content is conservative by policy, not silently
  generic. Operator policy may set protected roots/globs/fingerprints, breadth,
  byte, and file-count ceilings.
- Inspect every canonical outbound field, including tool schemas/results,
  system instructions, attachments, `extra_body`, and SDK-specific extensions.
- Implement split-secret/encoded-form checks from a frozen threat corpus.
  Scanner crash, timeout, unsupported encoding/type, or indeterminate source
  is a refusal before provider.

Can-fails must prove source in a non-message field, a summarized fragment, a
tool result, a split/encoded secret, an unknown provenance, and scanner fault
all produce a decision with provider calls = 0 and no raw/bare fingerprint in
receipts, exceptions, logs, or filenames.

## W9 — complete WING-owned route inventory and broker exclusivity

Create a machine-readable inventory of every outbound AI-capable route in the
fork: chat/streaming, image, embeddings, audio/transcription/TTS, file/batch
uploads, tools/MCP, provider health/auth, auxiliary agents, SDK wrappers,
dynamic imports, CLI paths, and future registered transports.

- Every route is exactly `GOVERNED`, `DISABLED`, or `OUTSIDE_BOUNDARY`; no
  omitted, advisory, or location-based exemption state. `OUTSIDE_BOUNDARY`
  requires a concrete reason and cannot carry provider payload.
- To claim **full WING TERMINUS**, every supported product AI route above must
  be `GOVERNED`; a disabled route is honest product behavior but is not full
  modality completion.
- Broker is the only provider-socket owner. Add static checks for imports,
  aliases, re-exports, dynamic/importlib reload, wrappers, HTTP/SDK/WebSocket
  entrypoints, and runtime probes. Separate inbound listener permission from
  outbound permission narrowly.
- Health/auth probes also use the broker and receive coverage/evidence labels.

Can-fails must plant each bypass shape and prove build/test failure; exercise
each manifest route once with a harmless fake provider and prove its exact
canonical bytes / expected refusal.

## W10 — exact-destination transport and REDACT protocol

- Bind authorization to scheme, hostname, port, endpoint class, provider, and
  operator-signed residency. Derive actual destination from the client/transport
  at call time; no context-declared destination can override it.
- Enforce HTTPS externally, host allowlist, redirect-disabled/manual redirect
  re-evaluation, credential non-forwarding, and appropriate DNS/IP checks.
  Any changed field invalidates authorization.
- Build the REDACT flow exactly: local preview only → no transmission → explicit
  fresh user intent → fresh envelope ID, provenance, scan, authorization and
  receipt. Do not auto-resubmit. If a faithful local redactor cannot be built,
  leave REDACT unavailable and refuse; do not call it a completed feature.

## W11 — evidence, production operator surface, and anchoring

Preserve R3/R4 pre-send durable, signed evidence. Complete the outstanding
requirements:

- Receipt schema has exact decision, policy digest/version, coverage,
  intended/actual destination, provider/residency, keyed finding correlation,
  sequence/previous digest/key ID/signature and precise two-phase outcome.
- A verifier/health surface independently verifies public-key signatures and
  chain; it reports unsigned legacy entries separately and never retro-signs.
- Build a configurable external-anchor adapter and a durable local pending
  queue. Until an operator configures an anchor, health says
  `REMOTE_ANCHOR_NOT_CONFIGURED`; it must not say anchored.
- Production Keychain/SE enrollment remains explicit. Test backends are never
  selectable by production defaults. Do not mutate Captain’s existing Keychain
  tag during development.

## W12 — controlled live cutover (separate final gate)

Do not edit the dirty live WING checkout. Create a clean, pinned deployment
target/config and an explicit install/attach command. Before any live provider
request, demonstrate:

- production signer status, private ledger ownership/mode, policy signature,
  route inventory, and remote-anchor status;
- all governed paths route through the new broker;
- no old ungoverned provider client remains reachable;
- a local fake-provider smoke passes for every supported modality;
- a protected-project and secret can-fail refuse with zero provider calls.

Live provider smoke requires Captain's explicit immediate approval and may use
only a harmless synthetic prompt. Never make it a hidden gate side effect.

## Completion standard and reporting

Use a new CADMUS input for W8–W12. Return in bounded milestones, each with a
commit, frozen CADMUS SHA, clean-tree status, cold commands/output, planted
can-fails, and an exact route coverage table. No builder self-CLEAR.

`TERMINUS ABSOLUTE · WING-OWNED AI EGRESS GOVERNED` is eligible only when W8–
W11 have independent gate evidence for every supported WING route. It remains
forbidden to say `workstation protected`, `all WING egress`, or `safe to send
raw protected code to a Chinese remote provider` unless an independently
enforced boundary actually covers those claims.

## Hard guardrails

- Work only in `~/projects/omnis-wing`; live WING at `2213ea9…` stays
  untouched.
- No live provider request, Keychain mutation, publish, push, or packaging
  during build/gate work without Captain's explicit authorization.
- Do not weaken a guard, exclude a route, or label a route disabled merely to
  turn a suite green. Record honest blockers.
