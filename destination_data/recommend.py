"""Destination recommendation tool (RAG) for the Destination Agent data layer.

Case 2: the user described what they want but named no city. This embeds the
local destination corpus into a ChromaDB vector store and returns the closest
matches by meaning.

Corpus  : destinations.json, produced by build_corpus.py (rerun that to refresh).
Vectors : ChromaDB, local and on-disk under ./chroma_db - no API key, no service.
Embedding: ChromaDB's default all-MiniLM-L6-v2 (ONNX). The model file (~80 MB)
           downloads once on first use and is cached locally afterwards.

Contract:
  - returns plain Python lists/dicts, never JSON strings
  - never raises: every failure path returns {"error": "..."}
  - every field returned comes from the corpus, which came from real APIs
"""

# truststore MUST be injected before any HTTPS happens - here that includes the
# one-off embedding model download, not just requests.
import truststore

truststore.inject_into_ssl()

import hashlib
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS_PATH = os.path.join(BASE_DIR, "destinations.json")
VECTOR_DB_PATH = os.path.join(BASE_DIR, "chroma_db")
COLLECTION_NAME = "destinations"

DEFAULT_TOP_K = 5
MIN_TOP_K = 1
MAX_TOP_K = 20

# Bump this whenever the metadata written into the index changes shape. It is
# folded into the corpus fingerprint, so an index built by an older version is
# discarded and rebuilt instead of silently lacking the new filter fields.
INDEX_SCHEMA_VERSION = 2

# --------------------------------------------------------------------------
# Structured filter vocabulary - edit freely, the mapping below is literal.
#
# Vector similarity treats "inland" as a weak hint, so a query for
# ["cool", "historic", "Europe", "inland"] used to rank coastal Nice above
# inland Paris. These words are lifted out of the query and applied as hard
# metadata filters BEFORE ranking; whatever is left over is the "vibe" text
# that actually gets embedded.
# --------------------------------------------------------------------------
COASTAL_WORDS = {"coastal", "coast", "beach", "beaches", "sea", "seaside", "ocean", "seafront"}
INLAND_WORDS = {"inland", "landlocked"}

CONTINENT_WORDS = {
    "asia": "Asia",
    "asian": "Asia",
    "europe": "Europe",
    "european": "Europe",
    "africa": "Africa",
    "african": "Africa",
    "america": "America",
    "americas": "America",
    "american": "America",
    "caribbean": "America",
    "australia": "Australia",
    "pacific": "Pacific",
}

WARM_WORDS = {"warm", "hot", "tropical", "sunny", "balmy"}
COOL_WORDS = {"cool", "cold", "chilly", "mild", "temperate"}

WARM_MIN_C = 20.0   # "warm" means an annual mean at or above this
COOL_MAX_C = 18.0   # "cool" means an annual mean at or below this

# Below this many survivors, filters start being dropped one at a time.
MIN_RESULTS_BEFORE_RELAXING = 3

# If ranking on the leftover vibe text alone produces a top similarity below
# this, the same filtered set is re-ranked on the full query text instead. A
# vibe word absent from every description ("historic") otherwise makes every
# survivor score 0.0, which reads as broken even though the results are right.
WEAK_VIBE_SCORE = 0.05

# Least critical first: temperature is a gradient, continent is geographic,
# coastal/inland is a binary the traveller stated outright - so it goes last.
RELAXATION_ORDER = ("temperature", "continent", "coastal")

# --------------------------------------------------------------------------
# Retrieval confidence - a SEPARATE signal from match_score.
#
# match_score is cosine similarity and nothing else; it is deliberately left
# untouched. But similarity alone is a poor confidence test: a candidate that
# survived a hard coastal+Asia+warm metadata filter is a proven match even at a
# low cosine value, while a vague one-word query can only ever be judged by
# similarity. So confidence is judged on whether a structural constraint
# actually held, falling back to the score only when nothing structural applied.
# --------------------------------------------------------------------------
CONFIDENCE_HIGH = "high"
CONFIDENCE_LOW = "low"

# Used only when NO filter survived, i.e. similarity is the sole evidence.
CONFIDENCE_SCORE_THRESHOLD = 0.30

_collection = None  # cached across calls so the corpus is embedded only once


