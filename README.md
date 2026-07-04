# agentic-coding-kit

A bespoke, terminal-first agentic coding setup that mixes the best **free** models with **one cheap flat-rate** coding subscription, keeps your secrets on your machine, and caps any paid spend at **$10/month**. Works for every language.

It's a **1 + N** design: one flat-rate primary (GLM by default) is your zero-anxiety daily driver, and a local gateway serves free lanes for bulk work, huge-context reads, and a hard-capped frontier escalation — with automatic failover so no single rate limit or outage stops you.

---

## Quick start (about 5 minutes)

```bash
git clone <this-repo> agentic-coding-kit && cd agentic-coding-kit
cp .env.example .env

# 1) Get two FREE keys (no credit card, they don't train on your code):
#    NVIDIA  -> https://build.nvidia.com
#    Gemini  -> https://aistudio.google.com
#    Paste them into .env  (NVIDIA_API_KEY=…, GEMINI_API_KEY=…)

./setup.sh                     # checks tools, starts the gateway, makes the $10-cap key

export PATH="$PWD/bin:$PATH"   # add the helper commands (put this in ~/.zshrc)
```

That's a working **$0** setup. To add your GLM primary, paste your key into `config/primary.env` (already created, GLM pre-selected). To add frontier Claude/GPT, put `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in `.env` — pay-as-you-go, capped at $10.

Prerequisites the script checks for: **Docker Desktop**, **jq**, **OpenCode** (`brew install sst/tap/opencode`), and optionally **gitleaks**.

---

## How to use

Work happens through one command, from inside any git project:

```bash
code-agent add-user-auth       # spins up an isolated worktree + sandbox, opens OpenCode
```

Inside OpenCode:

- **Plan mode** (`/plan`) reasons read-only with the `smart` tier. Use it for anything non-trivial first.
- **Build mode** (`/build`) implements with the free `mid` tier.
- It self-verifies with your compiler/tests/linters (LSP), and can drive a **real browser** (Playwright MCP) to open your app, click through, screenshot, and fix what breaks.
- It escalates to `smart` then `frontier` **only if verification fails** — so you pay for the expensive model only when the cheap one demonstrably couldn't do it. (This is the router: *the test suite decides.*)

Switch models any time with OpenCode's `/models` picker. The tiers you'll see: `frontier · smart · mid · long · cheap`, plus your primary.

Useful commands:

```bash
status                         # gateway up? how much of the $10 cap is left? which lanes are active?
code-agent --clean add-user-auth   # remove a finished worktree + its branch
refresh-models                 # check whether any configured model was renamed/removed
```

---

## Switching the flat-rate primary

Edit `config/primary.env`, uncomment **one** block, save. Options (all a 3-line swap):

| Primary | Cost | Privacy |
|---|---|---|
| **GLM** (default) | ~$3–18/mo | ⚠️ China-hosted |
| **Alibaba/Qwen** | ~$15–50/mo | ✅ US/EU/SG — the privacy-safer swap |
| MiniMax / Kimi / Cerebras Code / Xiaomi | varies | see file |

These plans are **interactive-use-only**, so the primary is used directly by OpenCode and is never routed through the gateway. Keep sensitive repos off the ⚠️ ones — route those to a no-train lane (frontier API, or free NVIDIA Build). *Codex Go ($8, GPT-5.5) and GitHub Copilot aren't swaps — run them as parallel cockpits (`codex`, or Copilot in VS Code).*

---

## Switching the sandbox

`code-agent` isolates the agent two ways: a **git worktree** (throwaway branch for its code changes — always on) and a **sandbox** (contains rogue/injected commands):

```bash
code-agent my-task                 # default: OS sandbox — writes limited to the worktree
SANDBOX=docker code-agent my-task  # container — writes + network fully contained (for unattended runs)
SANDBOX=none  code-agent my-task   # permission prompts only
```

The OS mode (macOS Seatbelt / Linux bubblewrap) blocks writes outside the worktree but allows network (the agent must reach the gateway and your primary). For **network-egress control** (blocking exfiltration), use `SANDBOX=docker`. This mirrors how Claude Code does it — permission prompts + an OS sandbox, with a container/VM as the real boundary for autonomous work. To build the container image for docker mode, see `sandbox/` (a minimal non-root image with the project mounted read-write).

---

## What's in here

```
setup.sh                     one-command bootstrap
.env                         provider keys (free + optional + paid)
config/litellm.yaml          gateway: tiers, fallback, cooldown, cache, $10 cap
config/primary.env           your flat-rate primary (GLM default, Qwen commented)
guardrails/secret_scan.py    fail-closed guardrail: blocks secrets leaving your machine
bin/code-agent               launcher (worktree + sandbox toggle)
bin/status                   health + remaining budget + active lanes
bin/refresh-models           catalog-drift alert (schedule nightly)
sandbox/opencode.sb          macOS Seatbelt profile
opencode/opencode.json       OpenCode: gateway provider + Playwright MCP + plan/build modes
docker-compose.yml           Redis + LiteLLM
```

For the full best-first catalog of every coding model per tier (to add/remove lanes), see the companion planning doc.

---

## Privacy & safety, in one place

- **Secrets never leave:** `secret_scan.py` blocks any prompt containing a key/token/private-key/`.env`-reference before it reaches a provider (fail-closed), and the gitleaks hook stops them entering git.
- **Sensitive code:** route only to `frontier` (paid API, no-train) or free **NVIDIA Build** (no-train). Never to Gemini-free or a ⚠️ China-hosted primary.
- **Blast radius:** the worktree + sandbox mean a bad or prompt-injected command can't touch your real tree; `SANDBOX=docker` also contains the network.
- **Spend:** hard-capped at $10/30 days by the gateway (`fail_closed_budget_enforcement`). When spent, frontier falls back to free lanes automatically.

---

## Troubleshooting

- **`status` says gateway down** → `docker compose up -d`; logs: `docker compose logs litellm`.
- **Test prompt returns nothing** → you have no key for that lane yet; add `GEMINI_API_KEY` or `GROQ_API_KEY` and `docker compose restart litellm`.
- **A model errors** → it was probably renamed; run `refresh-models`, update `config/litellm.yaml` (fallbacks cover you meanwhile).
- **Guardrail won't load** → your LiteLLM version may register guardrails differently; see the header of `guardrails/secret_scan.py` for the callback-style alternative and check current LiteLLM docs.
- **OpenCode can't see the tiers** → confirm `GATEWAY_KEY` is in `.env` and `OPENCODE_CONFIG` points at `opencode/opencode.json`; verify the config fields against current OpenCode docs (the schema evolves).

> Prices, model IDs, and free-tier limits shift monthly — this kit is built so drift is a config edit, not a rebuild. Re-verify specifics before relying on a number.
