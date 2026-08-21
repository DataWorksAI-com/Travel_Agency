from dotenv import load_dotenv
from deepagents import create_deep_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from destination_agent.geoapify_data import get_or_build_destination_profile
from destination_data.resolve_place import resolve_place
from destination_data.climate import get_climate
from destination_data.holidays import get_holidays
from destination_data.recommend import recommend_destinations
from destination_agent.expand_rag_corpus import add_destination_to_shared_corpus

# Load ANTHROPIC_API_KEY from the .env file
load_dotenv()

# --------------------------------------------------------
# TOOL: Destination Information Lookup
# --------------------------------------------------------

@tool
def get_destination_info(destination_name: str) -> str:
    """
    Get travel-oriented information about a specific destination.

    This tool combines:
    - place resolution
    - Geoapify travel features
    - historical climate information
    - public holiday information

    Args:
        destination_name:
            The destination name,
            for example Tokyo, Aruba, Barbados, or Fiji.
    """

    # STEP 1: RESOLVE THE DESTINATION

    place = resolve_place(destination_name)

    # The shared data layer returns {"error": "..."}
    # instead of raising an exception.
    if (
        isinstance(place, dict)
        and "error" in place
    ):
        return (
            f"Could not resolve destination: "
            f"{destination_name}. "
            f"{place['error']}"
        )

    name = place["name"]
    country_code = place["country_code"]
    latitude = place["lat"]
    longitude = place["lon"]

    # STEP 2: GET GEOAPIFY TRAVEL FEATURES

    profile = get_or_build_destination_profile(
        name,
        latitude=latitude,
        longitude=longitude,
        country_code=country_code
    )

    # If a valid destination outside the current corpus
    # was requested, add it to the shared RAG corpus.
    if profile:

        add_destination_to_shared_corpus(
            destination_name=name,
            place=place,
            profile=profile
        )

    # STEP 3: GET CLIMATE INFORMATION

    climate = get_climate(
        latitude,
        longitude
    )

    # STEP 4: GET PUBLIC HOLIDAYS

    holidays = get_holidays(
        country_code
    )

    # STEP 5: BUILD TOOL OUTPUT

    lines = [
        f"Destination: {name}",
        f"Country Code: {country_code}",
        f"Latitude: {latitude}",
        f"Longitude: {longitude}",
    ]

    # GEOAPIFY PROFILE

    if profile:

        features = profile.get(
            "features",
            []
        )

        if features:
            lines.append(
                "Travel Features: "
                + ", ".join(features)
            )

        for feature, places in profile.get(
            "places",
            {}
        ).items():

            if not places:
                continue

            # Only send a few examples to the LLM
            # to keep tool output concise.
            examples = places[:5]

            lines.append(
                f"{feature.title()}: "
                + ", ".join(examples)
            )

    else:
        lines.append(
            "Geoapify travel features: unavailable."
        )

    # CLIMATE

    if (
        isinstance(climate, dict)
        and "error" not in climate
    ):

        best_months = climate.get(
            "best_months",
            []
        )

        avoid_months = climate.get(
            "avoid_months",
            []
        )

        if best_months:
            lines.append(
                "Best Months: "
                + ", ".join(best_months)
            )
        else:
            lines.append(
                "Best Months: "
                "No standout best months under "
                "the current climate thresholds."
            )

        if avoid_months:
            lines.append(
                "Avoid Months: "
                + ", ".join(avoid_months)
            )

        note = climate.get("note")

        if note:
            lines.append(
                f"Climate Note: {note}"
            )

    else:
        lines.append(
            "Climate information: unavailable."
        )

    # HOLIDAYS

    if isinstance(holidays, list):

        if holidays:

            # Only send the first five holidays
            # to keep the tool output concise.
            holiday_examples = holidays[:5]

            holiday_text = []

            for holiday in holiday_examples:

                holiday_text.append(
                    f"{holiday['date']} - "
                    f"{holiday['name']}"
                )

            lines.append(
                "Public Holidays: "
                + "; ".join(holiday_text)
            )

        else:
            lines.append(
                "Public Holidays: none returned."
            )

    elif (
        isinstance(holidays, dict)
        and "error" in holidays
    ):
        lines.append(
            "Public Holidays: unavailable "
            f"({holidays['error']})"
        )

    return "\n".join(lines)

# --------------------------------------------------------
# TOOL: Destination Search by Preferences
# --------------------------------------------------------

