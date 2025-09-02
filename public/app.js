// ---------- helpers ----------
const $ = (id) => document.getElementById(id);
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

function hdrsJSON() {
  const key = $("apiKey").value || localStorage.apiKey || "";
  const h = { "Content-Type": "application/json" };
  if (key) h["X-API-Key"] = key;
  return h;
}
function hdrs() {
  const key = $("apiKey").value || localStorage.apiKey || "";
  return key ? { "X-API-Key": key } : {};
}

function flashKey(msg) {
  const keyEl = $("apiKey");
  const status = $("status");
  status.textContent = msg;
  keyEl.classList.add("input-error");
  setTimeout(() => {
    keyEl.classList.remove("input-error");
    status.textContent = "";
  }, 1400);
}

function showResult(j) {
  $("answer").textContent  = j.answer || "(no answer)";
  $("cites").textContent   = JSON.stringify(j.citations || [], null, 2);
  const m = j.metrics || {};
  $("metrics").textContent =
    JSON.stringify(m, null, 2) +
    (j.insufficient_context ? "\n[insufficient_context=true]" : "");

  // clickable citations
  const list = $("citesList");
  list.innerHTML = "";
  (j.citations || []).forEach((c, idx) => {
    const a = document.createElement("a");
    a.href = "#";
    a.textContent = `${idx + 1}. ${c.doc_id} [${c.start_line}-${c.end_line}]`;
    a.onclick = async (e) => { e.preventDefault(); await peekCitation(c.doc_id, c.start_line, c.end_line); };
    const div = document.createElement("div");
    div.appendChild(a);
    list.appendChild(div);
  });
}

// ---------- init ----------
function init() {
  const keyEl = $("apiKey");
  const kEl   = $("k");
  keyEl.value = localStorage.apiKey || keyEl.value || "demo-key";
  kEl.value   = localStorage.topK   || kEl.value   || "3";
  keyEl.addEventListener("input", () => { localStorage.apiKey = keyEl.value; });
  kEl.addEventListener("input",   () => { localStorage.topK   = kEl.value; });

  $("q").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); send(); }
  });

  // banner info
  fetch("/health").then(r => r.json()).then(j => {
    const b = $("demoBanner"); if (b) b.style.display = "block";
    const note = $("ephemeralNote"); if (note) note.style.display = j.ephemeral ? "inline-flex" : "none";
  }).catch(()=>{});

  listDocs();
}
window.addEventListener("DOMContentLoaded", init);

// ---------- /ask ----------
let inflight = null;

async function send() {
  const q   = $("q").value;
  const k   = clamp(parseInt(($("k").value || "3"), 10) || 3, 1, 8);
  const key = ($("apiKey").value || localStorage.apiKey || "").trim();

  if (!key) { flashKey('Add API key (try "demo-key") and press Ask.'); return; }
  if (inflight) inflight.abort();
  inflight = new AbortController();

  const btn = $("btn");
  const status = $("status");
  btn.disabled = true;
  btn.setAttribute("aria-busy", "true");
  status.textContent = "…thinking";

  try {
    const r = await fetch("/ask", {
      method: "POST",
      headers: hdrsJSON(),
      body: JSON.stringify({ question: q, top_k: k }),
      signal: inflight.signal,
    });

    if (r.status === 401) {
      flashKey('Unauthorized. Add a valid API key (try "demo-key").');
      showResult({ answer: "", citations: [], metrics: {} });
      return;
    }

    let j = {};
    try { j = await r.json(); } catch {}
    if (!r.ok || (j && j.error)) {
      const trace = j && j.trace_id ? ` (trace ${j.trace_id})` : "";
      $("answer").textContent = `Server error ${r.status}${trace}`;
      $("cites").textContent = "[]";
      $("metrics").textContent = "{}";
      return;
    }

    if (j.insufficient_context) {
      $("answer").textContent = "Not enough supporting context in the KB to answer safely.";
    }
    showResult(j);
  } catch (e) {
    if (e.name !== "AbortError") {
      $("answer").textContent = "Network error: " + (e?.message || e);
      $("cites").textContent = "[]";
      $("metrics").textContent = "{}";
    }
  } finally {
    btn.disabled = false;
    btn.removeAttribute("aria-busy");
    status.textContent = "";
    inflight = null;
  }
}