def _load_corpus():
    """Read destinations.json. Returns (entries, None) or (None, error_dict)."""
    if not os.path.exists(CORPUS_PATH):
        return None, {"error": f"Destination corpus not found at {CORPUS_PATH}. Run build_corpus.py first."}

    try:
        with open(CORPUS_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, {"error": f"Destination corpus could not be read ({exc})"}

    entries = payload.get("destinations") if isinstance(payload, dict) else None
    if not isinstance(entries, list) or not entries:
        return None, {"error": "Destination corpus contained no destinations. Rerun build_corpus.py."}

    usable = [
        e
        for e in entries
        if isinstance(e, dict)
        and isinstance(e.get("description"), str)
        and e.get("name")
        and e.get("lat") is not None
        and e.get("lon") is not None
    ]
    if not usable:
        return None, {"error": "Destination corpus had no entries with the required fields."}

    return usable, None


def _entry_metadata(entry):
    """Build the ChromaDB metadata row for one corpus entry.

    Chroma metadata values must be str/int/float/bool - never None - so a field
    the corpus does not have is OMITTED rather than stored empty. That is
    deliberate: an entry with unknown coastal status simply will not match an
    explicit coastal=True or coastal=False filter, instead of being guessed at.
    Three dynamic entries (added before structured enrichment existed) fall into
    this category.
    """
    metadata = {
        "name": str(entry.get("name")),
        "country_code": str(entry.get("country_code") or ""),
        "lat": float(entry["lat"]),
        "lon": float(entry["lon"]),
    }

    source_fields = entry.get("_source_fields")
    if not isinstance(source_fields, dict):
        return metadata

    coastal = source_fields.get("coastal")
    if isinstance(coastal, bool):
        metadata["coastal"] = coastal

    # IANA timezones are "Continent/City", so the prefix is the continent.
    timezone = source_fields.get("timezone")
    if isinstance(timezone, str) and "/" in timezone:
        metadata["continent"] = timezone.split("/")[0].replace("_", " ")

    avg_temp = source_fields.get("annual_avg_temp_c")
    if isinstance(avg_temp, (int, float)) and not isinstance(avg_temp, bool):
        metadata["avg_temp_c"] = float(avg_temp)

    return metadata


def _extract_filters(preferences):
    """Split preferences into hard structured filters plus leftover vibe text.

    Returns (filters, vibe_text). filters keys are the RELAXATION_ORDER names.
    Words not in any vocabulary above are left in vibe_text for the embedding.
    """
    if isinstance(preferences, str):
        tokens = preferences.replace(",", " ").split()
    elif isinstance(preferences, (list, tuple, set)):
        tokens = []
        for item in preferences:
            tokens.extend(str(item).replace(",", " ").split())
    elif isinstance(preferences, dict):
        tokens = []
        for key, value in preferences.items():
            tokens.extend(f"{key} {value}".replace(",", " ").split())
    else:
        tokens = []

    filters = {}
    leftover = []

    for token in tokens:
        word = token.strip().strip(".!?\"'").casefold()
        if not word:
            continue

        if word in COASTAL_WORDS:
            filters["coastal"] = True
        elif word in INLAND_WORDS:
            filters["coastal"] = False
        elif word in CONTINENT_WORDS:
            filters["continent"] = CONTINENT_WORDS[word]
        elif word in WARM_WORDS:
            filters["temperature"] = "warm"
        elif word in COOL_WORDS:
            filters["temperature"] = "cool"
        else:
            # Not a structured term - it is a "vibe" word, keep it for the vector.
            leftover.append(token.strip())

    return filters, " ".join(leftover)


def _build_where(filters):
    """Translate extracted filters into a ChromaDB where clause, or None."""
    clauses = []

    if "coastal" in filters:
        clauses.append({"coastal": {"$eq": bool(filters["coastal"])}})

    if "continent" in filters:
        clauses.append({"continent": {"$eq": filters["continent"]}})

    if filters.get("temperature") == "warm":
        clauses.append({"avg_temp_c": {"$gte": WARM_MIN_C}})
    elif filters.get("temperature") == "cool":
        clauses.append({"avg_temp_c": {"$lte": COOL_MAX_C}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _retrieval_confidence(applied_filters, relaxed_filters, match_score):
    """Rate how well-evidenced a result is: CONFIDENCE_HIGH or CONFIDENCE_LOW.

    high - at least one filter is still applied. A surviving metadata filter
           PROVED the constraint, so the candidate is a genuine match whatever
           its cosine value happens to be.
    high - no filters applied, but similarity cleared the threshold.
    low  - every filter had to be relaxed, or nothing structural applied and
           similarity is weak. Either way, no hard evidence backs the result.

    Deliberately does not look at match_score when a filter survived: that is
    the whole point of the fix. Never raises.
    """
    if applied_filters:
        return CONFIDENCE_HIGH

    # Every stated constraint had to be abandoned. A strong cosine score does
    # not rescue that - the result is not the thing the traveller asked for.
    if relaxed_filters:
        return CONFIDENCE_LOW

    # No structured terms in the query at all - similarity is the only evidence.
    try:
        score = float(match_score)
    except (TypeError, ValueError):
        return CONFIDENCE_LOW

    return CONFIDENCE_HIGH if score >= CONFIDENCE_SCORE_THRESHOLD else CONFIDENCE_LOW


def _describe_filter(name, filters):
    """Human-readable label for a filter, for the transparency note."""
    if name == "coastal":
        return "coastal" if filters.get("coastal") else "inland"
    if name == "continent":
        return f"in {filters.get('continent')}"
    if name == "temperature":
        band = filters.get("temperature")
        if band == "warm":
            return f"warm (>= {WARM_MIN_C} C)"
        return f"cool (<= {COOL_MAX_C} C)"
    return name


def _get_collection():
    """Build or reuse the vector store. Returns (collection, None) or (None, error_dict)."""
    global _collection
    if _collection is not None:
        return _collection, None

    entries, error = _load_corpus()
    if error:
        return None, error

    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as exc:
        return None, {"error": f"ChromaDB is not installed ({exc}). Run: pip install chromadb"}

    # Fingerprint the actual text we are about to embed. A count check is not
    # enough: editing descriptions without changing how many there are would
    # otherwise leave a stale index in place forever.
    fingerprint = hashlib.sha256(
        (
            f"schema={INDEX_SCHEMA_VERSION}\n"
            + "\n".join(
                f"{e.get('name')}|{e.get('country_code')}|{e.get('rag_text') or e['description']}"
                for e in entries
            )
        ).encode("utf-8")
    ).hexdigest()[:16]

    # Cosine space makes match_score readable as a similarity in 0..1.
    collection_metadata = {"hnsw:space": "cosine", "corpus_fingerprint": fingerprint}

    try:
        client = chromadb.PersistentClient(
            path=VECTOR_DB_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata=collection_metadata,
        )
    except Exception as exc:  # chromadb raises a wide range of backend errors
        return None, {"error": f"Vector store unavailable: could not open ChromaDB ({exc})"}

    try:
        stored_fingerprint = (collection.metadata or {}).get("corpus_fingerprint")
        needs_load = stored_fingerprint != fingerprint or collection.count() != len(entries)
    except Exception as exc:
        return None, {"error": f"Vector store unavailable: could not inspect ChromaDB ({exc})"}

    if needs_load:
        try:
            client.delete_collection(COLLECTION_NAME)
            collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata=collection_metadata,
            )
            collection.add(
                ids=[f"{e['name']}|{e.get('country_code')}|{i}" for i, e in enumerate(entries)],
                documents=[e.get("rag_text") or e["description"] for e in entries],
                metadatas=[_entry_metadata(e) for e in entries],
            )
        except Exception as exc:
            return None, {"error": f"Vector store unavailable: could not embed the corpus ({exc})"}

    _collection = collection
    return _collection, None


def _as_query_text(preferences):
    """Flatten preferences into one query string. Returns (text, None) or (None, error)."""
    if isinstance(preferences, str):
        text = preferences.strip()
    elif isinstance(preferences, (list, tuple, set)):
        parts = [str(p).strip() for p in preferences if p is not None and str(p).strip()]
        text = ", ".join(parts)
    elif isinstance(preferences, dict):
        parts = [f"{k}: {v}" for k, v in preferences.items() if v is not None and str(v).strip()]
        text = ", ".join(parts)
    elif preferences is None:
        return None, {"error": "preferences was empty - describe what the traveller wants"}
    else:
        return None, {"error": f"preferences must be a string, list or dict, got {type(preferences).__name__}"}

    if not text:
        return None, {"error": "preferences was empty - describe what the traveller wants"}
    return text, None


def recommend_destinations(preferences, top_k=DEFAULT_TOP_K):
    """Return a ranked shortlist of candidate destinations.

    Args:
        preferences: what the traveller wants - a string, a list of strings,
            or a dict of preference fields.
        top_k: how many candidates to return (default 5).

    Returns:
        On success, a list of {"name", "country_code", "lat", "lon",
        "description", "match_score"}, best first. match_score is cosine
        similarity in roughly 0..1, higher is closer.
        On any failure, a dict {"error": "..."}.
    """
    full_query_text, error = _as_query_text(preferences)
    if error:
        return error

    # Lift the hard constraints out; whatever remains is the text we embed.
    all_filters, vibe_text = _extract_filters(preferences)
    # If every word was a structured term there is no vibe left, so fall back to
    # the full query text - the filters still do the real work.
    query_text = vibe_text.strip() or full_query_text

    try:
        top_k = int(top_k)
    except (TypeError, ValueError):
        return {"error": f"top_k must be an integer, got {top_k!r}"}
    top_k = max(MIN_TOP_K, min(MAX_TOP_K, top_k))

    collection, error = _get_collection()
    if error:
        return error

    try:
        available = collection.count()
    except Exception as exc:
        return {"error": f"Vector store unavailable: could not count the collection ({exc})"}

    # Hard gate first, vector ranking second. Filters are dropped one at a time
    # (least critical first) only if too few destinations survive.
    active_filters = dict(all_filters)
    relaxed = []

    while True:
        where = _build_where(active_filters)
        try:
            results = collection.query(
                query_texts=[query_text],
                n_results=min(top_k, available),
                **({"where": where} if where else {}),
            )
        except Exception as exc:
            return {"error": f"Recommendation failed: vector search error ({exc})"}

        documents = (results.get("documents") or [[]])[0]
        if len(documents) >= min(MIN_RESULTS_BEFORE_RELAXING, top_k) or not active_filters:
            break

        # Drop the least critical filter still in play and try again.
        for candidate_name in RELAXATION_ORDER:
            if candidate_name in active_filters:
                relaxed.append(_describe_filter(candidate_name, all_filters))
                del active_filters[candidate_name]
                break
        else:
            break

    distances = (results.get("distances") or [[]])[0]

    # Weak-vibe re-rank. The filters have already decided WHO is eligible; this
    # only changes the ORDER and the score shown. A leftover vibe word that
    # appears nowhere in the corpus ("historic") is near-orthogonal to every
    # description, so every survivor scores ~0 and looks broken. Re-ranking the
    # same filtered set on the full query text gives meaningful numbers, because
    # words like "cool", "Europe" and "inland" do appear in the descriptions.
    reranked_on_full_text = False
    if (
        distances
        and query_text != full_query_text
        and (1.0 - float(distances[0])) < WEAK_VIBE_SCORE
    ):
        try:
            retry = collection.query(
                query_texts=[full_query_text],
                n_results=min(top_k, available),
                **({"where": where} if where else {}),
            )
        except Exception:
            retry = None  # keep the weak-but-valid original ordering

        retry_documents = (retry.get("documents") or [[]])[0] if retry else []
        if retry_documents:
            results = retry
            documents = retry_documents
            distances = (retry.get("distances") or [[]])[0]
            reranked_on_full_text = True

    metadatas = (results.get("metadatas") or [[]])[0]

    if not documents:
        return {"error": f"No destinations matched {query_text!r}"}

    applied = [_describe_filter(name, all_filters) for name in active_filters]
    note = None
    if relaxed:
        note = (
            "No destination in the corpus matched every stated preference, so "
            "these filters were relaxed and the results below do NOT match them: "
            + ", ".join(relaxed)
            + "."
        )

    shortlist = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        metadata = metadata or {}
        # Cosine distance -> similarity. Clamped because tiny negative
        # distances can come back from the index on near-identical vectors.
        score = 1.0 - float(distance)
        score = max(0.0, min(1.0, score))
        shortlist.append(
            {
                "name": metadata.get("name"),
                "country_code": metadata.get("country_code"),
                "lat": metadata.get("lat"),
                "lon": metadata.get("lon"),
                "description": document,
                "match_score": round(score, 3),
                # Repeated on every candidate so the return stays a plain list
                # while still disclosing what was and was not honoured.
                "applied_filters": applied,
                "relaxed_filters": relaxed,
                "retrieval_note": note,
                "ranked_on_full_text": reranked_on_full_text,
                # Additive signal for the agent layer: lets low-confidence be
                # driven by whether a hard constraint held, rather than by a
                # raw cosine score. match_score above is unchanged.
                "retrieval_confidence": _retrieval_confidence(
                    applied, relaxed, round(score, 3)
                ),
            }
        )

    # If even the full text scores near zero, similarity carries no signal here.
    # Sort by name so the order is at least deterministic rather than arbitrary.
    if shortlist and max(c["match_score"] for c in shortlist) < WEAK_VIBE_SCORE:
        shortlist.sort(key=lambda c: str(c["name"]))

    return shortlist


if __name__ == "__main__":
    probes = [
        ["warm", "coastal", "Asia"],
        ["cool", "historic", "Europe", "inland"],
        "",
    ]

    for probe in probes:
        print(f"\n=== recommend_destinations({probe!r}) ===")
        outcome = recommend_destinations(probe)

        if isinstance(outcome, dict):
            print(outcome)
            continue

        for rank, candidate in enumerate(outcome, start=1):
            print(f"\n{rank}. {candidate['name']} ({candidate['country_code']})  match_score={candidate['match_score']}")
            print(f"   lat={candidate['lat']}, lon={candidate['lon']}")
            print(f"   description: {candidate['description']}")
        print(f"\nkeys returned: {sorted(outcome[0].keys())}")
