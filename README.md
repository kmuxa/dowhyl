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

Work happens through one command, from inside any git project:

```bash
code-agent add-user-auth       # spins up an isolated worktree + sandbox, opens OpenCode
```

Inside OpenCode:

- **Plan mode** (`/plan`) reasons read-only with the `smart` tier. Use it for anything non-trivial first.
- **Build mode** (`/build`) implements with the free `mid` tier.
- It self-verifies with your compiler/tests/linters (LSP), and can drive a **real browser** (Playwright MCP) to open your app, click through, screenshot, and fix what breaks.
- It escalates to `smart` then `frontier` **only if verification fails** — so you pay for the expensive model only when the cheap one demonstrably couldn't do it. (This is the router: *the test suite decides.*)

Switch models any time with OpenCode's `/models` picker. The tiers you'll see: `frontier · smart · mid · long · cheap`, plus your primary. Run `status` to see exactly which models back each tier, your active primary, and how much of the $10 cap is left.

**Sensitive repo?** Secrets (keys/tokens/`.env`) are blocked from leaving automatically by the guardrail, whatever tier you pick. For proprietary *code* (not a secret), routing is your call — pick a no-train tier (`frontier` or NVIDIA), or use safe mode, which refuses to load a China-hosted primary so you can't send that repo through it by accident:

```bash
SAFE=1 code-agent my-task          # ignores the CN primary; uses no-train gateway lanes
```

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
SANDBOX=docker code-agent          # container — repo mounted, rest of your Mac isolated (unattended runs)
SANDBOX=none  code-agent my-task   # permission prompts only
```

The OS mode (macOS Seatbelt / Linux bubblewrap) limits the agent's writes to the worktree; network stays open because it must reach the gateway and your primary. The **docker mode** gives the stronger boundary: your repo is mounted at `/work` and nothing else on your Mac is reachable by the agent's filesystem — the right choice for unattended "let it run" sessions. (It isolates the filesystem and process; network stays open for the gateway and models. True network-egress allow-listing means running behind a proxy — advanced, not included.) This mirrors how Claude Code works: permission prompts + an OS sandbox, with a container as the real boundary for autonomous work.

Build the container image once (browser loop included, ~1.2 GB):

```bash
docker build -t opencode-sandbox:latest .
docker build --build-arg WITH_BROWSER=false -t opencode-sandbox:latest .   # slim (~350 MB), no browser
```

Note: docker mode mounts the whole repo (a worktree's git link lives outside a mount, so it wouldn't work in a container) — check out a feature branch first if you want change isolation there.

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
opencode/opencode.docker.json  same, but gateway via host.docker.internal (baked into the image)
docker-compose.yml           Redis + LiteLLM
Dockerfile                   builds opencode-sandbox:latest for SANDBOX=docker
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
- **Blast radius:** the worktree + OS sandbox keep the agent's writes off your real tree; `SANDBOX=docker` fully isolates the filesystem/processes (network stays open for the gateway/models).
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
