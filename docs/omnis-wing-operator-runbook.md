# OMNIS WING clean-profile operator runbook

This runbook repeats the locally governed WING startup path without replacing
live Hermes, printing credentials, mutating Keychain enrollment, or making a
provider request. It is bounded to ordinary non-stream chat plus the buffered
stream adapter through pinned local CADUCEUS.

## 1. Assemble exact sibling authorities

Create one private assembly directory with these sibling worktrees:

```text
assembly/
  caduceus/   05c7af0d3e49c73552cd446f3d1884ad40ae40b1
  omnis-gate/ 02322c52b6e95a8c10fe3ab110ab18dfea59891e
```

Run `npm ci` in the clean CADUCEUS worktree. Do not move either pin after the
operator configuration is written. CADUCEUS imports its exact sibling
`omnis-gate`; the verifier checks both tracked trees and refuses drift.

## 2. Create an isolated profile

Choose a new profile path that is not `~/.hermes` and keep all mutable state
under it:

```bash
export OMNIS_WING_PROFILE_HOME="$HOME/.hermes/profiles/omnis-wing-dogfood"
export HERMES_HOME="$OMNIS_WING_PROFILE_HOME"
export CADUCEUS_STATE_DIR="$HERMES_HOME/caduceus-state"
export CADUCEUS_LANES="$HERMES_HOME/operator/caduceus-lanes.yaml"
```

Copy the tracked production and real-work templates into
`$HERMES_HOME/operator/`. Set the production ledger inside this profile and
set its bridge path to:

```text
$HERMES_HOME/omnis-wing-runtime/bin/omnis_wing_keychain
```

The real-work config must name the exact CADUCEUS worktree, pin, unused
loopback port, instance id, and service-token environment variable. Install a
signed WING policy and trust record, then export their paths:

```bash
export OMNIS_WING_PRODUCTION_CONFIG="$HERMES_HOME/operator/wing-production.yaml"
export OMNIS_WING_REAL_WORK_CONFIG="$HERMES_HOME/operator/real-work.json"
export OMNIS_WING_POLICY_PATH="$HERMES_HOME/operator/wing-policy.json"
export OMNIS_WING_POLICY_TRUST_PATH="$HERMES_HOME/operator/wing-policy-trust.json"
```

Provider and local service capabilities remain in the inherited operator
environment. Never put either value in these tracked templates or the run
manifest.

## 3. Compile the bridge and inspect enrollment

This compiles only the Swift bridge, reads signer status, creates private
`0700` directories and `0600` empty ledgers, verifies both dependency pins,
and writes a content-addressed secret-free manifest. It never calls `enroll`.

```bash
scripts/omnis-wing-operator verify --compile-bridge
# alias (same command):
scripts/omnis-wing-operator verify-setup --compile-bridge
# or:
python -m omnis_wing.absolute.real_work.operator_runbook verify-setup
```

If the Captain tag is absent or Keychain is locked, the command refuses with
`signer_not_enrolled_or_locked`. Enrollment is a separate Captain-authorized
operation and is intentionally absent from this workflow. The verify command
never prints credentials, service tokens, or API keys; output is scrubbed for
common credential patterns.

## 4. Start local CADUCEUS and run cold preflight

Choose an unused loopback port in the real-work config, provide the local
service capability in its named environment variable, then run:

```bash
scripts/omnis-wing-operator start
```

The command verifies contract drift, policy, route coverage, signer, private
ledger, exact CADUCEUS and OMNIS GATE pins, local health identity, and chain
health. It makes no model request. A foreign listener refuses as
`caduceus_port_collision_untrusted_service`.

## 5. Launch WING

After the cold preflight is `READY`, launch the isolated product surface:

```bash
scripts/hermes-wing
```

Exit WING normally from its own interface. Do not use broad process-kill
commands. Read setup and router health at any time with:

```bash
scripts/omnis-wing-operator status
```

## 6. Stop only the run-owned router

```bash
scripts/omnis-wing-operator stop
```

The stop command requires the private ownership record, exact PID start time,
exact command, configured base, CADUCEUS pin, and entry path to match. Missing
or mismatched ownership refuses; it never searches for or kills other Node,
Hermes, or CADUCEUS processes.

## Actionable refusals

- `caduceus_dependencies_missing_run_npm_ci`: install the pinned worktree's
  lockfile dependencies.
- `omnis_gate_sibling_not_git_worktree` / `omnis_gate_tree_commit_mismatch`:
  restore the exact sibling authority.
- `caduceus_port_collision_untrusted_service`: choose an unused loopback port;
  do not kill an unidentified listener.
- `signer_not_enrolled_or_locked`: unlock or separately authorize enrollment.
- `policy:*` or `policy_id_mismatch`: repair signed operator policy/config;
  there is no bypass.
- `caduceus_process_not_owned_by_run`: nothing owned by this profile may be
  stopped.
- `missing_receipts`: initialize only the run-owned empty chain through
  `verify`; never synthesize a receipt.

## Claim boundary

This workflow proves repeatable setup and cold local readiness. It does not
repeat the live MiniMax proof, authorize another provider call, claim every
WING route is governed, or claim workstation-wide DLP.
