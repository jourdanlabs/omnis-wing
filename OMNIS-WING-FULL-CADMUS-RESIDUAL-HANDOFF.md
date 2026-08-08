# OMNIS WING × FULL CADMUS residual · READY_FOR_GATE

**Builder:** Videl  
**Independent gate:** Bulma  
**Verdict:** `READY_FOR_GATE` — **not** self-CLEAR  
**Not claimed:** `TERMINUS ABSOLUTE COMPLETE`

## Pins (uncollapsed)

| Item | Value |
|---|---|
| Branch | `omnis-wing/v0-admission` |
| P0 CLEAR base | `dfef719c2d0bcbb62dc13c9b2e0273ba27e3eb4b` |
| Prior HOLD (image unbound transmit_fn) | `7ce5b803012e81f860f48f01dd97b2fa06cc6482` |
| **Implementation (image dest bind)** | `07224c8be944835da612d7c96022c733a40cbd8b` |
| Live Hermes | `2213ea9…` untouched |
| Residual CADMUS sha256 | `4f79d51def6f5e2d509a0aa7b038c2863189f4239648e4c5be1da085133fa6b2` |

## Cold

```sh
cd ~/projects/omnis-wing && ./scripts/run_tests.sh tests/omnis_wing/
# 13 files, 178 tests passed, 0 failed
```

## HOLD repair (Bulma 7ce5b80301)

Free `transmit_fn` removed from `transmit_image`. Final image send is
broker-owned (`client.images.generations.create`) or a sealed
`BoundImageTransport` whose destination binding must match the client-derived
`images.generations` tuple. Allowed client + evil.example.test adapter →
`REFUSE_DESTINATION`, callback calls 0.

## Residual delivery (prior + repair)

Redirect refuse · GOVERNED image join **with dest binding** · hygiene ·
benign/latency budgets · anchor pending honesty · OUTSIDE_BOUNDARY messaging ·
seal script · ZT matrix tests (25).

Full handoff: `~/projects/pan-cc/handoffs/READY_FOR_GATE-WING-FULL-CADMUS-07224c8be9-2026-08-08.md`

🫡 + 🔑 — Videl
