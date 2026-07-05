"""
Fail-closed secret-scan guardrail for the LiteLLM gateway.

Blocks a request if a prompt looks like it contains a secret. When it fires it
reports WHICH kind of match and a REDACTED preview + message location, so you
can find and fix it. Two layers:
  1) ~40 explicit provider key/token patterns (always on).
  2) a high-entropy backstop for unknown base64/hex secrets. Common benign
     shapes (lockfile integrity hashes, git SHAs, UUIDs) are skipped. Disable
     the backstop only, keeping the explicit patterns, with:
        SECRET_SCAN_ENTROPY=off        (set in .env, then restart litellm)

Registration is in config/litellm.yaml (guardrails:). Standard library only.
"""

import math
import os
import re

try:
    from litellm.integrations.custom_guardrail import CustomGuardrail
    from fastapi import HTTPException
except Exception:  # importable for local unit testing
    class CustomGuardrail:  # type: ignore
        def __init__(self, *a, **k): ...
    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code=400, detail=""):
            super().__init__(detail); self.status_code, self.detail = status_code, detail

ENTROPY_ON = os.environ.get("SECRET_SCAN_ENTROPY", "on").lower() not in ("off", "0", "false", "no")
ENTROPY_MIN = 4.5       # bits/char (base64 blobs ~5-6; lowercase hex maxes at 4.0 so SHAs won't hit this)
ENTROPY_MINLEN = 40

PATTERNS = [
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY(?: BLOCK)?-----"), "private key block"),
    (re.compile(r"\bPuTTY-User-Key-File-\d"), "PuTTY private key"),
    (re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|A3T[A-Z0-9])[A-Z0-9]{16}\b"), "AWS access key id"),
    (re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+]{40}"), "AWS secret access key"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "Google API key"),
    (re.compile(r"\bya29\.[0-9A-Za-z_\-]+"), "Google OAuth access token"),
    (re.compile(r"\b1//[0-9A-Za-z_\-]{20,}"), "Google OAuth refresh token"),
    (re.compile(r'"type"\s*:\s*"service_account"'), "GCP service-account JSON"),
    (re.compile(r"(?i)AccountKey=[A-Za-z0-9+/=]{80,}"), "Azure storage account key"),
    (re.compile(r"\bSharedAccessKey=[A-Za-z0-9+/=]{20,}"), "Azure SAS key"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), "Anthropic API key"),
    (re.compile(r"\bsk-(?:proj|svcacct|admin)?-?[A-Za-z0-9_\-]{20,}"), "OpenAI API key"),
    (re.compile(r"\bsk-or-v1-[a-f0-9]{40,}"), "OpenRouter key"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), "Groq key"),
    (re.compile(r"\bnvapi-[A-Za-z0-9_\-]{20,}"), "NVIDIA API key"),
    (re.compile(r"\bhf_[A-Za-z0-9]{30,}"), "Hugging Face token"),
    (re.compile(r"\br8_[A-Za-z0-9]{35,}"), "Replicate token"),
    (re.compile(r"\bpplx-[A-Za-z0-9]{40,}"), "Perplexity key"),
    (re.compile(r"\bxai-[A-Za-z0-9]{60,}"), "xAI (Grok) key"),
    (re.compile(r"\bdapi[a-f0-9]{32,}"), "Databricks token"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}"), "GitHub fine-grained PAT"),
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"), "GitLab PAT"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"\bxapp-\d-[A-Z0-9]+-\d+-[a-f0-9]+"), "Slack app token"),
    (re.compile(r"https://hooks\.slack\.com/services/T[A-Za-z0-9_]+/B[A-Za-z0-9_]+/[A-Za-z0-9]+"), "Slack webhook"),
    (re.compile(r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{40,}"), "SendGrid key"),
    (re.compile(r"\bkey-[a-f0-9]{32}\b"), "Mailgun key"),
    (re.compile(r"\b[MNO][A-Za-z0-9_\-]{23}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,}"), "Discord bot token"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b"), "Telegram bot token"),
    (re.compile(r"\bAC[a-f0-9]{32}\b"), "Twilio account SID"),
    (re.compile(r"\bSK[a-f0-9]{32}\b"), "Twilio API key SID"),
    (re.compile(r"\b[rs]k_live_[A-Za-z0-9]{20,}"), "Stripe live secret key"),
    (re.compile(r"\bsk_test_[A-Za-z0-9]{20,}"), "Stripe test secret key"),
    (re.compile(r"\bwhsec_[A-Za-z0-9]{20,}"), "Stripe webhook secret"),
    (re.compile(r"\bshp(?:at|ca|pa|ss)_[a-fA-F0-9]{32}"), "Shopify token"),
    (re.compile(r"\bsq0(?:atp|csp)-[A-Za-z0-9_\-]{22,}"), "Square token"),
    (re.compile(r"\bEAAA[A-Za-z0-9_\-]{60,}"), "Square/Facebook access token"),
    (re.compile(r"\bdo[oprt]_v1_[a-f0-9]{64}"), "DigitalOcean token"),
    (re.compile(r"\bnpm_[A-Za-z0-9]{36}"), "npm token"),
    (re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{50,}"), "PyPI token"),
    (re.compile(r"\bAAAA[A-Za-z0-9_\-]{7}:[A-Za-z0-9_\-]{140,}"), "Firebase/FCM server key"),
    (re.compile(r"\bntn_[A-Za-z0-9]{40,}"), "Notion token"),
    (re.compile(r"\bsecret_[A-Za-z0-9]{43}\b"), "Notion legacy token"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "JWT"),
    (re.compile(r"(?i)\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|mariadb|redis|rediss|amqps?)://[^\s:@/]+:[^\s@/]+@"), "DB/URI with embedded credentials"),
    (re.compile(r"(?i)\bhttps?://[^\s:@/]+:[^\s@/]+@[^\s/]+"), "URL with basic-auth credentials"),
    (re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]{20,}"), "Bearer authorization header"),
    (re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|passwd|password|private[_-]?key)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-\.]{12,}"), "inline credential assignment"),
]

SENSITIVE_PATH_HINTS = re.compile(
    r"(?:^|[\\/])(?:\.env(?:\.[\w-]+)?|id_(?:rsa|ed25519|ecdsa|dsa)|\.pem|\.p12|\.pfx|\.key|"
    r"credentials?|\.aws[\\/]|\.ssh[\\/]|\.config[\\/]gcloud[\\/]|secrets?[\\/]|kubeconfig|"
    r"\.npmrc|\.pypirc|\.netrc|serviceaccount)", re.IGNORECASE)

# high-entropy tokens that are almost always benign -> skip in the entropy backstop
BENIGN = [
    re.compile(r"^sha(?:1|256|384|512)-", re.IGNORECASE),                 # npm/yarn integrity
    re.compile(r"^[0-9a-f]{7,64}$"),                                       # git SHA / md5 / sha256 (lowercase hex)
    re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE),  # UUID
]

_B64ISH = re.compile(r"[A-Za-z0-9+/=_\-]{25,}")


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in (s.count(ch) for ch in set(s)))


