"""
Fail-closed secret-scan guardrail for the LiteLLM gateway.

Inspects every outgoing prompt and BLOCKS the request if it looks like a secret
is about to leave your machine. Covers private keys, cloud provider keys, and
tokens from a wide range of service providers (small to major), connection
strings with embedded credentials, and a high-entropy backstop.

Registration (config/litellm.yaml):
    guardrails:
      - guardrail_name: "secret-scan"
        litellm_params:
          guardrail: guardrails.secret_scan.SecretScanGuardrail
          mode: "pre_call"
          default_on: true
Callback-style alternative (litellm_settings):
    callbacks: ["guardrails.secret_scan.secret_scanner"]

Standard library only. Tune ENTROPY_MIN / ENTROPY_MINLEN below if the entropy
backstop is too aggressive on your codebase (fail-closed => occasional false
positives are expected; the explicit patterns carry most of the load).
"""

import math
import re

try:
    from litellm.integrations.custom_guardrail import CustomGuardrail
    from fastapi import HTTPException
except Exception:  # keep importable for local unit testing
    class CustomGuardrail:  # type: ignore
        def __init__(self, *a, **k): ...
    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code=400, detail=""):
            super().__init__(detail); self.status_code, self.detail = status_code, detail

ENTROPY_MIN = 4.3      # bits/char; higher = fewer false positives
ENTROPY_MINLEN = 40    # only entropy-check tokens at least this long

# ---- explicit, high-signal patterns (regex, human label) -------------------
PATTERNS = [
    # --- private keys / certs ---
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY(?: BLOCK)?-----"), "private key block"),
    (re.compile(r"\bPuTTY-User-Key-File-\d"), "PuTTY private key"),

    # --- cloud: AWS / GCP / Azure ---
    (re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|A3T[A-Z0-9])[A-Z0-9]{16}\b"), "AWS access key id"),
    (re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+]{40}"), "AWS secret access key"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "Google API key"),
    (re.compile(r"\bya29\.[0-9A-Za-z_\-]+"), "Google OAuth access token"),
    (re.compile(r"\b1//[0-9A-Za-z_\-]{20,}"), "Google OAuth refresh token"),
    (re.compile(r'"type"\s*:\s*"service_account"'), "GCP service-account JSON"),
    (re.compile(r"(?i)AccountKey=[A-Za-z0-9+/=]{80,}"), "Azure storage account key"),
    (re.compile(r"\bSharedAccessKey=[A-Za-z0-9+/=]{20,}"), "Azure SAS key"),

    # --- AI / LLM providers ---
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), "Anthropic API key"),
    (re.compile(r"\bsk-(?:proj|svcacct|admin)?-?[A-Za-z0-9_\-]{20,}"), "OpenAI API key"),
    (re.compile(r"\bsk-or-v1-[a-f0-9]{40,}"), "OpenRouter key"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), "Groq key"),
    (re.compile(r"\bhf_[A-Za-z0-9]{30,}"), "Hugging Face token"),
    (re.compile(r"\br8_[A-Za-z0-9]{35,}"), "Replicate token"),
    (re.compile(r"\bpplx-[A-Za-z0-9]{40,}"), "Perplexity key"),
    (re.compile(r"\bxai-[A-Za-z0-9]{60,}"), "xAI (Grok) key"),
    (re.compile(r"\bdapi[a-f0-9]{32,}"), "Databricks token"),

    # --- source hosts ---
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}"), "GitHub fine-grained PAT"),
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"), "GitLab PAT"),
    (re.compile(r"\bglptt-[A-Za-z0-9_\-]{20,}"), "GitLab trigger token"),

    # --- messaging / comms ---
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"\bxapp-\d-[A-Z0-9]+-\d+-[a-f0-9]+"), "Slack app token"),
    (re.compile(r"https://hooks\.slack\.com/services/T[A-Za-z0-9_]+/B[A-Za-z0-9_]+/[A-Za-z0-9]+"), "Slack webhook"),
    (re.compile(r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{40,}"), "SendGrid key"),
    (re.compile(r"\bkey-[a-f0-9]{32}\b"), "Mailgun key"),
    (re.compile(r"\b[MNO][A-Za-z0-9_\-]{23}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,}"), "Discord bot token"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b"), "Telegram bot token"),
    (re.compile(r"\bAC[a-f0-9]{32}\b"), "Twilio account SID"),
    (re.compile(r"\bSK[a-f0-9]{32}\b"), "Twilio API key SID"),

    # --- payments / commerce ---
    (re.compile(r"\b[rs]k_live_[A-Za-z0-9]{20,}"), "Stripe live secret key"),
    (re.compile(r"\bsk_test_[A-Za-z0-9]{20,}"), "Stripe test secret key"),
    (re.compile(r"\bwhsec_[A-Za-z0-9]{20,}"), "Stripe webhook secret"),
    (re.compile(r"\bshp(?:at|ca|pa|ss)_[a-fA-F0-9]{32}"), "Shopify token"),
    (re.compile(r"\bsq0(?:atp|csp)-[A-Za-z0-9_\-]{22,}"), "Square token"),
    (re.compile(r"\bEAAA[A-Za-z0-9_\-]{60,}"), "Square/Facebook access token"),

    # --- infra / package registries ---
    (re.compile(r"\bdo[oprt]_v1_[a-f0-9]{64}"), "DigitalOcean token"),
    (re.compile(r"\bnpm_[A-Za-z0-9]{36}"), "npm token"),
    (re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{50,}"), "PyPI token"),
    (re.compile(r"\bAAAA[A-Za-z0-9_\-]{7}:[A-Za-z0-9_\-]{140,}"), "Firebase/FCM server key"),
    (re.compile(r"\bntn_[A-Za-z0-9]{40,}"), "Notion token"),
    (re.compile(r"\bsecret_[A-Za-z0-9]{43}\b"), "Notion legacy token"),

    # --- generic / structural ---
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "JWT"),
    (re.compile(r"(?i)\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|mariadb|redis|rediss|amqps?)://[^\s:@/]+:[^\s@/]+@"), "DB/URI with embedded credentials"),
    (re.compile(r"(?i)\bhttps?://[^\s:@/]+:[^\s@/]+@[^\s/]+"), "URL with basic-auth credentials"),
    (re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]{20,}"), "Bearer authorization header"),
    (re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|passwd|password|private[_-]?key)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-\.]{12,}"), "inline credential assignment"),
]

SENSITIVE_PATH_HINTS = re.compile(
    r"(?:^|[\\/])(?:\.env(?:\.[\w-]+)?|id_(?:rsa|ed25519|ecdsa|dsa)|\.pem|\.p12|\.pfx|"
    r"\.key|credentials?|\.aws[\\/]|\.ssh[\\/]|\.config[\\/]gcloud[\\/]|secrets?[\\/]|"
    r"kubeconfig|\.npmrc|\.pypirc|\.netrc|serviceaccount)",
    re.IGNORECASE,
)

_B64ISH = re.compile(r"[A-Za-z0-9+/=_\-]{25,}")


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in (s.count(ch) for ch in set(s)))


