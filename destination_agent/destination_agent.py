from dotenv import load_dotenv
from deepagents import create_deep_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from destination_data import get_or_build_destination_profile

# Load ANTHROPIC_API_KEY from the .env file
load_dotenv()

# TOOL: Destination Information Lookup
@tool
def get_destination_info(destination_name: str) -> str:
    """
    Get travel-oriented information about a specific destination.

    Args:
        destination_name: The destination name,
        for example Aruba, Jamaica, Barbados, or Fiji.
    """

    profile = get_or_build_destination_profile(
        destination_name
    )

    if not profile:
        return (
            "No destination information "
            "was found."
        )

    lines = [
        f"Destination: {profile['destination']}",
        (
            "Available Features: "
            f"{', '.join(profile['features'])}"
        )
    ]

    for feature, places in profile["places"].items():

        # Only send the first five examples
        # to the LLM to keep the tool output concise.
        examples = places[:5]

        lines.append(
            f"{feature.title()}: "
            f"{', '.join(examples)}"
        )

    return "\n".join(lines)

# TOOL: Destination Search by Preferences
@tool
def search_destinations(
    preferences: list[str]
) -> str:
    """
    Find tropical destinations that match
    one or more travel preferences.

    Args:
        preferences:
            A list of travel preferences,
            for example:
            ["beaches", "diving"]
            or
            ["nature", "attractions"].
    """

    # Initial candidate destinations.
    #
    # These provide a starting search set.
    # Individual new destinations can still be
    # automatically added to the knowledge cache
    # through get_destination_info().
    candidate_destinations = [
        "Aruba",
        "Jamaica",
        "Bahamas",
        "Barbados",
        "Saint Lucia",
        "Curacao",
        "Dominican Republic",
        "Puerto Rico"
    ]

    matches = []

    for destination_name in candidate_destinations:

        # Cache first.
        #
        # If the profile already exists,
        # no Geoapify API call is needed.
        profile = get_or_build_destination_profile(
            destination_name
        )

        if not profile:
            continue

        features = profile["features"]

        matched_preferences = []

        for preference in preferences:

            for feature in features:

                if (
                    preference.lower()
                    in feature.lower()
                ):
                    matched_preferences.append(
                        preference
                    )
                    break

        if matched_preferences:

            matches.append(
                {
                    "destination": destination_name,
                    "features": features,
                    "matched_preferences":
                        matched_preferences
                }
            )

    if not matches:
        return (
            "No matching destinations "
            "were found."
        )

    # Destinations matching more preferences
    # appear first.
    matches.sort(
        key=lambda item: len(
            item["matched_preferences"]
        ),
        reverse=True
    )

    lines = []

    for match in matches:

        lines.append(
            f"Destination: "
            f"{match['destination']}\n"
            f"Features: "
            f"{', '.join(match['features'])}\n"
            f"Matched Preferences: "
            f"{', '.join(match['matched_preferences'])}"
        )

    return "\n\n".join(lines)

# LLM MODEL
model = ChatAnthropic(
    model="claude-haiku-4-5",
    temperature=0
)

# DESTINATION EXPERT AGENT
agent = create_deep_agent(
    model=model,
    tools=[
    get_destination_info,
    search_destinations
    ],
    system_prompt="""
    You are a Destination Expert Agent in a multi-agent travel planning system.

    Your responsibilities are:
    1. Provide information about a specific tropical destination.
    2. Help identify destinations that match a user's travel preferences.
    
    Available tools:
    1. get_destination_info: Use this when the user asks about a specific destination.
    2. search_destinations: Use this when the user describes one or more travel preferences and wants help choosing a destination.

    Return your final response in this format:
    Recommended Destination: <destination name>
    Reason: <short explanation based on the tool result>
    Matched Preferences: <preferences that match>

    IMPORTANT RULES:
    Do not add facts from your own knowledge.
    Use only information explicitly returned by the tools.
    Do not expand or embellish the tool results.
    Do not infer activities, weather details, geography, or other information that is not explicitly present in the tool output.
    Keep the response concise because this result may later be passed to an Orchestrator Agent.
    """
)

# DESTINATION AGENT RUNNER
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

# LOCAL TEST
if __name__ == "__main__":

    test_query = "Tell me about Barbados."
    #test_query = (
        #"I want a tropical destination with beaches and diving. "
        #"Where should I go?"
    #)

    response = run_destination_agent(test_query)

    print("\nDESTINATION AGENT RESPONSE:\n")
    print(response)

    