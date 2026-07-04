#!/usr/bin/env bash
# ============================================================================
#  setup.sh — one command to stand up the agentic coding kit.
#  Safe to re-run. It won't overwrite your .env or primary.env once created.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"
say() { printf "\n\033[1m%s\033[0m\n" "$*"; }
ok()  { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn(){ printf "  \033[33m!\033[0m %s\n" "$*"; }

say "1/6  Checking prerequisites"
need_docker=1
command -v docker >/dev/null && docker compose version >/dev/null 2>&1 && { ok "docker + compose"; need_docker=0; } || warn "install Docker Desktop (needed to run the gateway)"
command -v jq >/dev/null && ok "jq" || warn "install jq  (brew install jq)  — needed for setup + status"
command -v opencode >/dev/null && ok "opencode" || warn "install OpenCode:  brew install sst/tap/opencode   (or: npm i -g opencode-ai)"
command -v gitleaks >/dev/null && ok "gitleaks (secret pre-commit)" || warn "optional: brew install gitleaks"

say "2/6  Config files"
[[ -f .env ]] || { cp .env.example .env; ok "created .env"; }
[[ -f config/primary.env ]] || { cp config/primary.env.example config/primary.env; ok "created config/primary.env (GLM default)"; }
chmod +x bin/* 2>/dev/null || true
ok "made bin/ scripts executable"

# auto-generate an admin key if still the placeholder
if grep -q '^LITELLM_MASTER_KEY=sk-local-master-change-me$' .env; then
  newkey="sk-$(openssl rand -hex 24 2>/dev/null || echo local-$(date +%s))"
  tmp=$(mktemp); sed "s#^LITELLM_MASTER_KEY=.*#LITELLM_MASTER_KEY=${newkey}#" .env > "$tmp" && mv "$tmp" .env
  ok "generated a random LITELLM_MASTER_KEY"
fi

# stop here if the required free keys aren't filled yet
set -a; . ./.env; set +a
if [[ -z "${NVIDIA_API_KEY:-}" && -z "${GEMINI_API_KEY:-}" && -z "${GROQ_API_KEY:-}" ]]; then
  warn "No provider keys yet. Edit .env and add at least NVIDIA_API_KEY and GEMINI_API_KEY (both free, no card)."
  warn "Then re-run ./setup.sh"
  exit 0
fi
ok "found at least one provider key"

if [[ "$need_docker" -eq 1 ]]; then
  warn "Docker not available — skipping gateway start. Install it and re-run."
  exit 0
fi

say "3/6  Starting gateway (Postgres + Redis + LiteLLM)"
docker compose up -d
printf "  waiting for gateway"
for _ in $(seq 1 30); do
  curl -fsS http://localhost:4000/health/liveliness >/dev/null 2>&1 && break
  printf "."; sleep 2
done; echo
curl -fsS http://localhost:4000/health/liveliness >/dev/null 2>&1 && ok "gateway up at http://localhost:4000" || { warn "gateway didn't come up — check: docker compose logs litellm"; exit 1; }

say "4/6  Creating the \$10/month budget-capped key"
if grep -qE '^GATEWAY_KEY=.+' .env; then
  ok "GATEWAY_KEY already set (skipping)"
else
  key=$(curl -fsS http://localhost:4000/key/generate \
    -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" -H "Content-Type: application/json" \
    -d '{"max_budget":10,"budget_duration":"30d","models":["frontier","smart","mid","long","cheap","overflow"]}' \
    | jq -r '.key')
  if [[ -n "$key" && "$key" != "null" ]]; then
    # portable in-place edit
    tmp=$(mktemp); sed "s#^GATEWAY_KEY=.*#GATEWAY_KEY=${key}#" .env > "$tmp" && mv "$tmp" .env
    ok "created + saved GATEWAY_KEY (hard cap: \$10 / 30 days)"
  else
    warn "could not create budgeted key (virtual keys need Postgres — check: docker compose ps postgres)."
    warn "Unblock now: set GATEWAY_KEY in .env to your LITELLM_MASTER_KEY (no cap), or re-run once Postgres is healthy."
  fi
fi

say "5/6  Secret pre-commit hook (defense-in-depth)"
if command -v gitleaks >/dev/null && git rev-parse --git-dir >/dev/null 2>&1; then
  hook="$(git rev-parse --git-dir)/hooks/pre-commit"
  printf '#!/bin/sh\ngitleaks protect --staged --redact -v || { echo "gitleaks blocked commit (secret detected)"; exit 1; }\n' > "$hook"
  chmod +x "$hook"; ok "installed gitleaks pre-commit hook"
else
  warn "skipped gitleaks hook (install gitleaks and run inside your project's git repo to enable)"
fi

say "6/6  Smoke test"
curl -fsS http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer ${GATEWAY_KEY:-$LITELLM_MASTER_KEY}" -H "Content-Type: application/json" \
  -d '{"model":"cheap","messages":[{"role":"user","content":"reply with the word: ready"}]}' \
  | jq -r '.choices[0].message.content' 2>/dev/null | grep -qi ready && ok "gateway answered a test prompt" \
  || warn "no test answer — likely no key for the 'cheap' lane yet (add GEMINI_API_KEY or GROQ_API_KEY)"

say "Done."
cat <<'EOF'
  Next:
    1) (optional) paste your GLM key into  config/primary.env
    2) add bin/ to your PATH:   export PATH="$PWD/bin:$PATH"
    3) in any project:          code-agent my-first-task
    4) check anytime:           status
  See README.md for the daily workflow and how to switch primary/sandbox.
EOF