@tool
def search_destinations(
    preferences: list[str]
):
    """
    Retrieve candidate destinations from the shared RAG
    and enrich them with Geoapify travel features.
    """

    # STEP 1: RETRIEVE CANDIDATES FROM THE SHARED RAG

    candidates = recommend_destinations(
        preferences,
        top_k=5
    )

    if (
        isinstance(candidates, dict)
        and "error" in candidates
    ):
        return candidates

    # Record how well-evidenced the retrieval was.
    #
    # This used to be `candidates[0]["match_score"] < 0.30`, but a raw cosine
    # score is the wrong test: a candidate that survived a hard metadata filter
    # (coastal + Asia + warm) is a proven match even at a low similarity, and
    # flagging it as "no strong match" made the agent refuse to recommend
    # perfectly valid results. The data layer now reports whether a structural
    # constraint actually held, and only falls back to the score when the query
    # contained no structured terms at all.
    retrieval_confidence = None

    if candidates:
        retrieval_confidence = candidates[0].get(
            "retrieval_confidence"
        )

    enriched_candidates = []

    # STEP 2: ENRICH EACH CANDIDATE WITH GEOAPIFY

    for candidate in candidates:

        name = candidate["name"]
        latitude = candidate["lat"]
        longitude = candidate["lon"]

        profile = get_or_build_destination_profile(
            name,
            latitude=latitude,
            longitude=longitude,
            country_code=candidate["country_code"]
        )

        enriched_candidate = {
            "name": name,
            "country_code": candidate["country_code"],
            "lat": latitude,
            "lon": longitude,
            "description": candidate["description"],
            "match_score": candidate["match_score"],
            # Forwarded from the data layer so the model can see WHICH hard
            # constraints were honoured and which had to be dropped, instead of
            # inferring quality from the similarity score alone.
            "applied_filters": candidate.get(
                "applied_filters",
                []
            ),
            "relaxed_filters": candidate.get(
                "relaxed_filters",
                []
            ),
            "retrieval_confidence": candidate.get(
                "retrieval_confidence"
            ),
        }

        if profile:

            enriched_candidate["travel_features"] = (
                profile.get("features", [])
            )

            enriched_candidate["places"] = (
                profile.get("places", {})
            )

        else:

            enriched_candidate["travel_features"] = []
            enriched_candidate["places"] = {}

        enriched_candidates.append(
            enriched_candidate
        )

    # STEP 3: ADD RETRIEVAL COVERAGE NOTE

    retrieval_note = None

    if retrieval_confidence == "low":
        retrieval_note = (
            "The retrieved destinations are the closest matches "
            "from the current shared destination corpus. "
            "The corpus may not contain a strong match for all "
            "of the user's preferences."
        )

    # STEP 4: RETURN CANDIDATES + RETRIEVAL NOTE

    return {
        "candidates": enriched_candidates,
        "retrieval_note": retrieval_note
    }

# --------------------------------------------------------
# LLM MODEL
# --------------------------------------------------------

model = ChatAnthropic(
    model="claude-haiku-4-5",
    temperature=0
)

# --------------------------------------------------------
# DESTINATION EXPERT AGENT
# --------------------------------------------------------

