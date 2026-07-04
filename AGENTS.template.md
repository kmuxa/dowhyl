<!--
  AGENTS.md TEMPLATE
  Copy this into the ROOT of a project you work on, renamed to AGENTS.md,
  then fill in the blanks. OpenCode (and most agent CLIs) read AGENTS.md as
  standing project context, so you don't re-explain your repo every session.

  Why it matters here: the build/test/lint commands below are what the agent
  runs to VERIFY its work — that verification is the router (cheap model tries,
  gate fails, it escalates). Accurate commands = reliable auto-escalation.
  Keep this file short and truthful; stale instructions are worse than none.
-->

# <Project name>

One-paragraph description of what this project is and who uses it.

## Stack
- Language(s) / runtime: <e.g. Go 1.23 / Node 22 / Python 3.12>
- Frameworks / key libs: <e.g. gin, React, FastAPI>
- Package manager: <e.g. go mod / pnpm / uv>

## Commands (the agent should run these to verify itself)
<!-- Use YOUR real commands. Examples per stack — delete the ones you don't use. -->
- Install:   `<go mod download | pnpm install | uv sync>`
- Build:     `<go build ./... | pnpm build | python -m build>`
- Test:      `<go test ./... | pnpm test | pytest -q>`
- Lint:      `<golangci-lint run | pnpm lint | ruff check .>`
- Format:    `<gofmt -w . | pnpm format | ruff format .>`
- Typecheck: `<—     | pnpm tsc --noEmit | pyright>`
- Run/dev:   `<go run ./cmd/app | pnpm dev | uvicorn app:app --reload>`   (dev server on <http://localhost:PORT>)

**Definition of done:** build passes, tests green, lint/format clean. For UI changes, the browser loop should open <http://localhost:PORT>, exercise the changed flow, and show no console errors before declaring done.

## Conventions
- <e.g. table-driven tests; errors wrapped with %w; no naked returns>
- <e.g. functional components + hooks; no class components>
- Commits: <e.g. Conventional Commits — feat:, fix:, chore:>
- Naming / structure: <where new files/modules go>

## Do NOT touch / send
- Never read, edit, or transmit: `.env*`, `secrets/`, `*.pem`, `**/credentials*`, CI secrets.
- Don't modify: `<generated dirs, vendored code, migrations already shipped>`.
- Don't add dependencies without flagging it first.

## Architecture notes (optional but valuable)
- Entry points: <e.g. cmd/app/main.go, src/index.ts>
- Data flow / modules: <2–4 bullets on how the pieces fit>
- Gotchas: <known sharp edges, flaky tests, external services needed to run>

## Model routing hint (optional)
- Use `smart` for planning and cross-module changes; `mid` for routine edits.
- This module is <sensitive/proprietary> → keep it on no-train lanes only
  (frontier API or NVIDIA Build), never free-tier or a China-hosted primary.
