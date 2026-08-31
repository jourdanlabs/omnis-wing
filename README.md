# OMNIS WING

JourdanLabs agent runtime: Ink TUI, BIFROST verification, CADUCEUS routing.

OMNIS WING is built on Hermes Agent by Nous Research — the OMNIS layer, BIFROST integration, and CADUCEUS routing are JourdanLabs'. Attribution lives in `LICENSE` and `NOTICE`. Upstream: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

This tree is the product. Security fixes from Nous are cherry-picked through the `upstream` remote. Do not auto-pull upstream into this repo. See `docs/UPSTREAM-POLICY.md`.

**Look (shipped default):** the Ink TUI skin is WING blue (`ui-tui` `DARK_THEME` / CLI skin `default`). Gold-on-navy is the optional `gold` skin, not the product default. See `docs/WING-DEFAULTS.md`.

**Shipped default model:** `moonshotai/kimi-k2.6` (non-Anthropic). CADUCEUS, when configured, routes it via Fireworks US. There is no `claude-*` in the first-run / example default.

Use any model you want — OpenRouter, Fireworks, Kimi/Moonshot, MiniMax, NVIDIA NIM, Hugging Face, OpenAI, or your own endpoint. Switch with `wing model` — no code changes, no lock-in. Optional Portal OAuth: `wing setup --portal`.

<table>
<tr><td><b>A real terminal interface</b></td><td>Full TUI with multiline editing, slash-command autocomplete, conversation history, interrupt-and-redirect, and streaming tool output.</td></tr>
<tr><td><b>Lives where you do</b></td><td>Telegram, Discord, Slack, WhatsApp, Signal, and CLI — all from a single gateway process. Voice memo transcription, cross-platform conversation continuity.</td></tr>
<tr><td><b>A closed learning loop</b></td><td>Agent-curated memory with periodic nudges. Autonomous skill creation after complex tasks. Skills self-improve during use. FTS5 session search with LLM summarization for cross-session recall. <a href="https://github.com/plastic-labs/honcho">Honcho</a> dialectic user modeling. Compatible with the <a href="https://agentskills.io">agentskills.io</a> open standard.</td></tr>
<tr><td><b>Scheduled automations</b></td><td>Built-in cron scheduler with delivery to any platform. Daily reports, nightly backups, weekly audits — all in natural language, running unattended.</td></tr>
<tr><td><b>Delegates and parallelizes</b></td><td>Spawn isolated subagents for parallel workstreams. Write Python scripts that call tools via RPC, collapsing multi-step pipelines into zero-context-cost turns.</td></tr>
<tr><td><b>Runs anywhere, not just your laptop</b></td><td>Six terminal backends — local, Docker, SSH, Singularity, Modal, and Daytona. Daytona and Modal offer serverless persistence — your agent's environment hibernates when idle and wakes on demand, costing nearly nothing between sessions. Run it on a $5 VPS or a GPU cluster.</td></tr>
<tr><td><b>Research-ready</b></td><td>Batch trajectory generation, trajectory compression for training the next generation of tool-calling models.</td></tr>
</table>

---

## Quick Install

Clone this repo. There is no third-party hosted installer for this tree.

```bash
git clone https://github.com/jourdanlabs/omnis-wing.git
cd omnis-wing
uv sync --extra dev
# Ink TUI
cd ui-tui && npm install && npm run build && cd ..
WING_PYTHON=.venv/bin/python ./wing --tui
```

State lives in `~/.omnis-wing/`. Pre-rename installs migrate on first run (see `NOTICE`). The source checkout is not copied; the old directory is not deleted.

Packaged runtime (`~/.omnis-wing/wing-r4/…`) is built from this `main`. Path: `docs/PACKAGED-RUNTIME.md`.

---

## Getting Started

```bash
./wing              # Interactive CLI
./wing --tui        # Ink TUI (the product look)
./wing model        # Provider / model
./wing tools        # Tool configuration
./wing config set   # Config keys
./wing gateway      # Messaging gateway
./wing setup        # Setup wizard
./wing doctor       # Diagnose issues
```

Pull from `origin` (`jourdanlabs/omnis-wing`). Cherry-pick Nous security fixes via `upstream` per `docs/UPSTREAM-POLICY.md`.

Docs in-tree: `website/docs/`. Issues: https://github.com/jourdanlabs/omnis-wing/issues

---

## Optional: one-subscription Portal

