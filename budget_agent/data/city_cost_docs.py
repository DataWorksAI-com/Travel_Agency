"""
Source-of-truth travel cost documents for the Budget Agent's RAG pipeline.

Each entry is a short unstructured write-up (like a mini travel-cost
guide) for one destination. This is the "truth" corpus that gets
chunked, embedded, and stored in a vector DB. The agent retrieves the
most relevant document(s) for a user's destination + question, rather
than doing an exact dict-key lookup -- this is what makes it RAG
instead of a plain lookup tool.

Feel free to edit/expand these -- add more cities, more detail, or
split into finer-grained documents (e.g. one per cost category) for
better retrieval granularity later.
"""

CITY_COST_DOCS = [
    {
        "city": "Cancun",
        "country": "Mexico",
        "text": (
            "Cancun, Mexico is one of the most budget-friendly tropical "
            "destinations from the US East Coast. Round-trip flights from "
            "Boston typically run $350-500. Budget hotels and hostels near "
            "the hotel zone cost $60-100 per night, while all-inclusive "
            "resorts range $150-300 per night. Street food and local "
            "restaurants cost $8-15 per meal; hotel-zone restaurants run "
            "$25-45 per meal. Popular activities like snorkeling tours cost "
            "$40-70, and day trips to Chichen Itza or Tulum ruins run "
            "$80-150. A budget traveler can manage a 4-day trip for "
            "roughly $600-750 total; a comfortable mid-range trip runs "
            "$900-1,300."
        ),
    },
    {
        "city": "Maui",
        "country": "USA (Hawaii)",
        "text": (
            "Maui, Hawaii is a higher-cost tropical destination since it's "
            "domestic US pricing without the currency advantage of "
            "international spots. Round-trip flights from Boston (usually "
            "with a layover) run $700-950. Lodging is expensive: budget "
            "condos or motels start around $180-220 per night, while "
            "oceanfront resorts run $400-700 per night. Food costs are high "
            "due to import costs -- casual meals run $20-30, sit-down "
            "dinners $45-70. Activities like snorkeling or whale-watching "
            "tours cost $80-150, and the Road to Hana day tour runs "
            "$100-180. A realistic budget for a 4-day trip starts around "
            "$1,800-2,200 even on the frugal end."
        ),
    },
    {
        "city": "Phuket",
        "country": "Thailand",
        "text": (
            "Phuket, Thailand is a long-haul destination (20+ hours from "
            "Boston with layovers) but extremely affordable once there. "
            "Round-trip flights run $1,000-1,300 due to distance. Lodging "
            "is very cheap: guesthouses run $15-30 per night, mid-range "
            "hotels $40-70. Local Thai food costs $2-5 per meal at street "
            "stalls, $10-20 at tourist restaurants. Activities like island-"
            "hopping tours cost $30-60, and half-day cooking classes run "
            "$25-40. Despite the high flight cost, the low daily spend "
            "means a 5-day trip can total $1,400-1,700, competitive with "
            "closer destinations once you factor in the cheap ground costs."
        ),
    },
    {
        "city": "Bali",
        "country": "Indonesia",
        "text": (
            "Bali, Indonesia is similar to Phuket in cost structure: high "
            "flight cost, very low daily spend. Round-trip flights from "
            "Boston run $1,100-1,500 with multiple layovers. Villas with "
            "private pools can be found for $40-90 per night; basic "
            "guesthouses run $10-20. Local warungs (small restaurants) "
            "charge $2-6 per meal; beach clubs and tourist restaurants run "
            "$15-30. Popular activities like rice terrace tours, temple "
            "visits, or surf lessons run $20-50. A 6-day trip typically "
            "totals $1,600-2,000, mostly driven by the flight cost."
        ),
    },
    {
        "city": "Punta Cana",
        "country": "Dominican Republic",
        "text": (
            "Punta Cana, Dominican Republic is a popular all-inclusive "
            "resort destination with easy 3.5-hour flights from Boston "
            "costing $300-450 round-trip. Most travelers book all-inclusive "
            "resorts ranging $150-350 per night, which bundles food and "
            "many activities into one price. A la carte, meals outside "
            "resorts run $10-25. Excursions like catamaran tours or zip-"
            "lining cost $50-100. Because of the all-inclusive model, a "
            "4-night trip is often easiest to budget as a flat resort rate "
            "plus flights, typically totaling $900-1,600 depending on "
            "resort tier."
        ),
    },
    {
        "city": "Costa Rica (San Jose)",
        "country": "Costa Rica",
        "text": (
            "San Jose, Costa Rica serves as the gateway for Costa Rica's "
            "beach and rainforest destinations. Round-trip flights from "
            "Boston run $400-600. Eco-lodges and mid-range hotels cost "
            "$60-120 per night; budget hostels run $20-35. Local sodas "
            "(small eateries) charge $6-10 per meal; tourist restaurants "
            "run $15-30. Activities are a major cost driver: zip-lining "
            "tours run $60-90, volcano park entries $15-20, and wildlife "
            "tours $50-100. A 5-day trip covering San Jose plus a beach or "
            "rainforest excursion typically totals $1,000-1,400."
        ),
    },
    {
        "city": "Fiji",
        "country": "Fiji",
        "text": (
            "Fiji is a premium, harder-to-reach tropical destination from "
            "the US East Coast, usually requiring 20+ hours of flying with "
            "connections, costing $1,400-1,900 round-trip. Overwater "
            "bungalow resorts run $400-900 per night, though budget island "
            "hostels can be found for $30-60. Food at resorts is expensive "
            "($30-50 per meal) but local markets and casual eateries run "
            "$8-15. Activities like snorkeling the Coral Coast or diving "
            "trips cost $60-150. Given the flight cost alone, even a "
            "budget-conscious 5-day trip typically starts around "
            "$2,200-2,800."
        ),
    },
    {
        "city": "Seychelles",
        "country": "Seychelles",
        "text": (
            "Seychelles is one of the most expensive tropical destinations "
            "covered here, both in flights and on-the-ground costs. Round-"
            "trip flights from Boston (via Europe or the Middle East) run "
            "$1,600-2,200. Lodging skews luxury: resorts commonly run "
            "$300-800 per night, with limited budget options around "
            "$80-120. Meals run $20-40 at casual spots, $50+ at resort "
            "restaurants. Activities like island-hopping boat tours or "
            "diving trips cost $80-150. A realistic 5-day trip, even "
            "trimmed down, tends to total $3,000-4,000."
        ),
    },
    {
        "city": "Maldives",
        "country": "Maldives",
        "text": (
            "The Maldives is a bucket-list luxury destination with limited "
            "budget options. Round-trip flights from Boston (via Europe or "
            "the Middle East, plus a domestic seaplane transfer) run "
            "$1,300-1,800 for the international leg, plus $300-500 for "
            "resort transfers. Overwater villas commonly run $500-1,500 "
            "per night; guesthouse islands (a budget alternative) run "
            "$60-120 per night. Resort dining is often bundled into "
            "half/full-board packages costing $80-150 per person per day. "
            "Even choosing guesthouse islands over resorts, a 4-day trip "
            "typically totals $2,200-3,000 due to flight and transfer costs."
        ),
    },
    {
        "city": "Barbados",
        "country": "Barbados",
        "text": (
            "Barbados offers a relatively easy 4.5-hour direct flight from "
            "Boston, costing $400-600 round-trip. Beachfront hotels run "
            "$150-300 per night; guesthouses and smaller inns run $70-120. "
            "Local rum shops and casual eateries charge $10-18 per meal; "
            "beachfront restaurants run $25-45. Activities like catamaran "
            "cruises or rum distillery tours cost $60-100. A 4-day trip "
            "typically totals $1,100-1,600 for a mid-range experience."
        ),
    },
    {
        "city": "Montego Bay",
        "country": "Jamaica",
        "text": (
            "Montego Bay, Jamaica has direct flights from Boston running "
            "$350-550 round-trip and a strong all-inclusive resort market "
            "similar to Punta Cana. All-inclusive resorts range $180-400 "
            "per night; independent hotels run $80-150. Jerk stands and "
            "local eateries charge $8-15 per meal outside resorts. "
            "Activities like Dunn's River Falls tours or catamaran cruises "
            "cost $50-90. A 4-night all-inclusive trip typically totals "
            "$1,100-1,900 including flights."
        ),
    },
    {
        "city": "Phu Quoc",
        "country": "Vietnam",
        "text": (
            "Phu Quoc, Vietnam is an emerging, very affordable island "
            "destination, though flights from Boston are long (20+ hours "
            "with connections) at $1,000-1,400 round-trip. Beachfront "
            "bungalows run $25-50 per night; upscale resorts run $100-180. "
            "Local seafood restaurants charge $5-12 per meal. Activities "
            "like snorkeling tours or the Vinpearl Safari cost $15-35. "
            "Given the low daily costs, a 5-day trip typically totals "
            "$1,300-1,600, driven mostly by the flight."
        ),
    },
    {
        "city": "Krabi",
        "country": "Thailand",
        "text": (
            "Krabi, Thailand offers dramatic limestone-cliff beaches with "
            "similar pricing to Phuket. Round-trip flights from Boston run "
            "$1,000-1,300. Beach bungalows run $20-40 per night; resorts "
            "$70-130. Street food costs $2-5 per meal; tourist restaurants "
            "$10-18. Longtail boat tours to nearby islands (Railay, Phi "
            "Phi) cost $15-40. A 5-day trip typically totals $1,400-1,700, "
            "similar to Phuket given the shared flight-cost baseline."
        ),
    },
    {
        "city": "Tulum",
        "country": "Mexico",
        "text": (
            "Tulum, Mexico is a trendier, pricier alternative to Cancun "
            "just an hour down the coast, sharing the same flight cost "
            "range ($350-500 round-trip from Boston) but with higher "
            "on-the-ground prices. Boutique eco-hotels run $120-250 per "
            "night; budget guesthouses $50-80. Restaurants aimed at "
            "tourists run $20-40 per meal; local spots away from the beach "
            "road run $8-15. Cenote entry fees run $5-15 each, and bike "
            "rentals to explore ruins cost $10-15 per day. A 4-day trip "
            "typically totals $900-1,300."
        ),
    },
    {
        "city": "Oahu",
        "country": "USA (Hawaii)",
        "text": (
            "Oahu, Hawaii (Honolulu/Waikiki) is slightly cheaper than Maui "
            "due to more competition and budget lodging options, though "
            "still a premium domestic destination. Round-trip flights from "
            "Boston run $650-900. Budget hotels near Waikiki run "
            "$150-200 per night; resorts run $300-600. Food costs mirror "
            "Maui: casual meals $18-28, dinners $40-65. Activities like "
            "Pearl Harbor tours or snorkeling at Hanauma Bay cost $25-70. "
            "A 4-day trip typically totals $1,600-2,000."
        ),
    },
]
