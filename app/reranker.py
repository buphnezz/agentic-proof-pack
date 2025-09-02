from __future__ import annotations

from typing import List, Tuple
import importlib

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .settings import settings


class BaseReranker:
    def rerank(self, query: str, candidates: List[Tuple[int, str]]) -> List[int]:
        """
        Given: query and candidates as (index, text) tuples.
        Return: indices into `candidates` in best → worst order.
        """
        raise NotImplementedError


class TfidfReranker(BaseReranker):
    """
    CPU-only, dependency-light reranker. Good default and deterministic.
    """
    def __init__(self):
        self.vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")

    def rerank(self, query: str, candidates: List[Tuple[int, str]]) -> List[int]:
        texts = [c[1] for c in candidates] or [""]
        X = self.vec.fit_transform([query] + texts)
        sim = cosine_similarity(X[0], X[1:]).ravel()
        # Return order over the *candidate list* positions
        return list(np.argsort(sim)[::-1])


def build_reranker() -> BaseReranker:
    """
    Try to build a HuggingFace CrossEncoder-based reranker if SENCODER_MODEL is set.
    Falls back silently to TF-IDF reranker to keep the app portable.
    """
    model = settings.sencoder_model
    if not model:
        return TfidfReranker()

    try:
        st = importlib.import_module("sentence_transformers")
        CrossEncoder = getattr(st, "CrossEncoder")
        ce = CrossEncoder(model)  # may download weights on first run

        class HFCEC(BaseReranker):
            def rerank(self, query: str, candidates: List[Tuple[int, str]]) -> List[int]:
                pairs = [(query, c[1]) for c in candidates]
                scores = ce.predict(pairs)  # higher is better
                return list(np.argsort(scores)[::-1])

        return HFCEC()
    except Exception:
        # Any issue (no package, CPU-only env, model download blocked) → deterministic fallback.
        return TfidfReranker()