def scan(text: str):
    """Return a reason string if a secret is detected, else None."""
    if not text:
        return None
    for rx, label in PATTERNS:
        if rx.search(text):
            return label
    if SENSITIVE_PATH_HINTS.search(text):
        return "reference to a sensitive file (.env / key / credentials)"
    for tok in _B64ISH.findall(text):
        if len(tok) >= ENTROPY_MINLEN and _shannon_entropy(tok) >= ENTROPY_MIN:
            return "high-entropy string (possible key/token)"
    return None


def _iter_message_text(data):
    for msg in data.get("messages", []) or []:
        content = msg.get("content")
        if isinstance(content, str):
            yield content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    yield part["text"]


class SecretScanGuardrail(CustomGuardrail):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        for text in _iter_message_text(data):
            reason = scan(text)
            if reason:
                raise HTTPException(
                    status_code=400,
                    detail=(f"Blocked by secret-scan guardrail: {reason}. A possible secret was "
                            "about to be sent to a model provider. Remove it (or .gitignore the "
                            "file) and retry."),
                )
        return data


secret_scanner = SecretScanGuardrail()


if __name__ == "__main__":
    samples = {
        "clean code":  "refactor the pagination helper in utils.py to use a cursor",
        "openai":      "OPENAI_API_KEY=sk-proj-abcdefghijklmnop1234567890qrstuv",
        "anthropic":   "sk-ant-api03-AbCdEf012345678901234567890123456789",
        "aws id":      "AKIAIOSFODNN7EXAMPLE",
        "aws secret":  'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"',
        "stripe":      "sk_live_51H0abcdEFGHijklMNOPqrstUVWX",
        "github":      "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "slack":       "xoxb-123456789012-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx",
        "jwt":         "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcDEF123456",
        "mongo uri":   "mongodb+srv://admin:S3cr3tP@cluster0.mongodb.net/db",
        "basic auth":  "curl https://user:hunter2@internal.example.com/api",
        "env file":    "open services/api/.env and read the DB creds",
        "google key":  "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7",
    }
    for name, s in samples.items():
        print(f"{name:12} -> {scan(s) or 'OK'}")
