"""Sentence-transformers wrapper with lazy-loaded model singleton."""

from __future__ import annotations

import numpy as np

_model = None
_model_name_loaded: str | None = None


def get_model(model_name: str = "all-MiniLM-L6-v2"):
    global _model, _model_name_loaded
    if _model is None or _model_name_loaded != model_name:
        print(f"  [embeddings] Loading model '{model_name}' (first use — may download ~80MB)...")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(model_name)
        _model_name_loaded = model_name
        print(f"  [embeddings] Model loaded.")
    return _model


def embed_texts(texts: list[str], model_name: str = "all-MiniLM-L6-v2") -> np.ndarray:
    """Returns (N, dim) float32 array."""
    if not texts:
        return np.array([])
    model = get_model(model_name)
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)


def mean_similarity_to_reference(
    texts: list[str],
    reference_texts: list[str],
    model_name: str = "all-MiniLM-L6-v2",
) -> list[float]:
    """
    For each text, compute mean cosine similarity to all reference_texts.
    Returns list of floats in [0, 1].
    Used for niche_similarity scoring in Phase 1.5.
    """
    if not texts or not reference_texts:
        return [0.0] * len(texts)

    text_embs = embed_texts(texts, model_name).astype(np.float64)
    ref_embs = embed_texts(reference_texts, model_name).astype(np.float64)

    # Normalize for cosine similarity
    text_norms = np.linalg.norm(text_embs, axis=1, keepdims=True)
    ref_norms = np.linalg.norm(ref_embs, axis=1, keepdims=True)
    text_embs = text_embs / np.maximum(text_norms, 1e-8)
    ref_embs = ref_embs / np.maximum(ref_norms, 1e-8)

    # (N_texts, N_refs) similarity matrix
    sim_matrix = np.clip(text_embs @ ref_embs.T, -1.0, 1.0)
    return sim_matrix.mean(axis=1).tolist()


def run_dbscan(
    embeddings: np.ndarray,
    eps: float = 0.4,
    min_samples: int = 2,
) -> np.ndarray:
    """
    Run DBSCAN clustering. Returns label array (len N).
    Label -1 means singleton/noise — still useful as a standalone candidate.
    """
    from sklearn.cluster import DBSCAN
    from sklearn.preprocessing import normalize

    normed = normalize(embeddings).astype(np.float64)
    # DBSCAN with cosine distance via precomputed metric
    # Convert cosine similarity to distance: dist = 1 - sim
    sim_matrix = np.clip(normed @ normed.T, -1.0, 1.0)
    dist_matrix = np.clip(1.0 - sim_matrix, 0.0, 2.0)

    db = DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed")
    labels = db.fit_predict(dist_matrix)
    return labels
