"""Run the test jig with no network, no API key and no model download.

ALY 6980 Capstone / DataWorksAI AI Travel Agency / Vrushti Shah

Chroma's default embedding model is an 80 MB download on first use. That makes
the normal test run impossible on a machine that is offline, behind a proxy, or
simply being checked quickly by someone marking the work. This swaps in a
deterministic stand-in embedder and an in-memory database, then runs the real
suite unchanged.

    python run_tests_offline.py        # exits 0 on pass, 1 on failure

What this DOES prove: every hard filter, the Chroma query path, the reflection
step, the coverage refusal and the whole orchestrator contract.
What it does NOT prove: the QUALITY of the semantic ranking, which depends on
the real embedding model. Run test_jig.py directly for that.
"""

import hashlib

import chromadb.utils.embedding_functions as ef

import restaurant_finder as rf


class StubEmbedder(ef.EmbeddingFunction):
    """Deterministic stand-in: hashes text into a fixed-length vector.

    Deterministic matters. A random embedder would make the suite flaky and a
    flaky suite is worse than no suite.
    """

    def __call__(self, input):
        return [
            [b / 255.0 for b in hashlib.sha256(t.encode("utf-8")).digest()[:32]]
            for t in input
        ]

    def name(self):
        return "stub"


rf._COLLECTION = rf.build_collection(embedding_function=StubEmbedder(),
                                     in_memory=True)

import test_jig  # noqa: E402  (imported after the stub collection is installed)

raise SystemExit(0 if test_jig.run() else 1)
