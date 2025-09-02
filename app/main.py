from fastapi import FastAPI, Request, Depends, UploadFile, File, HTTPException, status, Query
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import os, io, json, time, shutil, tempfile, datetime

from .models import AskRequest
from .orchestrator import handle_ask
from .audit import write_audit, tail_audit, new_trace_id, verify_audit_lines
from .telemetry import REQS, FAILS, LAT, GROUNDED
from .settings import settings
from .version import __version__
from .auth import require_auth
from .retrieval import rebuild_index

app = FastAPI(title="Agentic Proof Pack", version=__version__)

# --- CORS ---
allowed = (
    settings.allowed_origins
    if settings.allowed_origins
    else (["*"] if not settings.auth_required else [])
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static ---
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "public")
app.mount("/public", StaticFiles(directory=STATIC_DIR), name="public")

# --- Ephemeral KB (demo-safe) ---
# We use a TemporaryDirectory (deleted on process exit). We also seed it with
# small sample files from data/knowledge_base so the page shows docs on first load.
_EPHEMERAL_TD: tempfile.TemporaryDirectory | None = None

def _seed_demo_kb(dest_dir: str, src_dir: str):
    if not os.path.isdir(src_dir):
        return
    for fn in sorted(os.listdir(src_dir)):
        if not fn.lower().endswith((".md", ".txt", ".pdf", ".docx")):
            continue
        src = os.path.join(src_dir, fn)
        try:
            # avoid pulling huge PDFs by default in demo
            size_ok = os.stat(src).st_size <= settings.max_upload_bytes
            if not size_ok and not fn.lower().endswith((".md", ".txt")):
                continue
            shutil.copy2(src, os.path.join(dest_dir, fn))
        except Exception:
            # seeding is best-effort
            pass

def _ensure_kb_root():
    """
    On startup:
      * If EPHEMERAL_UPLOADS, point settings.kb_dir to a TemporaryDirectory.
      * Seed it with small sample docs so the list isn’t empty on first visit.
    """
    global _EPHEMERAL_TD
    if settings.demo_mode and settings.ephemeral_uploads:
        if _EPHEMERAL_TD is None:
            _EPHEMERAL_TD = tempfile.TemporaryDirectory(prefix="agentic_kb_")
            # re-point KB to the temp dir (safe: BaseModel is mutable)
            settings.kb_dir = _EPHEMERAL_TD.name
            os.makedirs(settings.kb_dir, exist_ok=True)
            _seed_demo_kb(settings.kb_dir, settings.seed_kb_dir)
    else:
        os.makedirs(settings.kb_dir, exist_ok=True)

@app.on_event("startup")
def _startup():
    _ensure_kb_root()
    # Build initial index so first request is snappy
    try:
        rebuild_index()
    except Exception:
        pass

# ---------- Basics ----------
@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)

@app.get("/health")
def health():
    return {"ok": True, "version": __version__, "demo": settings.demo_mode, "ephemeral": settings.ephemeral_uploads}

