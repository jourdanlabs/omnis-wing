# TERMINUS ABSOLUTE

_Extracted from Captain→Pan queue 2026-08-04 for gate use. Architect: Bulma._

BBB — TERMINUS ABSOLUTE
Version: 1.0 architecture packet
Architect: Bulma
Existing builder: Pan
Judgment gate: Someone other than the builder
Captain: Leland Jourdan II
Status: Build-ready
Rule: Ship no bullshit.
B1 — Business
The decision
Turn TERMINUS from a chat-payload secret scanner into the single provable outbound boundary for every AI-controlled transmission OMNIS owns.
The truthful promise
Before any governed AI payload leaves the machine, TERMINUS determines what is leaving, where it is going, and whether policy permits it. It refuses disallowed transmission and produces independently verifiable evidence—without copying the protected material into its own ledger.
The boundary we never blur
TERMINUS 1.0 governs OMNIS-owned AI egress:

* Chat and completion calls
* Image generation
* Embeddings
* Audio and transcription
* File and batch uploads
* Agent tool and MCP payloads
* Provider health/auth calls
* Every future transport registered through CADUCEUS

It does not claim to govern arbitrary terminal commands, Git, browsers, untrusted extensions, or unrelated child processes unless a separately installed OS/network enforcement layer controls those paths.
The glass must always say which boundary is active:

* `AI EGRESS GOVERNED`
* `IDE-OWNED EGRESS GOVERNED`
* `WORKSTATION EGRESS NOT GOVERNED`

No screen may shorten that into “all outbound traffic protected.”
Commercial wedge
Generic DLP detects content. AI gateways route traffic. Audit logs record events.
TERMINUS binds four things into one product:

1. Pre-transmission decision
2. Destination and jurisdiction enforcement
3. Secret-free refusal and transmission evidence
4. Explicit proof of whether enforcement ran

That combination—not regexes—is the asset.
B2 — Build
BBB: One Egress Chokepoint

```
AI surface
    ↓
OutboundEnvelope
    ↓
pure route plan
    ↓
TERMINUS policy decision
    ├── REFUSE → refusal receipt → stop
    ├── REDACT → local preview only → new request required
    └── PERMIT → authorization receipt
                     ↓
               TransportBroker
                     ↓
                  provider
                     ↓
               outcome receipt
```

No component except `TransportBroker` may open an external AI-provider socket.
Raw `fetch`, HTTP clients, WebSockets, provider SDKs, and direct socket APIs outside the broker are build failures.
Every modality—including the current image route—must use the same boundary.
BBB: Canonical Outbound Envelope
Every governed transmission becomes one immutable structure before evaluation:

```
interface OutboundEnvelope {
  envelope_id: string;
  modality:
    | 'chat'
    | 'image'
    | 'embedding'
    | 'audio'
    | 'file'
    | 'batch'
    | 'tool'
    | 'mcp'
    | 'health';
  lane: string;
  payload: CanonicalPayload;
  sources: SourceProvenance[];
  intended_destination: {
    provider: string;
    scheme: 'https' | 'http';
    hostname: string;
    port: number;
    path_class: string;
    residency: string;
  };
  policy_version: string;
  coverage_class: string;
}
```

The scanner evaluates the exact canonical bytes the broker would transmit—not an approximation assembled earlier in the stack.
Provider SDKs may not silently add unscanned fields afterward.
BBB: Source-Taint Protection
Pattern matching alone cannot identify valuable code. TERMINUS must know where outbound material came from.
Every file read into AI context carries provenance:

```
workspace-relative path
content digest
classification
protected-root membership
crown-jewel policy match
byte ranges included
```

Policy may therefore refuse:

* Any material originating in a protected root
* Any `.env`, keychain export, credential store, or private-key file
* Files matching operator-defined globs
* Exact protected-content fingerprints
* More than the permitted number of files or bytes
* A repository tree or architectural inventory beyond threshold
* Content without source provenance when provenance is mandatory

Source taint propagates through concatenation, summarization, tool results, and message construction. Transforming protected material does not erase its classification.
BBB: Deterministic Content Inspection
Required local checks:

* Private keys and certificates containing private material
* Provider tokens and credentials
* Connection strings
* Signed tokens
* Secret-shaped assignments
* High-entropy candidates with contextual confirmation
* Operator-declared literal markers
* Operator-declared paths and globs
* Protected content fingerprints
* Repository breadth and payload-size rules
* Split secrets spanning adjacent message parts
* Encoded forms required by the frozen threat corpus

The deterministic engine decides. Models may suggest classifications but cannot permit transmission.
Scanner crash, timeout, unknown encoding, or unsupported payload type means `REFUSE_UNKNOWN`, never pass.
BBB: Destination Binding
Before transmission, TERMINUS binds authorization to:

```
scheme + hostname + port + endpoint class + residency + provider
```

Required controls:

* HTTPS for external providers
* Exact host allowlisting
* Manual redirect handling
* Redirect destination re-evaluation
* No credential forwarding across redirects
* DNS/IP validation appropriate to the deployment
* Residency taken from signed operator policy—not provider self-report
* Authorization invalidated if any destination field changes

Health probes also use the broker. They may carry a lower sensitivity classification, but they do not become invisible egress.
BBB: Decision Grammar
Allowed decisions:

* `PERMIT`
* `REFUSE_SECRET`
* `REFUSE_CROWN_JEWEL`
* `REFUSE_SOURCE_POLICY`
* `REFUSE_REPO_BREADTH`
* `REFUSE_DESTINATION`
* `REFUSE_RESIDENCY`
* `REFUSE_UNSUPPORTED`
* `REFUSE_SCANNER_FAILURE`
* `REFUSE_POLICY_INVALID`

