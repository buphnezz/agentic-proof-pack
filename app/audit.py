import json, os, time, uuid, hmac, hashlib
from typing import Iterable
from .settings import settings

os.makedirs(os.path.dirname(settings.audit_path), exist_ok=True)

def new_trace_id() -> str:
    return uuid.uuid4().hex

def _canonical(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)

def _sign(payload: dict, key: str) -> str:
    msg = _canonical(payload).encode()
    return hmac.new(key.encode(), msg, hashlib.sha256).hexdigest()

def write_audit(entry: dict) -> None:
    """Append signed audit line: {"ts":..., "entry":{...}, "sig":"..."}"""
    payload = {"ts": round(time.time(), 3), "entry": entry}
    sig = _sign(payload, settings.audit_signing_key)
    out = {"ts": payload["ts"], "entry": entry, "sig": sig}
    with open(settings.audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(out) + "\n")

def tail_audit(n: int = 50) -> str:
    if not os.path.exists(settings.audit_path):
        return ""
    with open(settings.audit_path, "r", encoding="utf-8") as f:
        lines = f.readlines()[-n:]
    return "".join(lines)

def verify_audit_lines(lines: Iterable[str]) -> list[dict]:
    """Verify signatures; accepts current key or any in AUDIT_PREV_KEYS (rotation)."""
    keys = [settings.audit_signing_key] + list(settings.audit_prev_keys)
    results = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
            sig = obj.get("sig", "")
            payload = {"ts": obj.get("ts"), "entry": obj.get("entry")}
            ok = any(_sign(payload, k) == sig for k in keys)
            results.append({"ok": ok, "ts": obj.get("ts"), "trace_id": obj.get("entry", {}).get("trace_id")})
        except Exception:
            results.append({"ok": False, "error": "parse_error"})
    return results