agent = create_deep_agent(
    model=model,
    tools=[
    get_destination_info,
    search_destinations
    ],
    system_prompt="""
    You are a Destination Expert Agent in a multi-agent travel planning system.

    Your job is to:
    1. Provide grounded information about a named destination.
    2. Recommend one destination when the user provides travel preferences.
    3. Use only information returned by the available tools.

    ROUTING
    CASE 1 - Specific destination
    If the user explicitly asks for information about a named destination, for example "Tell me about Paris":
    - Use get_destination_info.
    - Provide concise destination information using only the tool output.
    - Include available travel features, climate information, and public holidays.
    Do not treat every mention of a city as a Destination Agent request.
    For example, if the user's intent is "Find me a flight to Paris", Paris is already selected and destination recommendation is not needed.

    CASE 2 - Destination recommendation
    If the user provides travel preferences but does not name a selected destination:
    1. Use search_destinations to retrieve candidate destinations.
    2. Compare candidates using:
    - the user's stated preferences
    - the RAG description
    - Geoapify travel features and places
    - match_score as supporting retrieval evidence only
    3. match_score represents semantic similarity only. It is NOT a destination-quality score.
    4. Give priority to candidates with explicit tool evidence supporting more of the user's stated preferences.
    5. Do not count a preference as matched unless the retrieved tool data explicitly supports it.
    6. Select exactly ONE final Recommended Destination.
    7. After selecting the destination, call get_destination_info for that destination to retrieve detailed travel features, climate, and public holiday information.
    8. You may mention up to two alternative candidates, but only the Recommended Destination is handed to downstream agents.

    LOW-CONFIDENCE RETRIEVAL
    search_destinations returns:
    - candidates: the retrieved destination shortlist
    - retrieval_note: an optional warning when the current shared corpus does not contain a strong semantic match
    If retrieval_note is present:
    - State only that the current shared destination corpus does not contain a strong match for all stated preferences.
    - Do not explain WHY the preferences do not match.
    - Do not claim that the preferences are impossible, contradictory, incompatible, geographically incompatible, or climatically incompatible.
    - Do not make general geographic or climate claims unless they are explicitly returned by the tools.
    - Do not create hypothetical destination types or examples that were not returned by the tools.
    - Do not suggest destinations, regions, or examples that were not returned by the tools.
    - Report only the retrieved candidates and the user preferences that are explicitly supported by tool evidence.
    - Do not infer that an unsupported preference is absent globally; only state that it is not supported by the retrieved tool data.
    - Do not select a Recommended Destination in low-confidence mode.
    - Ask exactly one clarification question: "Which of your stated preferences is most important to prioritize?"
    - Do not provide example answers or suggest how the user should change their preferences.

    GROUNDING RULES
    - Do not add facts from your own knowledge.
    - Use only information explicitly returned by tools.
    - Do not infer country names from country codes unless the tool explicitly provides the country name.
    - Do not invent activities, geography, weather, travel advice, or destination characteristics.
    - Do not reinterpret or generalize tool results.
    - Do not turn several returned POIs into qualitative claims such as:"strong infrastructure", "extensive options", "high quality", "diverse experiences", or similar statements.
    - Do not describe a destination as "perfect", "excellent", "ideal", "best", or "superior" unless that wording is explicitly supported by tool data.
    - Prefer repeating retrieved facts directly rather than adding evaluative wording.
    - If climate or holiday information is unavailable, say it is unavailable and continue.
    - An empty best_months list does NOT mean climate data is unavailable.
    - Do not add an extra concluding summary.
    - Keep responses concise.

    For the Recommended Destination field:
    - Return exactly one destination.
    - Use only the exact value from the candidate's "name" field.
    - Do not append a country name or other qualifier.
    - Only this value should be treated as the downstream handoff destination.

    OUTPUT FORMAT
    CASE 1:
    Destination: <destination name>
    Travel Features: <available features>
    Climate: <best/avoid month information>
    Public Holidays: <available examples or unavailable>

    CASE 2 - normal retrieval:
    Recommended Destination: <exactly one destination>
    Reason: <short explanation using only retrieved evidence>
    Matched Preferences: <preferences explicitly supported by retrieved data>
    Climate: <available information for the selected destination>
    Public Holidays: <available examples or unavailable>
    Alternatives Considered: <optional, maximum 2>

    CASE 2 - retrieval_note present:
    Retrieval Note:
    The current shared destination corpus does not contain a strong match for all stated preferences.
    Closest Retrieved Options:
    - <destination>: <only preferences explicitly supported by tool data>
    - <destination>: <only preferences explicitly supported by tool data>
    - <destination>: <only preferences explicitly supported by tool data>
    Question: Which of your stated preferences is most important to prioritize?
   """
   )

# --------------------------------------------------------
# DESTINATION AGENT RUNNER
# --------------------------------------------------------

def run_destination_agent(user_query: str) -> str:
    """
    Run the Destination Expert Agent.

    Args:
        user_query: A destination-related request from the user
        or from the Orchestrator Agent.

    Returns:
        The final text response generated by the Destination Agent.
    """

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": user_query
                }
            ]
        }
    )

    # Return only the final Destination Agent response.
    # This makes the function easy for an Orchestrator to use.
    return result["messages"][-1].content

# --------------------------------------------------------
# LOCAL TEST
# --------------------------------------------------------

if __name__ == "__main__":

    test_query = "Tell me about Seychelles."
    #test_query = (
        #"I want a very cold inland destination with desert scenery and tropical diving."
        #"Where should I go?"
    #)

    response = run_destination_agent(test_query)

    print("\nDESTINATION AGENT RESPONSE:\n")
    print(response)