No warning-and-continue decision exists.
“Send redacted” means:

1. Produce a local redacted preview.
2. Transmit nothing.
3. Require an explicit new request.
4. Canonicalize and scan the new payload from zero.
5. Issue a new envelope ID and receipt.

TERMINUS never edits and silently sends the original request.
BBB: Cryptographic Receipts
Replace the current unkeyed `sig` claim with real receipt signing.
Each receipt must contain:

* Envelope digest
* Decision
* Enforcement state
* Policy digest and version
* Coverage class
* Intended destination
* Actual destination, when contacted
* Provider and residency
* Scanner result codes
* Keyed finding correlation digest
* Previous receipt digest
* Monotonic sequence
* Signing-key identifier
* Ed25519 signature

Matched material must never enter:

* Receipt
* Error text
* Tooltip
* logs
* telemetry
* filenames
* exception objects

Use keyed correlation digests for findings. Bare SHA-256 can expose low-entropy crown-jewel markers to guessing.
The signing key belongs in Keychain/Secure Enclave where available. Export includes the public key and chain-verification manifest.
Periodically anchor the chain head outside the mutable ledger. Otherwise wholesale ledger replacement remains possible.
BBB: Two-Phase Truth
`PERMITTED` is not the same fact as `SENT`.
Record events precisely:

1. `AUTHORIZED`
2. `TRANSMISSION_STARTED`
3. `TRANSMISSION_COMPLETED`
4. `FAILED_BEFORE_TRANSMISSION`
5. `FAILED_AFTER_TRANSMISSION_STARTED`
6. `OUTCOME_UNKNOWN`

The UI may only say `SENT` when transmission started. It may only say `COMPLETED` when provider completion is evidenced.
A crash between stages must remain visible as uncertainty.
BBB: TERMINUS on the Glass
The panel header must show:

```
TERMINUS · AI EGRESS GOVERNED
Policy 7f31… · Signing key JL-MAC-01
12 completed · 2 refused · 1 uncertain
Coverage: chat · image · embeddings · tools
Outside boundary: terminal · Git · browser · third-party extensions
```

Every row exposes:

* Decision
* Modality and lane
* Intended and actual destination
* Residency
* Enforcement state
* Receipt signature status
* Policy version
* Secret-free finding description
* Coverage class

Image receipts and all future modalities appear in the same surface.
Missing ledger, invalid signature, broken chain, stale policy, unavailable signer, or ungoverned route is visually red—not empty, calm, or green.
BBB: Off-Switch Discipline
Production modes:

* `enforce`
* `local_only`
* `deny_all`

No production `off`.
Developer/audit mode may disable scanning only when explicitly compiled or administratively authorized. Every disabled call must say:

```
UNENFORCED — PAYLOAD NOT INSPECTED
```

Enterprise policy may forbid startup when enforcement is unavailable.
BBB: Coverage Manifest
Maintain a machine-verifiable registry of all outbound adapters.
Every adapter declares:

```
adapter ID
modalities
transport
governed status
policy contract version
conformance-test digest
```

The build fails when:

* A provider transport is unregistered
* An adapter bypasses `TransportBroker`
* A governed modality lacks a conformance test
* Product copy claims broader coverage than the manifest proves

B3 — Benchmark and Gate
Zero-tolerance acceptance

1. Chat secret: provider function never called; refusal signed; secret absent everywhere.
2. Image secret: identical result through the image route.
3. Every modality: the same hostile corpus runs against every registered adapter.
4. Crown-jewel glob: protected file content refuses even when its filename is omitted from the prompt.
5. Source taint: paraphrasing or concatenating protected context does not erase policy classification.
6. Split secret: token divided across message parts still refuses.
7. Redirect attack: allowed provider redirecting elsewhere refuses before forwarding body or credentials.
8. Destination mutation: authorization for one host cannot be replayed against another.
9. Scanner failure: injected crash produces refusal and no provider call.
10. Ledger secrecy: whole state directory contains zero cleartext test-secret occurrences.
11. Low-entropy finding: receipt contains no reversible bare hash of the marker.
12. Real signature: one-byte receipt mutation fails verification.
13. Whole-ledger rewrite: replacement chain fails external-anchor verification.
14. Enforcement disabled: screen reads `UNENFORCED`; it cannot resemble clean enforcement.
15. Coverage honesty: terminal/browser paths are visibly outside the 1.0 claim.
16. No raw transport: static sweep finds no external AI transport outside the broker.
17. False-positive corpus: ordinary code and synthetic fixtures remain below the frozen refusal budget.
18. Latency: scanner stays within a frozen local overhead budget at P50/P95/P99.
19. Installed artifact: all tests repeat against the sealed `.app`, not merely source.
20. Can-fail proof: weakening each critical invariant makes its assigned test fail.

Release-killing failures
Do not ship if any of these occur:

* One governed payload reaches a provider without a TERMINUS decision
* One secret appears in a receipt, error, UI, or log
* One modality bypasses the broker
* One invalid or unknown policy defaults to permit
* A receipt is called signed without a verifiable digital signature
* The glass implies terminal/workstation protection that is not installed
* A disabled boundary looks clean
* The builder is also the sole judgment gate

Final ship sentence
Only after every gate passes:
TERMINUS governs every OMNIS-controlled AI transmission before the first outbound byte, refuses disallowed payloads and destinations, and produces independently verifiable secret-free evidence of what was authorized, refused, attempted, and completed.
That is the perfect version, Captain.
Not “we scan prompts.”
Not “we keep China out.”
We own the border, we prove the border ran, and we never lie about where the border ends.