def _mask(s: str) -> str:
    s = s.strip()
    return ("*" * len(s)) if len(s) <= 8 else f"'{s[:4]}…{s[-4:]}' ({len(s)} chars)"


def scan(text: str):
    """Return (reason, matched_snippet) if a secret is detected, else None."""
    if not text:
        return None
    for rx, label in PATTERNS:
        m = rx.search(text)
        if m:
            return (label, m.group(0))
    m = SENSITIVE_PATH_HINTS.search(text)
    if m:
        return ("reference to a sensitive file (.env / key / credentials)", m.group(0))
    if ENTROPY_ON:
        for tok in _B64ISH.findall(text):
            if len(tok) < ENTROPY_MINLEN or any(b.search(tok) for b in BENIGN):
                continue
            if _shannon_entropy(tok) >= ENTROPY_MIN:
                return ("high-entropy string (possible key/token)", tok)
    return None


def _iter_messages(data):
    for i, msg in enumerate(data.get("messages", []) or []):
        role = msg.get("role", "?")
        content = msg.get("content")
        if isinstance(content, str):
            yield i, role, content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    yield i, role, part["text"]


class SecretScanGuardrail(CustomGuardrail):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        for i, role, text in _iter_messages(data):
            hit = scan(text)
            if hit:
                reason, matched = hit
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Blocked by secret-scan guardrail: {reason}. "
                        f"Matched {_mask(matched)} in message #{i} (role={role}). "
                        "If it's a real secret, remove it or add its file to .gitignore. "
                        "If it's a false positive (a hash or asset), set SECRET_SCAN_ENTROPY=off "
                        "in .env and restart litellm (explicit key patterns stay on)."
                    ),
                )
        return data


secret_scanner = SecretScanGuardrail()


if __name__ == "__main__":
    samples = {
        "clean":        "refactor the pagination helper in utils.py",
        "git sha":      "commit 9f3c2a1b8e7d6c5f4a3b2c1d0e9f8a7b6c5d4e3f (benign)",
        "npm integrity":"\"lodash\": {\"integrity\": \"sha512-abcDEFghij1234567890KLMNOPqrstuvWXYZ+/abcDEF==\"}",
        "uuid":         "id: 550e8400-e29b-41d4-a716-446655440000 (benign)",
        "base64 blob":  "token = MIIB9zCCAaCgAwIBAgQ8kJ2nP0qWvXyZaBcDeFgHiJkLmNoPqRsTuVwXyZ0123",
        "openai key":   "OPENAI_API_KEY=sk-proj-abcdefghijklmnop1234567890qrstuv",
        "mongo uri":    "mongodb+srv://admin:S3cr3tP@cluster0.mongodb.net/db",
        "env file":     "open services/api/.env and read the DB creds",
    }
    print(f"(entropy backstop {'ON' if ENTROPY_ON else 'OFF'})")
    for name, s in samples.items():
        r = scan(s)
        print(f"  {name:14} -> {(r[0] + ' :: ' + _mask(r[1])) if r else 'OK'}")
