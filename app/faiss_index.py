import numpy as np
from typing import List
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD

try:
    import faiss  # type: ignore
except Exception:
    faiss = None


class FaissIndex:
    """
    Robust FAISS index with auto-dimensioning for small corpora.
    Falls back to "disabled" (empty results) if FAISS/SVD can't run.
    """
    def __init__(self, texts: List[str], dims: int = 256):
        self.texts = texts or ["placeholder"]
        self.enabled = False
        self.vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
        self.index = None
        self.svd = None

        try:
            X = self.vec.fit_transform(self.texts)  # (n_docs, n_features)
            n_features = int(X.shape[1])

            # Not enough signal for SVD? Disable FAISS gracefully.
            if (faiss is None) or (n_features < 3):
                print("[FAISS] Disabled (faiss missing or too few features).")
                return

            # Pick a safe component count for tiny KBs.
            # Keep at least 2 and strictly < n_features
            eff_dims = min(dims, max(2, n_features - 1, 8))
            self.svd = TruncatedSVD(n_components=eff_dims, random_state=42)

            Xr = self.svd.fit_transform(X)  # (n_docs, eff_dims)
            Xr = Xr / (np.linalg.norm(Xr, axis=1, keepdims=True) + 1e-12)

            self.index = faiss.IndexFlatIP(eff_dims)
            self.index.add(Xr.astype("float32"))
            self.enabled = True
            print(f"[FAISS] Enabled with eff_dims={eff_dims}, n_features={n_features}, n_docs={len(self.texts)}")
        except Exception as e:
            # Never crash the app because of vector search
            print(f"[FAISS] Disabled due to error: {e}")
            self.enabled = False
            self.index = None
            self.svd = None

    def search(self, query: str, top_k: int = 10) -> List[int]:
        if not self.enabled or not query.strip():
            return []  # let lexical path carry the demo
        try:
            qv = self.vec.transform([query])
            qv = self.svd.transform(qv)
            qv = qv / (np.linalg.norm(qv, axis=1, keepdims=True) + 1e-12)
            D, I = self.index.search(qv.astype("float32"), top_k)
            return [int(i) for i in I[0] if i >= 0]
        except Exception as e:
            # Fail soft; hybrid retrieval still works
            print(f"[FAISS] query fallback due to error: {e}")
            return []
