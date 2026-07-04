# ============================================================================
#  opencode-sandbox — the image used by `SANDBOX=docker code-agent`.
#  Strong isolation: your repo is mounted at /work; nothing else on your Mac
#  is reachable by the agent's filesystem. Runs as a non-root user.
#
#  Build (browser loop included, ~1.2 GB):
#     docker build -t opencode-sandbox:latest .
#  Build slim (no browser, ~350 MB) — skip Playwright:
#     docker build --build-arg WITH_BROWSER=false -t opencode-sandbox:latest .
#
#  Network note: the container uses normal networking so it can reach your
#  gateway (host.docker.internal:4000) and your flat-rate primary. The docker
#  win is FILESYSTEM/PROCESS isolation. For network EGRESS allow-listing, run
#  it on a custom docker network behind a proxy (advanced; not included).
# ============================================================================
# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim
ARG WITH_BROWSER=true

# tools OpenCode expects: git (repo ops), ripgrep (search), curl/jq, ca-certs
RUN apt-get update && apt-get install -y --no-install-recommends \
      git ripgrep ca-certificates curl jq \
 && rm -rf /var/lib/apt/lists/*

# OpenCode + the Playwright MCP server (pre-installed so first run is offline-fast)
RUN npm install -g opencode-ai@latest @playwright/mcp@latest

# optional: chromium for the in-container browser-testing loop
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
RUN if [ "$WITH_BROWSER" = "true" ]; then \
      npx -y playwright@latest install --with-deps chromium && \
      chmod -R a+rx /opt/pw-browsers ; \
    else \
      echo "built without browser (browser-testing MCP will be disabled)"; \
    fi

# non-root runtime user
RUN useradd -m -u 10001 agent
USER agent

# baked config: gateway via host.docker.internal, Playwright MCP enabled
COPY --chown=agent:agent opencode/opencode.docker.json /home/agent/.config/opencode/opencode.json
ENV OPENCODE_CONFIG=/home/agent/.config/opencode/opencode.json

WORKDIR /work
ENTRYPOINT ["opencode"]
