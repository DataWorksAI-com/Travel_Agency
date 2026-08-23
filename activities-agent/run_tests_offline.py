"""
Offline test runner for the merged Activities Agent
-------------------------------------------------------
Runs the deterministic tool-level tests with no network access, no
OpenRouter API key, and no embedding-model download — using a fake,
hash-based embedding function (offline_embedding.py) instead of
Chroma's real one, against a separate chroma_db_offline/ collection.

Does NOT run the black-box agent tests — those call answer(), which
needs a real OpenRouter API key regardless of which embedding
function is used.

Run:
    python run_tests_offline.py

Exits non-zero on any failure.
"""

import os
import sys

os.environ["ACTIVITIES_OFFLINE_TEST"] = "true"

import build_vector_db
from test_jig import run_tool_tests


def main():
    print("=" * 60)
    print("OFFLINE MODE — building index with a fake embedder (no network, no model download)")
    print("=" * 60)
    build_vector_db.build_collection()
    print()

    passed, total = run_tool_tests()

    print("=" * 60)
    print(f"OFFLINE TOTAL: {passed}/{total} passing")
    print("=" * 60)

    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
