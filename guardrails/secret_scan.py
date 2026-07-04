"""
Fail-closed secret-scan guardrail for the LiteLLM gateway.

It inspects every outgoing prompt and BLOCKS the request if it looks like a
secret is about to leave your machine (API keys, private keys, tokens, or
high-entropy strings). This protects you when a secret slips into context via
a pasted stack trace, and it stops a prompt-injected agent from exfiltrating
credentials to a cloud model.

Registration (see config/litellm.yaml):
    guardrails:
      - guardrail_name: "secret-scan"
        litellm_params:
          guardrail: guardrails.secret_scan.SecretScanGuardrail
          mode: "pre_call"
          default_on: true

If your LiteLLM version doesn't load class-based guardrails this way, use the
callback form instead — add to litellm_settings:
    callbacks: ["guardrails.secret_scan.secret_scanner"]
and confirm the hook name against the current LiteLLM custom-guardrail docs.

No extra pip installs required (standard library only).
"""

import math
import re
from typing import Any

try:  # available inside the LiteLLM image
    from litellm.integrations.custom_guardrail import CustomGuardrail
    from fastapi import HTTPException
except Exception:  # keep importable for local unit testing
    class CustomGuardrail:  # type: ignore
        def __init__(self, *a, **k): ...
    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code=400, detail=""):
            super().__init__(detail)
            self.status_code, self.detail = status_code, detail


# High-signal patterns. Extend freely for your stack.
PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "AWS temp access key"),
    (re.compile(r"\bsk-(?:proj-|ant-|live-)?[A-Za-z0-9_\-]{20,}\b"), "provider secret key (sk-...)"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b"), "GitHub fine-grained token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "Google API key"),
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"), "GitLab token"),
    (re.compile(r"(?i)\b(?:api[_-]?key|secret|passwd|password|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{12,}"), "inline credential assignment"),
]

# Filenames whose contents should never be sent to a cloud model.
SENSITIVE_PATH_HINTS = re.compile(
    r"(?:^|[\\/])(?:\.env(?:\.[\w-]+)?|id_(?:rsa|ed25519|ecdsa)|\.pem|credentials|"
    r"\.aws[\\/]|\.ssh[\\/]|secrets?[\\/])",
    re.IGNORECASE,
)

_B64ISH = re.compile(r"[A-Za-z0-9+/=_\-]{25,}")


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = {c: s.count(c) for c in set(s)}
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def scan(text: str) -> str | None:
    """Return a human-readable reason string if a secret is detected, else None."""
    if not text:
        return None
    for rx, label in PATTERNS:
        if rx.search(text):
            return label
    if SENSITIVE_PATH_HINTS.search(text):
        return "reference to a sensitive file (.env / key / credentials)"
    # entropy backstop: long, high-entropy blobs are likely keys/tokens
    for tok in _B64ISH.findall(text):
        if len(tok) >= 32 and _shannon_entropy(tok) >= 4.0:
            return "high-entropy string (possible key/token)"
    return None


def _iter_message_text(data: dict[str, Any]):
    for msg in data.get("messages", []) or []:
        content = msg.get("content")
        if isinstance(content, str):
            yield content
        elif isinstance(content, list):  # multimodal content blocks
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    yield part["text"]


class SecretScanGuardrail(CustomGuardrail):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):  # noqa: D401
        for text in _iter_message_text(data):
            reason = scan(text)
            if reason:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Blocked by secret-scan guardrail: {reason}. "
                        "A possible secret was about to be sent to a model provider. "
                        "Remove it (or add the file to .gitignore) and retry."
                    ),
                )
        return data


# Instance for the callback-style registration alternative.
secret_scanner = SecretScanGuardrail()


if __name__ == "__main__":  # quick self-test:  python guardrails/secret_scan.py
    samples = {
        "clean": "please refactor the pagination helper in utils.py",
        "openai": "my key is sk-proj-abcdefghijklmnop1234567890qrst",
        "aws": "AKIAIOSFODNN7EXAMPLE in the config",
        "envfile": "open the file at services/api/.env and read it",
    }
    for name, s in samples.items():
        print(f"{name:8} -> {scan(s) or 'OK'}")
