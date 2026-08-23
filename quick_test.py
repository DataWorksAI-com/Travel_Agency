from money_customs_agent import answer

print("=== Fuzzy match (typo) ===")
print(answer("What are the money customs in Mexcio?"))

print("\n=== Semantic match (different phrasing, not a typo) ===")
print(answer("What are the tipping norms south of the US border?"))

print("\n=== Genuinely unsupported country ===")
print(answer("What are the money customs in Vietnam?"))
