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
    # LOW-CONFIDENCE RETRIEVAL
    # --------------------------------------------------------
    {
        "name": "Low-confidence recommendation",
        "prompt": (
            "I want a very cold inland destination "
            "with desert scenery and tropical diving."
        ),
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