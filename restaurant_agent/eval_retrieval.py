# =============================================================================
# ALY 6980 CAPSTONE - RESTAURANT AGENT
# Retrieval evaluation: does meaning-based search actually beat keyword search,
# and does the second look actually earn its place?
#
# Vrushti Shah, Northeastern University, August 2026
#
# WHY THIS EXISTS
# ---------------
# "It works" is not a result. This file turns the claim into two numbers that
# can go on a slide and into the blog:
#
#   EXPERIMENT 1 - retrieval quality.
#       20 questions written by hand, each paired with the restaurants a human
#       would accept as a correct answer. Every question is phrased the way a
#       traveller would actually ask, using words that mostly do NOT appear in
#       the restaurant descriptions ("somewhere romantic", "quick cheap bite").
#       That is the point: keyword search can only match words it can see,
#       while meaning-based search should find the right places anyway.
#       Scored with recall@3 - in what share of questions does at least one
#       acceptable restaurant appear in the top three?
#
#   EXPERIMENT 2 - the value of the second look.
#       A set of deliberately tight requests. Measures how many return a usable
#       recommendation with the reflection loop OFF versus ON. This is the
#       honest way to show what the loop buys, because the loop does not make
#       ranking better - it makes the difference between an answer and nothing.
#
# HOW TO RUN
#     source ~/Documents/capstone/.venv/bin/activate
#     python eval_retrieval.py
#
# The numbers are only meaningful with the real embedding model, so run this on
# the machine where the agent actually runs.
# =============================================================================

import re

try:  # works when imported as part of the restaurant_agent package
    from .restaurants_data import RESTAURANTS
    from .restaurant_finder import _doc_text, search_restaurants, search_with_reflection
except ImportError:  # works when run directly from its folder
    from restaurants_data import RESTAURANTS
    from restaurant_finder import _doc_text, search_restaurants, search_with_reflection

TOP_K = 3

# -----------------------------------------------------------------------------
# EXPERIMENT 1 - THE LABELLED QUESTION SET
# -----------------------------------------------------------------------------
# "relevant" lists the restaurants a reasonable person would accept. Labelling
# is a judgement call, so the rule used throughout is deliberately strict: a
# restaurant is listed only if its own description supports the request. The
# labels are written here in full so anyone can disagree with a specific one
# and re-run the numbers.

LABELLED = [
    ("somewhere romantic for an anniversary dinner",
     ["Coral Grill House", "Villa Toscana", "Diamond Steak & Fish", "Sugar Mill Terrace"]),
    ("a quick cheap bite on the go",
     ["Taco Loco", "Bamboo Shack", "Pan y Cafe", "Mango Street Tacos"]),
    ("plant-based food, nothing from an animal",
     ["Sunset Vegan Kitchen", "Banyan Vegan Cafe", "Selva Vegana", "Ital Roots", "Verde Mesa"]),
    ("fresh fish right by the water",
     ["Zeerover Shack", "La Marea Grill", "El Muelle Seafood", "Pelican Bites"]),
    ("a special occasion splurge, money no object",
     ["Diamond Steak & Fish", "Graycliff Dining", "Sugar Mill Terrace"]),
    ("morning coffee and something to eat",
     ["Pan y Cafe", "Aloha Greens"]),
    ("traditional local island cooking",
     ["Conch Corner", "Scotchies Jerk", "Casa Boricua", "Bamboo Shack"]),
    ("something light and healthy",
     ["Aloha Greens", "Island Greens", "Verde Mesa", "Palma Verde"]),
    ("relaxed family dinner, nothing fancy",
     ["Leilani Thai", "Mango Street Tacos", "Taco Loco", "Pelican Bites"]),
    ("grilled meat, a proper carnivore meal",
     ["Coral Grill House", "El Fuego Steak", "Diamond Steak & Fish", "Scotchies Jerk"]),
    ("authentic tacos",
     ["Mango Street Tacos", "Taco Loco", "Maya Jungle Kitchen"]),
    ("a good wine list with dinner",
     ["Coral Grill House", "Graycliff Dining"]),
    ("dining right on the beach with a view",
     ["Palma Verde", "Sunset Vegan Kitchen", "Sugar Mill Terrace", "Pelican Bites"]),
    ("late night food after a night out",
     ["Taco Loco"]),
    ("smoothies and bowls",
     ["Aloha Greens", "Island Greens", "Selva Vegana"]),
    ("spicy asian curry",
     ["Leilani Thai"]),
    ("an upscale tasting menu",
     ["Graycliff Dining", "Sugar Mill Terrace"]),
    ("watching the sunset while eating",
     ["Sunset Vegan Kitchen", "Sugar Mill Terrace"]),
    ("a no-frills place the locals go to",
     ["Zeerover Shack", "Conch Corner", "Scotchies Jerk", "Bamboo Shack"]),
    ("handmade pasta or pizza",
     ["Villa Toscana"]),
]


# -----------------------------------------------------------------------------
# THE BASELINE - PLAIN KEYWORD SEARCH
# -----------------------------------------------------------------------------
# Deliberately simple and deliberately fair: it searches exactly the same text
# the vector database indexes. It scores a restaurant by how many of the
# question's words appear in its description. This is what "search" meant
# before embeddings, and it is the thing the agentic-RAG claim has to beat.

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "at", "with",
    "my", "me", "i", "we", "is", "it", "some", "something", "somewhere",
    "place", "food", "eat", "eating", "dinner", "lunch", "good", "nothing",
    "no", "from", "right", "by", "after", "out", "while", "money", "object",
}


