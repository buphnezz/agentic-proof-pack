from typing import List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

def _split_csv(v: Optional[str]) -> List[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]

def _truthy(v: Optional[str], default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")

def _int(v: Optional[str], default: int) -> int:
    try:
        return int(v) if v is not None else default
    except Exception:
        return default

# allow demo-driven defaults before Settings initialization
_DEMO = _truthy(os.getenv("DEMO_MODE"), True)

class Settings(BaseModel):
    # App
    app_port: int = _int(os.getenv("APP_PORT"), 8000)

    # KB / Storage
    kb_dir: str = os.getenv("KB_DIR", "./data/knowledge_base")
    seed_kb_dir: str = os.getenv("SEED_KB_DIR", "./data/knowledge_base")

    # Audit (signed logs + rotation)
    audit_path: str = os.getenv("AUDIT_PATH", "./data/audit/audit.jsonl")
    audit_signing_key: str = os.getenv("AUDIT_SIGNING_KEY", "dev-signing-key")
    audit_prev_keys: List[str] = _split_csv(os.getenv("AUDIT_PREV_KEYS"))

    # Auth / RBAC
    api_keys: List[str] = _split_csv(os.getenv("API_KEYS"))
    jwt_secret: Optional[str] = os.getenv("JWT_SECRET")
    auth_required: bool = _truthy(os.getenv("AUTH_REQUIRED"), False)

    # CORS
    allowed_origins: List[str] = _split_csv(os.getenv("ALLOWED_ORIGINS"))

    # Retrieval / ranking
    faiss_enabled: bool = _truthy(os.getenv("FAISS_ENABLED"), True)
    svd_components: int = _int(os.getenv("SVD_COMPONENTS"), 256)
    # Optional HF CrossEncoder id
    sencoder_model: Optional[str] = os.getenv("SENCODER_MODEL")

    # Composition / defaults
    max_context_chars: int = _int(os.getenv("MAX_CONTEXT_CHARS"), 3000)
    default_top_k: int = _int(os.getenv("DEFAULT_TOP_K"), 3)

    # Demo / uploads / rate limiting
    demo_mode: bool = _DEMO
    ephemeral_uploads: bool = _truthy(os.getenv("EPHEMERAL_UPLOADS"), True if _DEMO else False)
    max_upload_bytes: int = _int(os.getenv("MAX_UPLOAD_BYTES"), 1_000_000 if _DEMO else 5_000_000)
    allowed_upload_exts: List[str] = _split_csv(os.getenv("ALLOWED_UPLOAD_EXTS") or ".md,.txt,.pdf,.docx")
    rate_limit_window_sec: int = _int(os.getenv("RATE_LIMIT_WINDOW_SEC"), 300)
    rate_limit_max_reqs: int = _int(os.getenv("RATE_LIMIT_MAX_REQS"), 60 if _DEMO else 300)

settings = Settings()
