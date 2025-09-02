import os, re
from dataclasses import dataclass
from typing import List, Tuple, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .settings import settings
from .faiss_index import FaissIndex
from .reranker import build_reranker

# ---------- optional deps ----------
try:
    from rank_bm25 import BM25Okapi
except Exception:
    BM25Okapi = None

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None

# Optional readers for PDF/DOCX
try:
    import PyPDF2
except Exception:
    PyPDF2 = None
try:
    import docx  # python-docx
except Exception:
    docx = None

_token_re = re.compile(r"[A-Za-z0-9_]+")

def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _token_re.findall(text or "")]

def _is_noise_line(ln: str) -> bool:
    s = (ln or "").strip()
    if not s:
        return True
    if re.match(r"^(?:https?://|www\.)", s):   # pure urls
        return True
    # repeated boilerplate often seen in PDFs
    if "Learn About Vorne XL" in s:
        return True
    # lines with mostly non-letters (page headers/footers)
    letters = sum(ch.isalpha() for ch in s)
    return (letters / max(1, len(s))) < 0.25

@dataclass
class Chunk:
    """A token-aware(ish) text window with document + line offsets."""
    doc_id: str
    start_line: int
    end_line: int
    text: str

def read_doc_lines(path: str) -> List[str]:
    """Return a list of logical 'lines' for supported file types."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".md", ".txt"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read().splitlines()
                return [ln for ln in raw if not _is_noise_line(ln)]

        if ext == ".pdf" and PyPDF2 is not None:
            out: List[str] = []
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for pg in reader.pages:
                    txt = pg.extract_text() or ""
                    for ln in txt.replace("\r", "\n").split("\n"):
                        ln = (ln or "").strip()
                        if ln and not _is_noise_line(ln):
                            out.append(ln)
            return out

        if ext == ".docx" and docx is not None:
            out: List[str] = []
            d = docx.Document(path)
            for p in d.paragraphs:
                t = (p.text or "").strip()
                if t and not _is_noise_line(t):
                    out.append(t)
            return out
    except Exception:
        pass
    return []

def iter_docs(kb_dir: str):
    """Yield (doc_id, lines[]) for supported files in the KB dir."""
    if not os.path.isdir(kb_dir):
        return
    for fn in os.listdir(kb_dir):
        if not fn.lower().endswith((".md", ".txt", ".pdf", ".docx")):
            continue
        path = os.path.join(kb_dir, fn)
        lines = read_doc_lines(path)
        if lines:
            yield fn, lines

def make_chunks(lines: List[str], window: int = 4, stride: int = 3) -> List[Tuple[int, int, str]]:
    out: List[Tuple[int, int, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        s = i
        e = min(n - 1, i + window - 1)
        txt = "\n".join(lines[s : e + 1]).strip()
        if txt:
            out.append((s, e, txt))
        i += max(1, stride)
    return out

class KBIndex:
    """
    In-memory hybrid index:
      * TF-IDF lexical matrix
      * Optional BM25 (natural language)
      * Optional FAISS (recall)
      * Final reranker (TF-IDF cosine or optional HF CrossEncoder)
    """
    def __init__(self, kb_dir: str):
        self.kb_dir = kb_dir
        self.chunks: List[Chunk] = []

        # Build chunks
        for doc_id, lines in list(iter_docs(kb_dir) or []):
            for s, e, txt in make_chunks(lines):
                self.chunks.append(Chunk(doc_id, s, e, txt))

        texts = [c.text for c in self.chunks] or ["placeholder"]
        self._empty = (texts == ["placeholder"])

        # TF-IDF
        self.lex_vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
        self.lex_mx = self.lex_vec.fit_transform(texts)

        # BM25
        self._bm25_enabled = os.getenv("BM25_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
        if BM25Okapi and not self._empty and self._bm25_enabled:
            self._bm25_corpus_tokens = [_tokenize(t) for t in texts]
            self._bm25 = BM25Okapi(self._bm25_corpus_tokens)
        else:
            self._bm25 = None

        # FAISS (optional) + reranker
        self.faiss = FaissIndex(texts, dims=settings.svd_components) if settings.faiss_enabled else None
        self.reranker = build_reranker()

    def lexical_topn(self, query: str, n: int = 25) -> List[int]:
        if self._empty:
            return []
        qv = self.lex_vec.transform([query])
        scores = (qv @ self.lex_mx.T).toarray().ravel()
        if scores.size == 0:
            return []
        idx = np.argsort(scores)[::-1]
        return [int(i) for i in idx[:n] if scores[i] > 0]

    def bm25_topn(self, query: str, n: int = 25) -> List[int]:
        if not self._bm25 or self._empty or not query.strip():
            return []
        qtok = _tokenize(query)
        scores = self._bm25.get_scores(qtok)

        if fuzz and len(qtok) <= 3:
            boost = np.zeros_like(scores, dtype=float)
            qstr = " ".join(qtok)
            for i, toks in enumerate(getattr(self, "_bm25_corpus_tokens", [])):
                if not toks:
                    continue
                s = fuzz.token_set_ratio(qstr, " ".join(toks)) / 100.0
                if s > 0.85:
                    boost[i] += 0.15 * s
            scores = scores + boost

        idx = np.argsort(scores)[::-1]
        return [int(i) for i in idx[:n] if scores[i] > 0]

    def faiss_topn(self, query: str, n: int = 25) -> List[int]:
        if self._empty or not self.faiss:
            return []
        return self.faiss.search(query, top_k=n)

    def hybrid_search(self, query: str, top_k: int = 3) -> List[Chunk]:
        if not query.strip():
            return []
        cand_ids = set(self.lexical_topn(query, n=25))
        for i in self.bm25_topn(query, n=25):
            cand_ids.add(i)
        for i in self.faiss_topn(query, n=25):
            cand_ids.add(i)
        if not cand_ids:
            return []
        candidates = [(i, self.chunks[i].text) for i in cand_ids]
        order = self.reranker.rerank(query, candidates)
        selected_ids = [candidates[i][0] for i in order[: max(1, top_k)]]
        return [self.chunks[i] for i in selected_ids]

_index: Optional[KBIndex] = None

def get_index() -> KBIndex:
    global _index
    if _index is None:
        os.makedirs(settings.kb_dir, exist_ok=True)
        _index = KBIndex(settings.kb_dir)
    return _index

def rebuild_index() -> KBIndex:
    global _index
    _index = None
    return get_index()

def hybrid_search(query: str, top_k: int = 3) -> List[Chunk]:
    return get_index().hybrid_search(query, top_k=top_k)