@app.get("/")
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/audit/ui")
def audit_ui():
    with open(os.path.join(STATIC_DIR, "audit.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/whoami")
def whoami(ctx=Depends(require_auth)):
    return {"auth": ctx}

# ---------- Q&A ----------
@app.post("/ask")
def ask(req: AskRequest, request: Request, ctx=Depends(require_auth)):
    route = "/ask"
    REQS.labels(route=route).inc()
    trace = new_trace_id()
    with LAT.labels(route=route).time():
        try:
            resp = handle_ask(req)
            GROUNDED.labels(route=route).set(resp.metrics.grounded_ratio)
            write_audit(
                {
                    "trace_id": trace,
                    "auth": ctx,
                    "client": request.client.host if request.client else None,
                    "request": req.model_dump(),
                    "response": json.loads(resp.model_dump_json()),
                }
            )
            return JSONResponse(resp.model_dump())
        except Exception as e:
            FAILS.labels(route=route, reason="exception").inc()
            write_audit({"trace_id": trace, "error": str(e), "request": req.model_dump()})
            return JSONResponse(
                {"error": "internal_error", "trace_id": trace}, status_code=500
            )

# ---------- KB APIs ----------
@app.get("/kb/list")
def kb_list(ctx=Depends(require_auth)):
    out = []
    if os.path.isdir(settings.kb_dir):
        for fn in sorted(os.listdir(settings.kb_dir)):
            if not fn.lower().endswith((".md", ".txt", ".pdf", ".docx")):
                continue
            path = os.path.join(settings.kb_dir, fn)
            try:
                st = os.stat(path)
                out.append({
                    "doc_id": fn,
                    "bytes": st.st_size,
                    "mtime": int(st.st_mtime),
                    "mtime_iso": datetime.datetime.utcfromtimestamp(st.st_mtime).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
            except OSError:
                pass
    return {"count": len(out), "docs": out}

@app.post("/kb/reindex")
def kb_reindex(ctx=Depends(require_auth)):
    t0 = time.time()
    idx = rebuild_index()
    return {"ok": True, "chunks": len(idx.chunks), "ms": int((time.time() - t0) * 1000)}

@app.get("/kb/raw")
def kb_raw(
    doc_id: str = Query(..., description="filename within KB_DIR"),
    start: int = Query(0, ge=0),
    end: int = Query(200, ge=0),
    ctx=Depends(require_auth),
):
    path = os.path.join(settings.kb_dir, os.path.basename(doc_id))
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="doc not found")
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext in (".md", ".txt"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.read().splitlines()
        else:
            from .retrieval import read_doc_lines
            lines = read_doc_lines(path)
        s = max(0, start); e = max(s, end)
        snippet = "\n".join(lines[s:e+1])
        return PlainTextResponse(snippet or "(empty)")
    except Exception:
        raise HTTPException(status_code=500, detail="read_error")

@app.post("/kb/upload")
async def kb_upload(file: UploadFile = File(...), ctx=Depends(require_auth)):
    """
    In demo+ephemeral mode:
      - persist into a TemporaryDirectory (deleted when server exits)
    Otherwise:
      - write into settings.kb_dir as usual
    """
    name = os.path.basename(file.filename or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing filename")
    ext = os.path.splitext(name)[1].lower()
    allowed = set(x.strip().lower() for x in (settings.allowed_upload_exts or [".md", ".txt"]))
    if ext not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ext {ext} not allowed")

    # pick destination root (ephemeral temp dir when enabled)
    dest_root = settings.kb_dir
    os.makedirs(dest_root, exist_ok=True)

    # stream to disk with a size guard
    maxb = settings.max_upload_bytes
    total = 0
    dst_path = os.path.join(dest_root, name.replace(" ", "_"))
    try:
        with open(dst_path, "wb") as out:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > maxb:
                    try: os.remove(dst_path)
                    except Exception: pass
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                        detail=f"file too large (> {maxb} bytes)")
                out.write(chunk)
    finally:
        await file.close()

    idx = rebuild_index()
    return {"ok": True, "doc_id": os.path.basename(dst_path), "bytes": total, "indexed_chunks": len(idx.chunks),
            "ephemeral": bool(_EPHEMERAL_TD is not None)}

@app.delete("/kb/{doc_id}")
def kb_delete(doc_id: str, ctx=Depends(require_auth)):
    path = os.path.join(settings.kb_dir, os.path.basename(doc_id))
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="doc not found")
    try:
        os.remove(path)
    except Exception:
        raise HTTPException(status_code=500, detail="delete_failed")
    idx = rebuild_index()
    return {"ok": True, "remaining_chunks": len(idx.chunks)}

# ---------- Audit & Metrics ----------
@app.get("/audit/logs")
def logs(n: int = 50, ctx=Depends(require_auth)):
    return PlainTextResponse(tail_audit(n) or "no logs yet")

@app.get("/audit/verify")
def audit_verify(n: int = 50, ctx=Depends(require_auth)):
    res = verify_audit_lines((tail_audit(n) or "").splitlines())
    return JSONResponse({"checked": len(res), "results": res})

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
