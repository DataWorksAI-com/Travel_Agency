"""
RAG retrieval tool for the Budget Agent.

This is what makes the agent's knowledge source RAG rather than a
plain dictionary lookup: instead of an exact key match (e.g.
`_COSTS["cancun"]`), the agent embeds the user's query and does a
similarity search over a vector store of city cost documents, so it
can retrieve relevant info even for fuzzy or partial queries (e.g.
"cheap tropical beach trip" could surface Cancun/Phuket/Vietnam docs
even without naming them exactly).

Requires the vector store to already be built:
    python scripts/build_vectorstore.py
"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings

PERSIST_DIR = str(Path(__file__).resolve().parent.parent.parent / "chroma_db")
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_embeddings = None
_vectorstore = None


def _get_vectorstore() -> Chroma:
    """Lazily load the embedding model + vector store (only once per process)."""
    global _embeddings, _vectorstore
    if _vectorstore is None:
        if not Path(PERSIST_DIR).exists():
            raise RuntimeError(
                f"Vector store not found at {PERSIST_DIR}.\n"
                "Run `python scripts/build_vectorstore.py` first."
            )
        _embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        _vectorstore = Chroma(persist_directory=PERSIST_DIR, embedding_function=_embeddings)
    return _vectorstore


@tool
def retrieve_cost_info(query: str, k: int = 3) -> list[dict]:
    """Retrieve the most relevant travel cost information for a query
    using semantic (vector) search over the city cost knowledge base.

    Use this for ANY question about destination costs -- it will find
    the most relevant city write-up(s) even if the destination isn't
    named exactly, or if the query is about a type of trip (e.g.
    "affordable beach destination" or "expensive luxury island").

    Args:
        query: A natural-language question or description, e.g.
            "cost of a 4-day trip to Cancun" or "cheapest tropical
            destination from Boston".
        k: Number of top matching chunks to return (default 3).

    Returns:
        A list of dicts, each with the matched city, country, and the
        retrieved text chunk.
    """
    vectorstore = _get_vectorstore()
    results = vectorstore.similarity_search(query, k=k)

    return [
        {
            "city": doc.metadata.get("city", "unknown"),
            "country": doc.metadata.get("country", "unknown"),
            "content": doc.page_content,
        }
        for doc in results
    ]


ALL_RAG_TOOLS = [retrieve_cost_info]
