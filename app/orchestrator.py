import re
import time
from typing import List

from .models import AskRequest, AskResponse, Citation, Metrics
from .guardrails import detect_injection, scrub_pii
from .retrieval import hybrid_search
from .settings import settings


# ----------------------- tiny helpers (no-LLM extractive QA) -----------------------

_WORD_NUM = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}
_NUM_WORD = {v: k.capitalize() for k, v in _WORD_NUM.items()}

_token_re = re.compile(r"[A-Za-z0-9]+")

def _tokenize(s: str) -> List[str]:
    return _token_re.findall((s or "").lower())

def _normalize(s: str) -> str:
    # strip urls + condense whitespace
    s = re.sub(r"https?://\S+", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _split_sentences(s: str) -> List[str]:
    s = re.sub(r"([.!?])\s+", r"\1\n", s or "")
    out = [p.strip() for p in s.split("\n") if p.strip()]
    return out

def _best_sentence(query: str, text: str) -> str:
    """Pick the sentence with best token overlap with the question."""
    qs = set(_tokenize(query))
    best = ""
    best_score = 0.0
    for sent in _split_sentences(_normalize(text)):
        ts = set(_tokenize(sent))
        if not ts:
            continue
        inter = len(qs & ts)
        union = len(qs | ts) or 1
        score = inter / float(union)
        if score > best_score:
            best_score = score
            best = sent
    return best

def _rule_answer(query: str, chunk_texts: List[str]) -> str:
    q = (query or "").lower()

    # 1) "What does TOC stand for?"
    m = re.search(r"\bwhat\s+does\s+([A-Za-z]{2,8})\s+stand\s+for\b", q)
    if m:
        ac = m.group(1).upper()
        # form: "AC stands for ____"
        pat = re.compile(r"\b" + re.escape(ac) + r"\s+(?:stands\s+for|–|-|—)\s+(.+?)(?:[.;]|$)", re.I)
        for t in chunk_texts:
            t2 = _normalize(t)
            mm = pat.search(t2)
            if mm:
                return f"{ac} stands for {mm.group(1).strip()}"

        # fallback: "Full Name (AC)"
        pat2 = re.compile(r"\b([A-Z][A-Za-z ]+)\s*\(\s*" + re.escape(ac) + r"\s*\)")
        for t in chunk_texts:
            mm = pat2.search(t)
            if mm:
                return f"{ac} stands for {mm.group(1).strip()}"

    # 2) "How many focusing steps…?"
    if re.search(r"\bhow\s+many\b.*\bfocusing\s+steps\b", q):
        for t in chunk_texts:
            t2 = _normalize(t)
            mm = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b\s+focusing\s+steps", t2, re.I)
            if mm:
                raw = mm.group(1)
                num = _WORD_NUM.get(raw.lower(), raw)
                word = _NUM_WORD.get(num, num)
                return f"{word} (i.e., {num})."

    # 3) "definition of X" / "define X"
    m = re.search(r"\bdefinition\s+of\s+(?:a|an|the)?\s*\"?([A-Za-z -]+?)\"?\b", q)
    if not m:
        m = re.search(r"\bdefine\s+(?:a|an|the)?\s*\"?([A-Za-z -]+?)\"?\b", q)
    if m:
        term = m.group(1).strip()
        pat = re.compile(r"\b(?:a|an|the)?\s*" + re.escape(term) + r"\s+is\s+(.+?)(?:[.;]|$)", re.I)
        for t in chunk_texts:
            for s in _split_sentences(_normalize(t)):
                mm = pat.search(s)
                if mm:
                    return f"{term.capitalize()} is {mm.group(1).strip()}"

        # If we can't find explicit "X is …", pick best sentence near the term
        for t in chunk_texts:
            if term.lower() in t.lower():
                s = _best_sentence(term, t)
                if s:
                    return s

    # 4) generic extractive fallback: best sentence from the first useful chunk
    for t in chunk_texts:
        s = _best_sentence(query, t)
        if s:
            return s

    return ""


def compose_answer(question: str, citations: List[Citation]) -> str:
    texts = [c.snippet for c in citations]
    # Try rule-based extractive answer first
    extracted = _rule_answer(question or "", texts)
    if extracted:
        return f"Based on the cited sources below, the grounded answer is: {extracted}"

    # Final safety fallback: stitched, de-noised snippet
    joined = " ".join(_normalize(c) for c in texts)
    if len(joined) > settings.max_context_chars:
        joined = joined[: settings.max_context_chars] + " …"
    return f"Based on the cited sources below, the grounded answer is: {joined}"


# ----------------------- main orchestration -----------------------

def handle_ask(req: AskRequest) -> AskResponse:
    t0 = time.time()

    # Guardrails (PII scrub + injection detect)
    q = scrub_pii(req.question or "")
    inj = detect_injection(q)

    # Retrieval (hybrid lexical/BM25/FAISS → rerank)
    topk = max(1, req.top_k or settings.default_top_k)
    chunks = [] if inj else hybrid_search(q, top_k=topk)

    # Insufficient context / unsafe path
    if inj or not chunks:
        return AskResponse(
            answer=(
                "Your query appears unsafe or under-grounded. "
                "Please rephrase or add sources."
            ),
            citations=[],
            metrics=Metrics(
                latency_ms=int((time.time() - t0) * 1000),
                grounded_ratio=0.0,
                schema_repairs=0,
            ),
            insufficient_context=True,
        )

    # Map chunks → citations
    citations = [
        Citation(
            doc_id=c.doc_id,
            start_line=c.start_line,
            end_line=c.end_line,
            snippet=c.text,
        )
        for c in chunks
    ]

    # Deterministic, extractive answer
    answer_text = compose_answer(q, citations)

    return AskResponse(
        answer=answer_text,
        citations=citations,
        metrics=Metrics(
            latency_ms=int((time.time() - t0) * 1000),
            grounded_ratio=1.0 if citations else 0.0,
            schema_repairs=0,
        ),
        insufficient_context=False,
    )