def _tokens(text):
    return [w for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOPWORDS]


_DOC_TOKENS = {r["name"]: set(_tokens(_doc_text(r))) for r in RESTAURANTS}


def keyword_search(query, top_k=TOP_K):
    """Rank restaurants by how many query words literally appear in their text."""
    q = set(_tokens(query))
    scored = [(len(q & words), name) for name, words in _DOC_TOKENS.items()]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [name for score, name in scored[:top_k] if score > 0]


def vector_search(query, top_k=TOP_K):
    """Rank restaurants by meaning, using the agent's own retrieval engine."""
    return [r["name"] for r in search_restaurants(query, top_k=top_k)]


def _recall_at_k(ranked, relevant):
    """1.0 if at least one acceptable answer made the top k, else 0.0."""
    return 1.0 if any(name in relevant for name in ranked) else 0.0


def _hit_at_1(ranked, relevant):
    return 1.0 if ranked and ranked[0] in relevant else 0.0


def experiment_one():
    print("=" * 74)
    print("  EXPERIMENT 1 - retrieval quality on 20 hand-labelled questions")
    print("=" * 74)
    print(f"  Metric: recall@{TOP_K} - did an acceptable restaurant reach the top {TOP_K}?\n")

    totals = {"keyword": [0.0, 0.0], "vector": [0.0, 0.0]}

    for query, relevant in LABELLED:
        kw = keyword_search(query)
        vec = vector_search(query)
        totals["keyword"][0] += _recall_at_k(kw, relevant)
        totals["keyword"][1] += _hit_at_1(kw, relevant)
        totals["vector"][0] += _recall_at_k(vec, relevant)
        totals["vector"][1] += _hit_at_1(vec, relevant)

        mark = lambda ranked: "HIT " if _recall_at_k(ranked, relevant) else "miss"
        print(f"  {mark(kw)} keyword | {mark(vec)} vector | {query}")
        print(f"         keyword top {TOP_K}: {', '.join(kw) if kw else '(no word overlap at all)'}")
        print(f"         vector  top {TOP_K}: {', '.join(vec)}")
        print()

    n = len(LABELLED)
    print("-" * 74)
    print(f"  {'':<10}{'recall@' + str(TOP_K):>12}{'top-1 hit rate':>18}")
    for label in ("keyword", "vector"):
        recall, hit1 = totals[label]
        print(f"  {label:<10}{recall / n:>11.0%}{hit1 / n:>18.0%}")
    print("-" * 74)
    lift = (totals["vector"][0] - totals["keyword"][0]) / n
    print(f"  Meaning-based search beats keyword search by {lift:+.0%} on recall@{TOP_K}.")
    print()
    return totals


# -----------------------------------------------------------------------------
# EXPERIMENT 2 - WHAT THE SECOND LOOK IS WORTH
# -----------------------------------------------------------------------------
# Each case is a request tight enough that the literal filters return nothing.
# Without the loop the traveller gets no restaurant at all. With it, they get a
# real recommendation and a plain statement of what was adjusted.

TIGHT_REQUESTS = [
    ("vegan gluten-free lunch in Honolulu under $15",
     {"city": "Honolulu", "max_price": 15, "dietary": ["vegan", "gluten-free"]}),
    ("highly rated vegan dinner in Nassau",
     {"city": "Nassau", "min_rating": 4.5, "dietary": ["vegan"]}),
    ("vegan Bahamian food in Aruba",
     {"city": "Aruba", "cuisine": "Bahamian", "dietary": ["vegan"]}),
    ("cheap fine dining in Montego Bay under $20",
     {"city": "Montego Bay", "cuisine": "Fine Dining", "max_price": 20}),
    ("top rated cheap seafood in San Juan under $20",
     {"city": "San Juan", "cuisine": "Seafood", "max_price": 20, "min_rating": 4.5}),
    ("gluten-free Italian in Cancun under $25",
     {"city": "Cancun", "cuisine": "Italian", "max_price": 25, "dietary": ["gluten_free"]}),
]


def experiment_two():
    print("=" * 74)
    print("  EXPERIMENT 2 - the second look, on requests that cannot be met literally")
    print("=" * 74)
    print("  Metric: how many tight requests return a usable recommendation?\n")

    without = 0
    with_loop = 0

    for description, filters in TIGHT_REQUESTS:
        plain = search_restaurants(description, top_k=TOP_K, **filters)
        looped, adjustments = search_with_reflection(description, top_k=TOP_K, **filters)

        without += 1 if plain else 0
        with_loop += 1 if looped else 0

        print(f"  {description}")
        print(f"    loop OFF: {'answer' if plain else 'NO ANSWER - traveller gets nothing'}")
        if looped:
            print(f"    loop ON : {looped[0]['name']} (${looped[0]['price']}, "
                  f"rated {looped[0]['rating']})")
            for note in adjustments:
                print(f"              adjusted - {note}")
        else:
            print("    loop ON : still nothing, and it says so rather than inventing one")
        print()

    n = len(TIGHT_REQUESTS)
    print("-" * 74)
    print(f"  Answered without the second look: {without}/{n}  ({without / n:.0%})")
    print(f"  Answered with the second look:    {with_loop}/{n}  ({with_loop / n:.0%})")
    print("-" * 74)
    print("  Every recovered answer states which requirement was adjusted, so a")
    print("  bent constraint is never presented as though it were met.")
    print()


if __name__ == "__main__":
    print()
    experiment_one()
    experiment_two()
    print("Note: these numbers are only meaningful under the real embedding model.")
    print("Run this on the machine where the agent itself runs.\n")
