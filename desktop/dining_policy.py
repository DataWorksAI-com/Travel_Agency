"""No restaurant claims without a connected restaurant data source."""
import re

UNAVAILABLE = (
    "Restaurant recommendations are unavailable: this version has no connected "
    "restaurant data source. I cannot verify restaurant names, addresses, menus, "
    "prices or Michelin ratings. Please check a restaurant's official website "
    "before making plans."
)


def is_dining_request(task):
    return bool(re.search(
        r"\b(?:restaurants?|dining|eateries|cafes?|cafés|where\s+to\s+eat)\b|餐厅|餐馆|饭店|吃饭|美食推荐",
        task, re.I,
    ))


def is_dining_only(task):
    return is_dining_request(task) and not re.search(
        r"\b(?:itinerary|flights?|plan\s+(?:a\s+|my\s+)?trip)\b|行程|航班|规划.*旅行",
        task, re.I,
    )
