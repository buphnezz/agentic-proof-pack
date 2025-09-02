# Agentic Proof Pack

Deterministic, auditable **RAG (without the “G”)** demo: schema-locked I/O, inline citations, signed audit logs, metrics, RBAC, and ephemeral uploads for safe trials.

> **TL;DR**  
> Upload a doc, ask a question, get an answer stitched **only** from cited snippets (doc id + line ranges).  
> Everything is auditable and verifiable. No external LLM/API required.

---

## Why this matters

- **Determinism & auditability** – Every `/ask` writes a **signed JSONL** line. `/audit/ui` verifies signatures.  
- **Grounded outputs** – Answers are composed strictly from retrieved snippets with **doc + line ranges**.  
- **Governance & safety** – PII scrub + basic injection detection; explicit `insufficient_context` fallback.  
- **Zero data risk in demos** – **Ephemeral uploads** (demo mode) live in a temp store and are cleared on restart.  
- **Operational-ready** – Prometheus metrics, API-first design, simple RBAC (API key/JWT), and a Helm chart.

---

## Features

- 📄 **Ingestion:** `.pdf`, `.docx`, `.md`, `.txt`
- 🔎 **Retrieval:** TF-IDF + **BM25** (rank-bm25) + optional **FAISS** recall  
  (reranked by TF-IDF cosine; optional HF CrossEncoder if configured)
- 🧷 **Citations:** doc id + start/end line ranges (always returned)
- 🧹 **Guardrails:** PII scrub, injection detection, `insufficient_context` fallback
- 🧾 **Signed audit log:** verify via `/audit/ui` or `/audit/verify`
- 📈 **Metrics:** Prometheus histograms + gauges at `/metrics`
- 🔐 **RBAC:** API key or JWT; demo uses `demo-key`
- ☁️ **Ephemeral uploads:** in demo mode, files don’t persist after restart
- 🧰 **Postman** collection & environment included (`/clients`)

---

## Quick start

### Prereqs
- Python **3.9+**
- `pip`, `venv`

### Setup
```bash
git clone https://github.com/buphnezz/agentic-proof-pack.git
cd agentic-proof-pack

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy env and keep defaults (demo mode is on by default)
cp .env.example .env
# Ensure a demo API key
echo "API_KEYS=demo-key" >> .env

# Run
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
````

### In the UI

1. **Enter API Key:** `demo-key`
2. (Optional) **Upload** `.pdf` / `.docx` / `.md` / `.txt`
   *In demo mode, uploads are **ephemeral** and cleared on restart.*
3. **Ask a question** → see **Answer**, **Citations**, **Metrics**
4. Click **Audit UI** (top card or footer) → verify **signed logs**

> **Note on footer links** (`/audit/logs`, `/audit/verify`): those require the `X-API-Key` header and will 401 if opened directly. Use **Audit UI** for a friendly, prefilled experience.

---

## How the shared demo link was created (FYI only)

You may receive a public URL that points to this app running on my machine.
That link was generated with **Cloudflared quick tunnels**. Reviewers **don’t need** to do anything to use the app.

* It’s a best-effort link intended for short demos (typically 24–72 hours).
* Protected endpoints (like `/audit/verify`) expect `X-API-Key: demo-key`.
  The UI includes an API Key field and the Audit UI prefills `demo-key`.

If the link ever goes dormant, I’ll refresh it.

---

## API Cheatsheet

> All auth-required routes expect header: `X-API-Key: demo-key`
> (JWT is supported too; API key is simplest for demos.)

* `GET /` → demo UI
* `GET /health` → ping
* `GET /whoami` → shows auth context (requires auth)
* `POST /ask` → body: `{"question":"...", "top_k":3}`
* `GET /kb/list` → list KB docs (requires auth)
* `POST /kb/upload` → multipart file upload (requires auth)
* `POST /kb/reindex` → rebuild hybrid index (requires auth)
* `GET /kb/raw?doc_id=...&start=0&end=120` → peek raw lines (requires auth)
* `DELETE /kb/delete?doc_id=...` → delete a doc (requires auth)
* `GET /audit/ui` → HTML verifier (requires auth)
* `GET /audit/logs` → last N audit lines (requires auth)
* `GET /audit/verify?n=100` → JSON signature check (requires auth)
* `GET /metrics` → Prometheus metrics (no auth)

### Curl examples

```bash
# whoami
curl -H "X-API-Key: demo-key" http://127.0.0.1:8000/whoami