WING works with whatever provider you want — that's not changing. If you'd rather not collect five separate API keys for the model, web search, image generation, TTS, and a cloud browser, `wing setup --portal` covers them under one subscription (OAuth host: portal.nousresearch.com — named exception, see `docs/WING-DEFAULTS.md`):

- **300+ models** — pick any of them with `/model <name>`
- **Tool Gateway** — web search, image generation, TTS, cloud browser, routed through the sub.

```bash
wing setup --portal
```

Check routing any time with `wing portal info`.

You can still bring your own keys per-tool whenever you want — the gateway is per-backend, not all-or-nothing.

---

## CLI vs Messaging Quick Reference

WING has two entry points: start the terminal UI with `wing`, or run the gateway and talk to it from Telegram, Discord, Slack, WhatsApp, Signal, or Email. Once you're in a conversation, many slash commands are shared across both interfaces.

| Action                         | CLI                                           | Messaging platforms                                                              |
| ------------------------------ | --------------------------------------------- | -------------------------------------------------------------------------------- |
| Start chatting                 | `wing`                                      | Run `wing gateway setup` + `wing gateway start`, then send the bot a message |
| Start fresh conversation       | `/new` or `/reset`                            | `/new` or `/reset`                                                               |
| Change model                   | `/model [provider:model]`                     | `/model [provider:model]`                                                        |
| Set a personality              | `/personality [name]`                         | `/personality [name]`                                                            |
| Retry or undo the last turn    | `/retry`, `/undo`                             | `/retry`, `/undo`                                                                |
| Compress context / check usage | `/compress`, `/usage`, `/insights [--days N]` | `/compress`, `/usage`, `/insights [days]`                                        |
| Browse skills                  | `/skills` or `/<skill-name>`                  | `/<skill-name>`                                                                  |
| Interrupt current work         | `Ctrl+C` or send a new message                | `/stop` or send a new message                                                    |
| Platform-specific status       | `/platforms`                                  | `/status`, `/sethome`                                                            |

For the full command lists, see in-tree `website/docs/user-guide/cli` and `website/docs/user-guide/messaging`.

---

## Documentation

Docs live in-tree under `website/docs/` (this repo). Defaults for look and model: `docs/WING-DEFAULTS.md`.

---

## Migrating from OpenClaw

If you're coming from OpenClaw, WING can automatically import your settings, memories, skills, and API keys.

**During first-time setup:** The setup wizard (`wing setup`) automatically detects `~/.openclaw` and offers to migrate before configuration begins.

**Anytime after install:**

```bash
wing claw migrate              # Interactive migration (full preset)
wing claw migrate --dry-run    # Preview what would be migrated
wing claw migrate --preset user-data   # Migrate without secrets
wing claw migrate --overwrite  # Overwrite existing conflicts
```

What gets imported:

- **SOUL.md** — persona file
- **Memories** — MEMORY.md and USER.md entries
- **Skills** — user-created skills → `~/.omnis-wing/skills/openclaw-imports/`
- **Command allowlist** — approval patterns
- **Messaging settings** — platform configs, allowed users, working directory
- **API keys** — allowlisted secrets (Telegram, OpenRouter, OpenAI, Anthropic, ElevenLabs)
- **TTS assets** — workspace audio files
- **Workspace instructions** — AGENTS.md (with `--workspace-target`)

See `wing claw migrate --help` for all options, or use the `openclaw-migration` skill for an interactive agent-guided migration with dry-run previews.

---

## Contributing

We welcome contributions! See `CONTRIBUTING.md` and `website/docs/developer-guide/contributing`.

Quick start for contributors — clone this repo:

```bash
git clone https://github.com/jourdanlabs/omnis-wing.git
cd omnis-wing
```

Then:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[all,dev]"
scripts/run_tests.sh
```

---

## Community

- 🐛 [Issues](https://github.com/jourdanlabs/omnis-wing/issues)
- 📚 [Skills Hub](https://agentskills.io)
- 🔌 [computer-use-linux](https://github.com/avifenesh/computer-use-linux) — Linux desktop-control MCP server for WING and other MCP hosts, with AT-SPI accessibility trees, Wayland/X11 input, screenshots, and compositor window targeting.

---

## License

MIT — see [LICENSE](LICENSE). Attribution for the upstream runtime is in `NOTICE` and the opening paragraph of this README.

Built by [JourdanLabs](https://github.com/jourdanlabs).
