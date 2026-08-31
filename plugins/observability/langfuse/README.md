# Langfuse Observability Plugin

This plugin ships bundled with WING but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

Pick one:

```bash
# Interactive: walks you through credentials + SDK install + enable
wing tools  # → Langfuse Observability

# Manual
pip install langfuse
wing plugins enable observability/langfuse
```

## Required credentials

Set these in `~/.omnis-wing/.env` (or via `wing tools`):

```bash
WING_LANGFUSE_PUBLIC_KEY=pk-lf-...
WING_LANGFUSE_SECRET_KEY=sk-lf-...
WING_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
wing plugins list                 # observability/langfuse should show "enabled"
wing chat -q "hello"              # then check Langfuse for a "WING turn" trace
```

## Optional tuning

```bash
WING_LANGFUSE_ENV=production       # environment tag
WING_LANGFUSE_RELEASE=v1.0.0       # release tag
WING_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
WING_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
WING_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
wing plugins disable observability/langfuse
```
