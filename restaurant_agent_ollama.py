# =============================================================================
# ALY 6980 CAPSTONE - WEEK 2
# Restaurant Finder Deep Agent  --  FREE / LOCAL VERSION (Agentic RAG)
#
# Vrushti Shah, Northeastern University, August 2026
# Sponsor: DataWorksAI - Rapid Agentic RAG Development (AI Travel Agency)
#
# WHAT THIS IS
# ------------
# This is my Week 2 domain-expert agent: a restaurant finder for the travel
# bot. It is built the same way as my Hello World weather agent, with ONE big
# upgrade - the tool does real retrieval ("RAG"):
#
#   * every restaurant is stored in a local vector database (Chroma)
#   * a question is matched by MEANING (semantic search), not exact keywords
#   * hard filters then enforce city, price, and dietary needs
#
# It runs locally on Ollama - no API key, no cost - exactly the setup the
# mentors recommended for a narrow expert agent. The data is mock this week,
# but shaped like a real restaurant API so it can be swapped in later.
#
# BEFORE YOU RUN THIS
# -------------------
#   1. The Ollama application must be installed and running.
#   2. You must have the model:  ollama pull lfm2.5
#   3. Install the libraries:  pip install langchain-ollama chromadb
# =============================================================================


# -----------------------------------------------------------------------------
# STEP 1 - BRING IN CODE
# -----------------------------------------------------------------------------
from deepagents import create_deep_agent
from restaurant_finder import search_restaurants, warm_up


# -----------------------------------------------------------------------------
# STEP 2 - CHOOSE WHICH MODEL THINKS
# -----------------------------------------------------------------------------
# Same as the weather agent. "provider:model-name". Must match your Ollama
# model name exactly. If the agent ignores the tool, swap to the fallback line.

MODEL = "ollama:lfm2.5"          # first choice - built for tool calling
# MODEL = "ollama:granite4.1:3b" # lighter fallback if your Mac has less memory


# -----------------------------------------------------------------------------
# STEP 3 - WRITE THE TOOL
# -----------------------------------------------------------------------------
# This is the agent's one tool. It hands the request to the RAG engine in
# restaurant_finder.py and formats the answer as readable text.
#
# The type labels (str, int, bool) and the docstring are how Deep Agents tells
# the model what this tool does and how to call it. Keep them accurate.

def find_restaurants(
    query: str,
    city: str = "",
    cuisine: str = "",
    max_price: int = 0,
    min_rating: float = 0,
    vegetarian: bool = False,
    vegan: bool = False,
    gluten_free: bool = False,
) -> str:
    """Find restaurants that match a diner's request, using meaning-based
    search over a restaurant database plus hard filters.

    Args:
        query: what the person wants, in plain words, e.g.
               'romantic seafood dinner' or 'cheap casual tacos'.
        city: limit to one city such as 'Aruba', 'San Juan', 'Honolulu',
              'Cancun', 'Nassau', or 'Montego Bay'. Leave empty for any city.
        cuisine: limit to one cuisine such as 'Mexican', 'Seafood', 'Vegan',
                 'Italian', 'Thai', 'Steakhouse'. Leave empty for any cuisine.
        max_price: the most they want to spend per person, in US dollars.
                   Use 0 for no price limit.
        min_rating: only return places rated at least this (0 to 5). Use 0 for no limit.
        vegetarian: set True only if the diner needs vegetarian options.
        vegan: set True only if the diner needs vegan options.
        gluten_free: set True only if the diner needs gluten-free options.

    Returns:
        A numbered list of matching restaurants, or a message that none matched.
    """
    dietary = []
    if vegetarian:
        dietary.append("vegetarian")
    if vegan:
        dietary.append("vegan")
    if gluten_free:
        dietary.append("gluten_free")

    results = search_restaurants(
        query,
        city=city or None,
        cuisine=cuisine or None,
        max_price=max_price or None,
        min_rating=min_rating or None,
        dietary=dietary or None,
        top_k=5,
    )

    if not results:
        return ("No restaurants in the database matched those requirements. "
                "Try relaxing the price limit, the city, or the dietary filters.")

    lines = []
    for i, r in enumerate(results, 1):
        tags = [t for t, on in (
            ("vegetarian", r["vegetarian"]),
            ("vegan", r["vegan"]),
            ("gluten-free", r["gluten_free"]),
        ) if on]
        tag_str = ("  [" + ", ".join(tags) + "]") if tags else ""
        lines.append(
            f"{i}. {r['name']} - {r['cuisine']} in {r['city']}, "
            f"about ${r['price']} per person, rated {r['rating']}/5{tag_str}.\n"
            f"   {r['description']}"
        )
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# STEP 4 - BUILD THE AGENT
# -----------------------------------------------------------------------------
agent = create_deep_agent(
    model=MODEL,
    tools=[find_restaurants],
    system_prompt=(
        "You are a restaurant expert for a tropical holiday planner.\n"
        "\n"
        "RULES YOU MUST FOLLOW:\n"
        "1. For ANY question about where to eat, food, dining, or restaurants, "
        "you MUST call the find_restaurants tool. Never invent restaurants.\n"
        "2. Read the user's request and pass the right arguments: put their "
        "wish into 'query'; if they name a city, set 'city'; if they name a "
        "cuisine, set 'cuisine'; if they give a budget, set 'max_price'; if "
        "they ask for highly rated, set 'min_rating' (e.g. 4.5); if they say "
        "vegetarian, vegan, or gluten-free, set that flag to True.\n"
        "3. Only recommend restaurants that the tool returned. Do not add your "
        "own. If the tool returns none, say so plainly.\n"
        "4. Give advice only. Never attempt to book anything.\n"
        "\n"
        "Briefly introduce the results, then list them clearly."
    ),
)


# -----------------------------------------------------------------------------
# STEP 5 - RUN IT
# -----------------------------------------------------------------------------
if __name__ == "__main__":

    print("\n" + "=" * 62)
    print("  ALY 6980 - Week 2 - Restaurant Finder Deep Agent (RAG)")
    print("  Model: " + MODEL)
    print("=" * 62)
    print("\nLoading the restaurant database...")
    print("(The very first run downloads a small search model, about a minute.)")
    try:
        n = warm_up()
        print(f"Ready. {n} restaurants loaded into the vector database.\n")
    except Exception as error:
        print("\nCould not load the database yet:")
        print(error)
        print("Most likely: run  pip install chromadb  inside your .venv.\n")

    print("Ask for a restaurant. Examples you can try:")
    print("  - vegan gluten-free dinner in Aruba under 30 dollars")
    print("  - cheap casual tacos in Cancun")
    print("  - romantic seafood dinner in San Juan")
    print("Type  quit  and press Enter to stop.\n")

    while True:
        question = input("You: ").strip()

        if question.lower() in ("quit", "exit", "q"):
            print("\nStopped.\n")
            break
        if not question:
            continue

        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": question}]}
            )
            print("\nAgent:", result["messages"][-1].content, "\n")

        except Exception as error:
            print("\n--- SOMETHING WENT WRONG ---")
            print(error)
            print("\nMost likely causes, in order:")
            print("  1. The Ollama application is not running. Open it.")
            print("  2. chromadb or langchain-ollama is not installed. Run:")
            print("     pip install chromadb langchain-ollama")
            print("  3. The model name in MODEL does not match. Run  ollama list")
            print("----------------------------\n")
