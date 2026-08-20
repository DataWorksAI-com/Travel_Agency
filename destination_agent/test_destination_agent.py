from destination_agent.destination_agent import run_destination_agent


test_cases = [
    # --------------------------------------------------------
    # CASE 1 - Specific destination
    # --------------------------------------------------------
    {
        "name": "Named destination - Aruba",
        "prompt": "Tell me about Aruba.",
        "expected_keywords": [
            "Destination:",
            "Aruba",
            "Travel Features:",
            "Climate:",
            "Public Holidays:"
        ],
        "forbidden_keywords": [
            "Recommended Destination:"
        ]
    },

    {
        "name": "Named destination - Fiji",
        "prompt": "Tell me about Fiji.",
        "expected_keywords": [
            "Destination:",
            "Fiji",
            "Travel Features:",
            "Climate:",
            "Public Holidays:"
        ],
        "forbidden_keywords": [
            "Recommended Destination:"
        ]
    },

    # --------------------------------------------------------
    # CASE 2 - Preference recommendation
    # --------------------------------------------------------
    {
        "name": "Beach and diving recommendation",
        "prompt": (
            "I want a tropical destination "
            "with beaches and diving."
        ),
        "expected_keywords": [
            "Recommended Destination:",
            "beaches",
            "diving",
            "Climate:",
            "Public Holidays:"
        ],
        "forbidden_keywords": []
    },

    {
        "name": "Beach and nature recommendation",
        "prompt": (
            "I want a tropical destination "
            "with beaches and nature."
        ),
        "expected_keywords": [
            "Recommended Destination:",
            "beaches",
            "nature"
        ],
        "forbidden_keywords": []
    },

    {
        "name": "Attractions and nature recommendation",
        "prompt": (
            "I want a destination "
            "with attractions and nature."
        ),
        "expected_keywords": [
            "Recommended Destination:",
            "attractions",
            "nature"
        ],
        "forbidden_keywords": []
    },

    # --------------------------------------------------------
    # FILTERED MATCH - must NOT trip low-confidence
    #
    # This is the regression guard for the false negative. Low confidence used
    # to be `match_score < 0.30`, and this query's similarity is only ~0.14 -
    # so it used to refuse to recommend. But three hard metadata filters
    # (cool + Europe + inland) all held, which PROVES the match regardless of
    # the cosine value, so a recommendation is now required.
    # --------------------------------------------------------
    {
        "name": "Filtered match recommends despite low similarity",
        "prompt": "a cool historic European city inland",
        "expected_keywords": [
            "Recommended Destination:",
            "Climate:"
        ],
        "forbidden_keywords": [
            "Retrieval Note:",
            "Which of your stated preferences"
        ]
    },

    # --------------------------------------------------------
    # LOW-CONFIDENCE RETRIEVAL
    #
    # Genuinely weak retrieval: no structured terms at all, so no hard
    # constraint can be proved and similarity is the only evidence - and it is
    # below threshold. This is what low-confidence is actually for.
    # --------------------------------------------------------
    {
        "name": "Low-confidence recommendation (vague, no structured terms)",
        "prompt": "I want somewhere romantic and unforgettable.",
        "expected_keywords": [
            "Retrieval Note:",
            "current shared destination corpus",
            "Which of your stated preferences"
        ],
        "forbidden_keywords": [
            "geographically incompatible",
            "climatically incompatible",
            "globally impossible",
            "Recommended Destination:"
        ]
    }
]


passed = 0


for i, test in enumerate(test_cases, start=1):

    print("\n" + "=" * 60)
    print(f"TEST {i}: {test['name']}")
    print("=" * 60)

    print("Prompt:")
    print(test["prompt"])

    response = run_destination_agent(
        test["prompt"]
    )

    print("\nActual Response:")
    print(response)

    # --------------------------------------------------------
    # Check required keywords
    # --------------------------------------------------------
    missing_keywords = [
        keyword
        for keyword in test["expected_keywords"]
        if keyword.lower() not in response.lower()
    ]

    # --------------------------------------------------------
    # Check forbidden keywords
    # --------------------------------------------------------
    found_forbidden = [
        keyword
        for keyword in test["forbidden_keywords"]
        if keyword.lower() in response.lower()
    ]

    if (
        not missing_keywords
        and not found_forbidden
    ):
        print("\nResult: PASS")
        passed += 1

    else:
        print("\nResult: FAIL")

        if missing_keywords:
            print(
                "Missing keywords:",
                ", ".join(missing_keywords)
            )

        if found_forbidden:
            print(
                "Forbidden keywords found:",
                ", ".join(found_forbidden)
            )


print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)

print(
    f"Passed: {passed}/{len(test_cases)}"
)

print(
    f"Failed: "
    f"{len(test_cases) - passed}/"
    f"{len(test_cases)}"
)