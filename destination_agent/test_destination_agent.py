from destination_agent import run_destination_agent


test_cases = [
    {
        "prompt": "I want a tropical destination with beaches and diving.",
        "expected_keywords": ["beaches", "diving"]
    },
    {
        "prompt": "I want a tropical destination with beaches and nature.",
        "expected_keywords": ["beaches", "nature"]
    },
    {
        "prompt": "I want a destination with attractions and nature.",
        "expected_keywords": ["attractions", "nature"]
    },
    {
        "prompt": "Tell me about Aruba.",
        "expected_keywords": ["Aruba", "beaches", "attractions"]
    },
    {
        "prompt": "Tell me about Fiji.",
        "expected_keywords": ["Fiji", "beaches"]
    }
]


passed = 0


for i, test in enumerate(test_cases, start=1):

    print(f"\n===== TEST {i} =====")
    print("Prompt:", test["prompt"])
    print(
        "Expected keywords:",
        ", ".join(test["expected_keywords"])
    )

    response = run_destination_agent(
        test["prompt"]
    )

    print("\nActual Response:")
    print(response)

    # Check whether all expected keywords
    # appear somewhere in the Agent response.
    missing_keywords = [
        keyword
        for keyword in test["expected_keywords"]
        if keyword.lower() not in response.lower()
    ]

    if not missing_keywords:
        print("\nResult: PASS")
        passed += 1

    else:
        print("\nResult: FAIL")
        print(
            "Missing keywords:",
            ", ".join(missing_keywords)
        )


print("\n===== TEST SUMMARY =====")
print(f"Passed: {passed}/{len(test_cases)}")
print(
    f"Failed: {len(test_cases) - passed}/"
    f"{len(test_cases)}"
)