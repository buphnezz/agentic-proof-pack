# agentic-proof-pack/app/guardrails.py
from __future__ import annotations
import re

# --- PII scrubbing (stdlib-only, fast, safe) ---
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC  = re.compile(r"\b(?:\d[ -]?){13,16}\b")

def scrub_pii(text: str) -> str:
    if not text:
        return text
    # order matters a bit (emails before generic digit runs)
    text = _EMAIL.sub("[REDACTED EMAIL]", text)
    text = _PHONE.sub("[REDACTED PHONE]", text)
    text = _SSN.sub("[REDACTED SSN]", text)
    text = _CC.sub("[REDACTED CARD]", text)
    return text

# --- simple jailbreak detector ---
_INJECTION = re.compile(
    r"(?:ignore\s+previous|disregard\s+all\s+prior|system\s*prompt|"
    r"jailbreak|do\s+anything\s+now|pretend|override|act\s+as\s+if)",
    re.IGNORECASE,
)

def detect_injection(text: str) -> bool:
    if not text:
        return False
    return bool(_INJECTION.search(text))