# ask
curl -H "Content-Type: application/json" -H "X-API-Key: demo-key" \
  -d '{"question":"What are the acceptance tests for the pilot?","top_k":3}' \
  http://127.0.0.1:8000/ask

# upload
curl -H "X-API-Key: demo-key" -F "file=@/path/to/file.pdf" \
  http://127.0.0.1:8000/kb/upload

# delete
curl -X DELETE -H "X-API-Key: demo-key" \
  "http://127.0.0.1:8000/kb/delete?doc_id=compliance.md"
```

---

## Configuration (`.env`)

Common toggles (safe defaults provided):

```ini
# --- App / Auth ---
APP_PORT=8000
API_KEYS=demo-key
AUTH_REQUIRED=true
JWT_SECRET=

# --- Demo / Uploads / Rate Limits ---
DEMO_MODE=true                 # ephemeral uploads in temp store
MAX_UPLOAD_BYTES=1000000
ALLOWED_UPLOAD_EXTS=.md,.txt,.pdf,.docx
RATE_LIMIT_WINDOW_SEC=300
RATE_LIMIT_MAX_REQS=60

# --- Retrieval / Ranking ---
FAISS_ENABLED=true
SVD_COMPONENTS=256
BM25_ENABLED=true
SENCODER_MODEL=

# --- Composition defaults ---
MAX_CONTEXT_CHARS=3000
DEFAULT_TOP_K=3

# --- Audit ---
AUDIT_PATH=./data/audit/audit.jsonl
AUDIT_SIGNING_KEY=dev-signing-key
AUDIT_PREV_KEYS=
```

*To switch to persisted KB, set `DEMO_MODE=false` and ensure `KB_DIR` (default `./data/knowledge_base`) is writable.*

---

## Architecture

```
app/
  main.py         # FastAPI routes (UI, KB mgmt, audit, metrics)
  orchestrator.py # guardrails + retrieval + deterministic compose
  retrieval.py    # TF-IDF + BM25 + optional FAISS + reranker
  faiss_index.py  # SVD-reduced TF-IDF vectors → FAISS ANN (optional)
  reranker.py     # TF-IDF cosine or optional HF CrossEncoder
  audit.py        # signed JSONL + verification
  telemetry.py    # Prometheus metrics
  auth.py         # API key / JWT
  settings.py     # typed settings from env
public/
  index.html, app.js, styles.css, audit.html
data/
  knowledge_base/ # starter docs (when not in demo mode)
  audit/          # signed logs (for verification)
clients/
  postman/        # collection + environment
deploy/helm/      # k8s chart (optional)
```

**Retrieval pipeline:**
Query → TF-IDF ∪ BM25 ∪ (optional) FAISS → rerank → **deterministic** stitched answer (clamped by `MAX_CONTEXT_CHARS`) + citations.

---

## Starter prompts (optional)

* “What are the acceptance tests for the pilot?”
* “Summarize the five focusing steps.”
* “Define a constraint in this document’s terms.”
* “What benefits does the document claim for this approach?”
* “Show citations for your answer.”

---

## Security & privacy

* **No external LLM/API** calls.
* **Ephemeral uploads** in demo mode (cleared on restart).
* **Signed audit logs** for every `/ask` (verify via `/audit/ui`).
* **RBAC & CORS** configurable; demo uses `demo-key`.

---

## License

This repository is provided for interview/demo purposes.
© 2025 Zachary Schumpert. All rights reserved.