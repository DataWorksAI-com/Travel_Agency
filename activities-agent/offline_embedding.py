"""
Deterministic stand-in embedding function for offline testing
------------------------------------------------------------------
Chroma's default embedding model requires a one-time ~80MB download
on first use, which fails with no internet access — this is what's
been causing build_vector_db.py to fail in restricted environments.

This gives Tier 2 (semantic search) a fixed, hash-based vector
instead of a real language-model embedding, so the vector-DB code
path (build index, query, return results) can be exercised fully
offline, with no network call and no model download.

This is NOT a real embedding — it does not capture meaning, only a
deterministic fingerprint of the text. Same input text always
produces the same vector, so results are reproducible, but this
should only be used for offline testing, never for real semantic
search quality.
"""

import hashlib


class OfflineFakeEmbeddingFunction:
    """A Chroma-compatible embedding function that needs no ML model.

    Chroma calls this like `embedding_function(["text1", "text2"])`
    and expects a list of equal-length float vectors back.
    """

    def __init__(self, dim: int = 32):
        self.dim = dim

    def __call__(self, input):
        vectors = []
        for text in input:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            repeated = (digest * ((self.dim // len(digest)) + 1))[: self.dim]
            vectors.append([b / 255.0 for b in repeated])
        return vectors

    def embed_query(self, input):
        """Chroma calls this for search queries specifically; without
        it, newer chromadb versions raise AttributeError on query()
        even though __call__ (used for indexing documents) works
        fine. Reuse the same deterministic hashing for consistency."""
        return self.__call__(input)

    def name(self) -> str:
        return "offline-fake-embedder"