// ---------- whoami ----------
async function whoami(){
  const out = $("whoamiOut");
  out.textContent = "…";
  try{
    const r = await fetch("/whoami", { headers: hdrs() });
    if (r.status === 401) { out.textContent = "401 (need API key)"; return; }
    const j = await r.json();
    out.textContent = JSON.stringify(j.auth || j, null, 0);
  }catch(e){
    out.textContent = "error";
  }
}

// ---------- uploads / kb mgmt ----------
async function uploadDoc(){
  const kb = $("kbFile");
  const st = $("kbStatus");
  if (!kb.files || kb.files.length === 0) { st.textContent = "pick a file"; return; }
  st.textContent = "uploading…";
  const fd = new FormData();
  fd.append("file", kb.files[0]);
  try{
    const r = await fetch("/kb/upload", { method:"POST", headers: hdrs(), body: fd });
    if (r.status === 401) { st.textContent = "401 (need API key)"; return; }
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || "upload failed");
    st.textContent = `ok: ${j.doc_id} (${j.bytes} bytes), chunks=${j.indexed_chunks}`;
    await listDocs();
  }catch(e){
    st.textContent = "error: " + (e.message || e);
  }
}

async function reindex(){
  const st = $("kbStatus");
  st.textContent = "reindexing…";
  try{
    const r = await fetch("/kb/reindex", { method:"POST", headers: hdrsJSON() });
    if (r.status === 401) { st.textContent = "401 (need API key)"; return; }
    const j = await r.json();
    st.textContent = `ok: ${j.chunks} chunks in ${j.ms} ms`;
    await listDocs();
  }catch(e){
    st.textContent = "error: " + (e.message || e);
  }
}

async function listDocs(){
  const container = $("kbListContainer");
  container.innerHTML = '<div class="muted">loading…</div>';
  try{
    const r = await fetch("/kb/list", { headers: hdrs() });
    if (r.status === 401) { container.textContent = "401 (need API key)"; return; }
    const j = await r.json();

    if (!j.docs || j.docs.length === 0) {
      container.innerHTML = '<div class="muted">No documents yet. Upload a .md/.txt/.pdf/.docx to try it.</div>';
      return;
    }

    const list = document.createElement("div");
    list.className = "docList";

    j.docs.forEach(d => {
      const row = document.createElement("div");
      row.className = "docRow";

      const left = document.createElement("div");
      left.className = "docLeft";
      left.textContent = `${d.doc_id} • ${d.bytes} bytes • ${d.mtime_iso}`;

      const right = document.createElement("div");
      right.className = "docRight";
      const btn = document.createElement("button");
      btn.className = "danger";
      btn.textContent = "delete";
      btn.onclick = async () => { await deleteDoc(d.doc_id); };
      right.appendChild(btn);

      row.appendChild(left);
      row.appendChild(right);
      list.appendChild(row);
    });

    container.innerHTML = "";
    container.appendChild(list);
  }catch(e){
    container.textContent = "error: " + (e.message || e);
  }
}

async function deleteDoc(doc_id){
  const ok = confirm(`Delete ${doc_id}?`);
  if (!ok) return;
  const container = $("kbListContainer");
  try{
    const r = await fetch(`/kb/${encodeURIComponent(doc_id)}`, { method:"DELETE", headers: hdrs() });
    const j = await r.json().catch(()=>({}));
    if (!r.ok) throw new Error(j.detail || "delete failed");
    await listDocs();
  }catch(e){
    container.insertAdjacentHTML("afterbegin", `<div class="notice bad">delete failed: ${e.message || e}</div>`);
    setTimeout(() => {
      const n = container.querySelector(".notice.bad"); if (n) n.remove();
    }, 2000);
  }
}

// ---------- citation peek ----------
async function peekCitation(doc_id, start, end){
  const view = $("citeView");
  view.textContent = "loading…";
  const params = new URLSearchParams({ doc_id: doc_id, start: String(start), end: String(end) });
  try{
    const r = await fetch("/kb/raw?" + params.toString(), { headers: hdrs() });
    if (r.status === 401) { view.textContent = "401 (need API key)"; return; }
    const txt = await r.text();
    view.textContent = txt;
  }catch(e){
    view.textContent = "error";
  }
}

// expose
window.send = send;
window.whoami = whoami;
window.uploadDoc = uploadDoc;
window.reindex = reindex;
window.listDocs = listDocs;
window.peekCitation = peekCitation;
window.deleteDoc = deleteDoc;
