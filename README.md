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

**Prerequisites you install yourself** (the script only checks and warns — it never installs anything): **Docker Desktop**, **jq**, **OpenCode** (`brew install sst/tap/opencode`), and optionally **gitleaks** (`brew install gitleaks`). On Apple Silicon the brew commands are identical — just make sure Homebrew is on your PATH (`eval "$(/opt/homebrew/bin/brew shellenv)"` in `~/.zshrc`). `setup.sh` is safe to fix-and-re-run: it won't overwrite `.env`/`primary.env` or regenerate an existing key. It also auto-generates a random `LITELLM_MASTER_KEY` if you leave the default, and stands up Postgres + Redis + LiteLLM (Postgres backs the virtual key + the $10 cap).

---

## How to use

Work happens through one command, run **in the directory you want the agent working on** — changes apply there directly, so git is your undo net:

```bash
code-agent plan     # read-only deep-dive → produces an implementation plan (zero file changes)
code-agent          # edit (default): makes changes, asking before each is applied
code-agent auto     # autonomous edits; prompts only before risky commands (rm, sudo, git push…)
code-agent full     # no prompts at all — reserve for committed work / branches
```

Inside OpenCode:

- **Plan** (`code-agent plan`, or the plan agent in-session) reasons read-only with the `smart` tier — edits are denied, so it's safe for pure research. Ask it to print the plan; implement it in a fresh `edit`/`auto` session.
- **Build** implements with the free `mid` tier (the default agent in `edit`/`auto`/`full`).
- It self-verifies with your compiler/tests/linters (LSP), and can drive a **real browser** (Playwright MCP) to open your app, click through, screenshot, and fix what breaks.
- It escalates to `smart` then `frontier` **only if verification fails** — so you pay for the expensive model only when the cheap one demonstrably couldn't do it. (This is the router: *the test suite decides.*)

Switch models any time with OpenCode's `/models` picker. The tiers you'll see: `frontier · smart · mid · long · cheap`, plus your primary. Run `status` to see exactly which models back each tier, your active primary, and how much of the $10 cap is left.

**Sensitive repo?** Secrets (keys/tokens/`.env`) are blocked from leaving automatically by the guardrail, whatever tier you pick. For proprietary *code* (not a secret), routing is your call — pick a no-train tier (`frontier` or NVIDIA), or use safe mode, which refuses to load a China-hosted primary so you can't send that repo through it by accident:

```bash
SAFE=1 code-agent auto             # ignores the CN primary; uses no-train gateway lanes
```

Useful commands:

```bash
status                         # gateway up? how much of the $10 cap is left? which lanes are active?
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

## Permission modes (how much the agent may do)

The agent works **directly in your current directory** — no worktrees, no containers. Control comes from a permission ladder, enforced by each agent's own native permission system:

```bash
code-agent plan     # read-only: researches the codebase, produces a plan — zero file changes
code-agent          # edit (default): proposes changes, asks before applying each
code-agent auto     # applies edits freely; asks only before risky commands (rm, sudo, git push…)
code-agent full     # no prompts at all — full autonomy (committed work / branches only)
```

| Mode | OpenCode | Claude Code | Codex |
|---|---|---|---|
| **plan** | plan agent + `edit: deny` overlay | `--permission-mode plan` | `--sandbox read-only` |
| **edit** | `edit`/`bash` = ask | `--permission-mode default` | default approvals |
| **auto** | edits allowed; risky bash asks (10-rule list) | `--permission-mode acceptEdits` (Shift+Tab reaches Claude's native `auto` classifier if available) | `--full-auto` |
| **full** | everything allowed | `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` |

The honest trade-off vs the old worktree/sandbox: containment is gone, so **git is the undo net** — the launcher warns when you start with uncommitted changes, and the intended rhythm is `plan → edit/auto → review diff → commit`, with `full` reserved for a branch. The secret-scan guardrail and gitleaks hook are unchanged. Flag names above track current agent CLIs — if one errors, check that agent's docs (they shift). The old `Dockerfile`, `sandbox/opencode.sb`, and `opencode/opencode.docker.json` are no longer used and are safe to delete.

---

## Choosing the coding agent (the "cockpit")

The gateway is agent-agnostic, so the cockpit is a per-session choice — same idea as the swappable primary:

```bash
code-agent [mode]                           # OpenCode (default)   mode = plan|edit|auto|full
AGENT=claude code-agent auto                # Claude Code → your primary if set, else gateway tiers
AGENT=claude BACKEND=gateway code-agent …   # Claude Code → force the gateway tiers
AGENT=codex  code-agent plan                # Codex CLI → gateway tiers
```

Each cockpit is a **separate CLI you install yourself** (the kit never installs software). No Anthropic/OpenAI account is needed against the gateway — the launcher passes your `GATEWAY_KEY` as the auth token.

| Cockpit | Install | One-time setup | Tiers appear as | Project memory |
|---|---|---|---|---|
| **OpenCode** | `brew install sst/tap/opencode` | none — kit ships `opencode/opencode.json` | "Local Gateway" group in `/models` | `AGENTS.md` (native) |
| **Claude Code** | `npm i -g @anthropic-ai/claude-code` | register the browser loop once: `claude mcp add playwright -- npx -y @playwright/mcp@latest` | `/model` picker entries labeled "From gateway" (launcher enables discovery); defaults: smart, background=cheap | reads `CLAUDE.md` — the launcher auto-creates one containing `@AGENTS.md` if missing (kept in your repo; commit or delete) |
| **Codex CLI** | `npm i -g @openai/codex` | two files: provider + Playwright MCP in `~/.codex/config.toml` (with `wire_api = "responses"` — Codex dropped `"chat"` in Feb 2026), profile in `~/.codex/kit.config.toml` — **run `AGENT=codex code-agent` once and it prints both**; switch tiers per-run with `-m mid` | profile `kit`, pinned to `smart` | `AGENTS.md` (native) |

Notes: env is read once at agent start, so switch cockpits **between** sessions; MCP registration is per-agent, so OpenCode's Playwright wiring doesn't carry over automatically; `AGENT=claude` with the GLM primary is the classic pairing (Claude Code's harness on your flat-rate plan), and `BACKEND=gateway` gives Claude Code the whole tier system with the cap and secret guardrail intact.

---

## What's in here

```
setup.sh                     one-command bootstrap
.env                         provider keys (free + optional + paid)
config/litellm.yaml          gateway: tiers, fallback, cooldown, cache, $10 cap
config/primary.env           your flat-rate primary (GLM default, Qwen commented)
guardrails/secret_scan.py    fail-closed guardrail: blocks secrets leaving your machine
bin/code-agent               launcher: cockpit (opencode/claude/codex) + permission modes, runs in your current dir
bin/status                   health + remaining budget + active lanes
bin/refresh-models           catalog-drift alert (schedule nightly)
sandbox/opencode.sb          (legacy, unused — safe to delete)
opencode/opencode.json       OpenCode: gateway provider + Playwright MCP + plan/build agents
opencode/opencode.docker.json  (legacy, unused — safe to delete)
docker-compose.yml           Postgres + Redis + LiteLLM
Dockerfile                   (legacy, unused — safe to delete)
AGENTS.template.md           copy into your repos (as AGENTS.md) to give the agent context
.gitignore                   keeps your keys (.env, primary.env) out of git
```

For the full best-first catalog of every coding model per tier (to add/remove lanes), see the companion planning doc.

---

## Give the agent project context (AGENTS.md)

Copy `AGENTS.template.md` into any repo you work on, rename it `AGENTS.md`, and fill in the blanks — OpenCode reads it as standing context so you don't re-explain your project each session. Most important are the **build / test / lint commands**: those are what the agent runs to verify itself, and that verification is the router (cheap model tries → gate fails → it escalates). Accurate commands make the auto-escalation reliable. Keep it short and truthful.

---

## Privacy & safety, in one place

- **Secrets never leave:** `secret_scan.py` blocks any prompt containing a key/token/private-key/`.env`-reference before it reaches a provider (fail-closed), and the gitleaks hook stops them entering git.
- **Sensitive code:** route only to `frontier` (paid API, no-train) or free **NVIDIA Build** (no-train). Never to Gemini-free or a ⚠️ China-hosted primary.
- **Blast radius:** permission modes gate what the agent may do, and it edits your working directory directly — so git is the undo net: work on a branch, commit before `auto`/`full`, review diffs before merging. The launcher warns when you start with uncommitted changes.
- **Spend:** hard-capped at $10/30 days by the gateway (`fail_closed_budget_enforcement`, backed by Postgres). When spent, frontier falls back to free lanes automatically.

---

## Troubleshooting

- **`status` says gateway down** → `docker compose up -d`; logs: `docker compose logs litellm`.
- **Key-gen returned HTTP 500 / "DB not connected"** → LiteLLM has no `DATABASE_URL`. Usually because your `.env` predates the Postgres addition (setup never overwrites `.env`). Re-running `setup.sh` now repairs it automatically; or do it manually: `echo 'POSTGRES_PASSWORD=litellm' >> .env && echo 'DATABASE_URL=postgresql://litellm:litellm@postgres:5432/litellm' >> .env`, then `docker compose up -d --force-recreate litellm`, and check `curl -s localhost:4000/health/readiness | jq -r '.db'` shows `connected`. To skip the cap entirely, set `GATEWAY_KEY` in `.env` to your `LITELLM_MASTER_KEY`. (If Postgres was ever initialized with a different password, `docker compose down -v` to reset its volume.)
- **`http://localhost:4000/v1` shows "not found" in a browser** → expected: `/v1` has no page. The client calls `/v1/chat/completions`. Test properly: `curl http://localhost:4000/v1/models -H "Authorization: Bearer $GATEWAY_KEY"`. (If OpenCode ever 404s on real calls, try the base URL without `/v1`.)
- **Test prompt returns nothing** → you have no key for that lane yet; add `GEMINI_API_KEY` or `GROQ_API_KEY` and `docker compose restart litellm`.
- **A model errors** → it was probably renamed; run `refresh-models`, update `config/litellm.yaml` (fallbacks cover you meanwhile).
- **Guardrail won't load** → your LiteLLM version may register guardrails differently; see the header of `guardrails/secret_scan.py` for the callback-style alternative and check current LiteLLM docs.
- **OpenCode can't see the tiers** → confirm `GATEWAY_KEY` is in `.env` and `OPENCODE_CONFIG` points at `opencode/opencode.json`; verify the config fields against current OpenCode docs (the schema evolves).

