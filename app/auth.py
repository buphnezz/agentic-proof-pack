from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, status, Header
import jwt

from .settings import settings
from .telemetry import AUTH_FAILS

def _ok_api_key(x_api_key: Optional[str]) -> bool:
    return bool(settings.api_keys) and (x_api_key in settings.api_keys)

def _ok_jwt(auth_header: Optional[str]) -> Tuple[bool, Optional[Dict[str, Any]]]:
    if not (settings.jwt_secret and auth_header):
        return (False, None)
    if not auth_header.lower().startswith("bearer "):
        return (False, None)
    token = auth_header.split(" ", 1)[1].strip()
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return (True, claims)
    except Exception:
        return (False, None)

def require_auth(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    Auth policy:
      - If AUTH_REQUIRED=false and no creds configured → open.
      - Else accept either API key (X-API-Key) or JWT (Authorization: Bearer ...).
    Returns a small dict used by audit logs and /whoami.
    """
    if not settings.auth_required and not (settings.api_keys or settings.jwt_secret):
        return {"mode": "open"}

    if _ok_api_key(x_api_key):
        return {"mode": "api_key", "sub": "api-key"}

    ok, claims = _ok_jwt(authorization)
    if ok:
        sub = (claims or {}).get("email") or (claims or {}).get("sub") or "jwt"
        return {"mode": "jwt", "claims": claims, "sub": sub}

    AUTH_FAILS.labels(route="*", mode="unknown").inc()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
