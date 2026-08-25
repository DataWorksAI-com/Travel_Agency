"""
Mock restaurant dataset for the travel-agency restaurant finder.

This is placeholder ("mock") data, deliberately shaped like a real
restaurant API response so it can be swapped for a live source later
without changing the rest of the code. Each restaurant has:

  id           unique string id
  name         restaurant name
  city         which tropical city it is in
  cuisine      style of food
  price        average spend per person, in US dollars (integer)
  rating       average review score, 0 to 5
  vegetarian   True if it has good vegetarian options
  vegan        True if it has good vegan options
  gluten_free  True if it has good gluten-free options
  description  a short human description used for meaning-based search
"""

RESTAURANTS = [
    {"id": "r01", "name": "Palma Verde", "city": "Aruba", "cuisine": "Mediterranean",
     "price": 28, "rating": 4.6, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Breezy beachfront patio known for fresh salads, grilled vegetables, hummus platters and plenty of plant-based and gluten-free choices."},
    {"id": "r02", "name": "Coral Grill House", "city": "Aruba", "cuisine": "Steakhouse",
     "price": 55, "rating": 4.4, "vegetarian": False, "vegan": False, "gluten_free": True,
     "description": "Upscale steakhouse serving prime cuts, grilled lobster and a strong wine list; romantic candlelit tables by the water."},
    {"id": "r03", "name": "Mango Street Tacos", "city": "Aruba", "cuisine": "Mexican",
     "price": 14, "rating": 4.3, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Casual cheap taco stand with jackfruit and grilled veggie tacos, corn tortillas, and vegan and gluten-free friendly street food."},
    {"id": "r04", "name": "Zeerover Shack", "city": "Aruba", "cuisine": "Seafood",
     "price": 22, "rating": 4.7, "vegetarian": False, "vegan": False, "gluten_free": False,
     "description": "Rustic dockside seafood shack famous for fried fresh catch and shrimp, casual picnic tables, local favorite."},
    {"id": "r05", "name": "Sunset Vegan Kitchen", "city": "Aruba", "cuisine": "Vegan",
     "price": 26, "rating": 4.8, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Fully plant-based restaurant with vegan bowls, raw desserts, gluten-free options and sunset ocean views."},

    {"id": "r06", "name": "Casa Boricua", "city": "San Juan", "cuisine": "Puerto Rican",
     "price": 24, "rating": 4.6, "vegetarian": True, "vegan": False, "gluten_free": True,
     "description": "Traditional Puerto Rican mofongo, roast pork and plantains in a colorful Old San Juan courtyard; vegetarian mofongo available."},
    {"id": "r07", "name": "Verde Mesa", "city": "San Juan", "cuisine": "Vegetarian",
     "price": 30, "rating": 4.7, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Cozy vintage bistro focused on vegetarian and vegan plates, fresh market produce, and many gluten-free dishes."},
    {"id": "r08", "name": "La Marea Grill", "city": "San Juan", "cuisine": "Seafood",
     "price": 40, "rating": 4.5, "vegetarian": False, "vegan": False, "gluten_free": True,
     "description": "Modern waterfront seafood grill with ceviche, whole fish and cocktails; upscale but relaxed."},
    {"id": "r09", "name": "Pan y Cafe", "city": "San Juan", "cuisine": "Cafe",
     "price": 12, "rating": 4.2, "vegetarian": True, "vegan": False, "gluten_free": False,
     "description": "Budget breakfast and coffee spot with sandwiches, pastries and strong local coffee; cheap and cheerful."},
    {"id": "r10", "name": "El Fuego Steak", "city": "San Juan", "cuisine": "Steakhouse",
     "price": 58, "rating": 4.4, "vegetarian": False, "vegan": False, "gluten_free": True,
     "description": "Classic churrascaria with grilled meats carved tableside, hearty portions, lively atmosphere."},

    {"id": "r11", "name": "Aloha Greens", "city": "Honolulu", "cuisine": "Healthy Bowls",
     "price": 18, "rating": 4.6, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Fresh acai bowls, poke-style tofu bowls and smoothies; vegan and gluten-free friendly, quick and casual."},
    {"id": "r12", "name": "Kaimana Poke Bar", "city": "Honolulu", "cuisine": "Hawaiian",
     "price": 20, "rating": 4.7, "vegetarian": False, "vegan": False, "gluten_free": True,
     "description": "Beloved poke counter with fresh ahi tuna bowls, seaweed salads and rice; light, fresh and affordable."},
    {"id": "r13", "name": "Banyan Vegan Cafe", "city": "Honolulu", "cuisine": "Vegan",
     "price": 25, "rating": 4.8, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Plant-based comfort food, jackfruit tacos, vegan burgers and gluten-free desserts under a big banyan tree."},
    {"id": "r14", "name": "Diamond Steak & Fish", "city": "Honolulu", "cuisine": "Steakhouse",
     "price": 62, "rating": 4.5, "vegetarian": False, "vegan": False, "gluten_free": True,
     "description": "Fine-dining steak and fresh island fish with ocean views, an anniversary-worthy splurge."},
    {"id": "r15", "name": "Leilani Thai", "city": "Honolulu", "cuisine": "Thai",
     "price": 22, "rating": 4.4, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Family Thai kitchen with curries, tofu stir-fries and rice noodles; easy to make vegan and gluten-free."},

    {"id": "r16", "name": "Maya Jungle Kitchen", "city": "Cancun", "cuisine": "Mexican",
     "price": 27, "rating": 4.6, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Farm-to-table Yucatecan cooking with vegetable tacos, mole and fresh salsas; strong vegan and gluten-free menu."},
    {"id": "r17", "name": "El Muelle Seafood", "city": "Cancun", "cuisine": "Seafood",
     "price": 35, "rating": 4.5, "vegetarian": False, "vegan": False, "gluten_free": True,
     "description": "Lively marina seafood house with shrimp tacos, grilled octopus and margaritas; great for groups."},
    {"id": "r18", "name": "Taco Loco", "city": "Cancun", "cuisine": "Mexican",
     "price": 10, "rating": 4.2, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Super cheap late-night taqueria with corn-tortilla tacos, including grilled cactus and bean vegan options."},
    {"id": "r19", "name": "Villa Toscana", "city": "Cancun", "cuisine": "Italian",
     "price": 44, "rating": 4.4, "vegetarian": True, "vegan": False, "gluten_free": True,
     "description": "Romantic Italian trattoria with handmade pasta, wood-fired pizza and gluten-free pasta on request."},
    {"id": "r20", "name": "Selva Vegana", "city": "Cancun", "cuisine": "Vegan",
     "price": 23, "rating": 4.7, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Jungle-themed fully vegan spot with plant-based tacos, smoothie bowls and raw gluten-free cakes."},

    {"id": "r21", "name": "Conch Corner", "city": "Nassau", "cuisine": "Bahamian",
     "price": 19, "rating": 4.5, "vegetarian": False, "vegan": False, "gluten_free": False,
     "description": "Colorful shack for fresh conch salad, fried fish and island sides; casual and very local."},
    {"id": "r22", "name": "Island Greens", "city": "Nassau", "cuisine": "Healthy Bowls",
     "price": 21, "rating": 4.4, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Bright cafe with grain bowls, salads and smoothies; plenty of vegan and gluten-free picks near the beach."},
    {"id": "r23", "name": "Graycliff Dining", "city": "Nassau", "cuisine": "Fine Dining",
     "price": 75, "rating": 4.6, "vegetarian": True, "vegan": False, "gluten_free": True,
     "description": "Historic mansion fine-dining with a famous wine cellar, tasting menus and a vegetarian tasting option."},
    {"id": "r24", "name": "Bamboo Shack", "city": "Nassau", "cuisine": "Caribbean",
     "price": 13, "rating": 4.1, "vegetarian": False, "vegan": False, "gluten_free": True,
     "description": "Cheap and cheerful jerk chicken, rice and peas and plantains; grab-and-go island comfort food."},

    {"id": "r25", "name": "Scotchies Jerk", "city": "Montego Bay", "cuisine": "Jamaican",
     "price": 16, "rating": 4.7, "vegetarian": False, "vegan": False, "gluten_free": True,
     "description": "Legendary open-air jerk pit with smoky chicken and pork, festival bread and a laid-back vibe."},
    {"id": "r26", "name": "Ital Roots", "city": "Montego Bay", "cuisine": "Vegan",
     "price": 15, "rating": 4.6, "vegetarian": True, "vegan": True, "gluten_free": True,
     "description": "Rastafarian Ital kitchen serving plant-based stews, callaloo and ground provisions; naturally vegan and gluten-free."},
    {"id": "r27", "name": "Sugar Mill Terrace", "city": "Montego Bay", "cuisine": "Fine Dining",
     "price": 68, "rating": 4.5, "vegetarian": True, "vegan": False, "gluten_free": True,
     "description": "Elegant terrace restaurant on a former sugar estate, Caribbean-French menu, sunset views, special-occasion dining."},
    {"id": "r28", "name": "Pelican Bites", "city": "Montego Bay", "cuisine": "Seafood",
     "price": 24, "rating": 4.3, "vegetarian": False, "vegan": False, "gluten_free": True,
     "description": "Relaxed seaside grill for garlic shrimp, grilled snapper and cold beers right on the sand."},
]