> Prices, model IDs, and free-tier limits shift monthly — this kit is built so drift is a config edit, not a rebuild. Re-verify specifics before relying on a number.

## Known Issues
- Groq not recording any requests on litellm nor console
- Openrouter not recording any requests on litellm, but seeing 429 on console. setting rpm: 15 hasn't changed this behaviour





  "//model": "Your flat-rate PRIMARY (GLM by default) is picked up from config/primary.env via the ANTHROPIC_* env vars and appears as the built-in anthropic provider. Switch with the /models picker in OpenCode, or set a default here."

  "//": "Verify field names against current OpenCode docs — the schema evolves. This wires (1) the local gateway as a provider exposing the tier aliases, (2) the Playwright browser loop via MCP, (3) plan->smart / build->mid model mapping.",


anthropic
openai
cerebros
grok
deepseek




3. add at least one of the frontiers - I get Claude already, or?



can I know which providers/models were used for each prompt?


how to delete a branch?
which coding agent is in use? can I use claude code/codex/ switching between them?
does openrouter have any free models that can displace any of what we got? what of Github

lots of providers aren't mapped in litellm.yaml but their api key env vars are available. is it that they don't have any models that can do better than the current selection?

why does pressing tab to switch between models switch between only smart and mid


create an ordered list of value for money for all the providers listed stating how much I'll need to pay for which plan
is what we have now truly better than any free agentic coding tool out there 
and when I spend up to $10 a month, is it still better than paying $10 for any of the agentic coding tools out there?



be able to take images
how to use with mcp
long running agent + dashboard