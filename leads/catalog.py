"""What Projexian sells commercially, who buys it, and where to look.

BUYERS maps a buyer type to the OpenStreetMap filters that find it, a rough value weight
(bigger facilities, more recurring spend), and the services that buyer pays for. The email
leads with the first three services, so order matters.
"""

SERVICES = {
    "janitorial": "janitorial and day porter",
    "windows": "window cleaning",
    "floors": "carpet and floor care",
    "pressure": "pressure washing",
    "grounds": "landscaping and grounds",
    "snow": "snow and ice removal",
    "pest": "pest control",
    "waste": "trash and recycling hauling",
    "grease": "grease trap pumping",
    "hood": "kitchen hood and exhaust cleaning",
    "restrooms": "portable restrooms",
    "hvac": "HVAC maintenance",
    "plumbing": "plumbing",
    "electrical": "electrical",
    "painting": "painting",
    "parking": "parking lot sweeping and striping",
    "security": "security guards",
    "junk": "junk removal and cleanouts",
    "moving": "office moves",
    "fire": "fire extinguisher and fire door inspection",
    "construction_clean": "post-construction cleanup",
    "medwaste": "medical waste pickup",
    "rental": "equipment rental",
    "shred": "document shredding",
}

# key: (label, [overpass filters], weight 1-5, [service keys])
BUYERS = {
    "office": ("Office", ['["office"]["name"]', '["building"="office"]["name"]'], 3,
               ["janitorial", "windows", "floors", "pest", "hvac", "snow", "shred", "moving", "security", "parking"]),
    "property_mgr": ("Property manager", ['["office"="property_management"]', '["office"="estate_agent"]["name"]'], 5,
                     ["janitorial", "grounds", "snow", "pest", "pressure", "parking", "painting", "junk", "hvac", "plumbing"]),
    "apartments": ("Apartment community", ['["building"="apartments"]["name"]', '["landuse"="residential"]["name"]["operator"]'], 4,
                   ["grounds", "snow", "pest", "waste", "pressure", "painting", "junk", "parking", "plumbing"]),
    "hotel": ("Hotel", ['["tourism"~"^(hotel|motel)$"]["name"]'], 4,
              ["hood", "grease", "pest", "windows", "pressure", "floors", "grounds", "snow", "hvac", "waste"]),
    "restaurant": ("Restaurant", ['["amenity"~"^(restaurant|fast_food|cafe|bar|pub)$"]["name"]'], 2,
                   ["grease", "hood", "pest", "pressure", "waste", "windows", "plumbing"]),
    "medical": ("Medical facility", ['["amenity"~"^(hospital|clinic|doctors|dentist)$"]["name"]', '["healthcare"]["name"]'], 4,
                ["janitorial", "medwaste", "shred", "pest", "floors", "windows", "hvac", "grounds", "snow"]),
    "senior": ("Senior living", ['["social_facility"~"^(nursing_home|assisted_living|group_home)$"]["name"]', '["amenity"="nursing_home"]["name"]'], 4,
               ["janitorial", "hood", "grease", "pest", "floors", "grounds", "snow", "medwaste"]),
    "school": ("School or college", ['["amenity"~"^(school|college|university|kindergarten|childcare)$"]["name"]'], 4,
               ["janitorial", "floors", "grounds", "snow", "pest", "hood", "grease", "parking", "painting"]),
    "worship": ("Church", ['["amenity"="place_of_worship"]["name"]'], 2,
                ["janitorial", "grounds", "snow", "parking", "windows", "pest", "painting"]),
    "warehouse": ("Warehouse or industrial", ['["building"~"^(warehouse|industrial)$"]["name"]', '["landuse"="industrial"]["name"]', '["industrial"]["name"]'], 4,
                  ["janitorial", "waste", "pest", "snow", "parking", "rental", "pressure", "security", "junk"]),
    "retail_center": ("Shopping center", ['["shop"="mall"]["name"]', '["landuse"="retail"]["name"]'], 5,
                      ["parking", "pressure", "snow", "grounds", "security", "janitorial", "windows", "waste"]),
    "grocery": ("Grocery store", ['["shop"~"^(supermarket|wholesale)$"]["name"]'], 3,
                ["floors", "pest", "pressure", "parking", "snow", "grease", "waste"]),
    "auto": ("Car dealership", ['["shop"="car"]["name"]', '["shop"="car_repair"]["name"]'], 3,
             ["windows", "pressure", "parking", "snow", "janitorial", "grounds", "waste"]),
    "fitness": ("Gym or fitness center", ['["leisure"="fitness_centre"]["name"]', '["leisure"="sports_centre"]["name"]'], 2,
                ["janitorial", "floors", "pest", "windows", "hvac"]),
    "bank": ("Bank", ['["amenity"="bank"]["name"]'], 2,
             ["janitorial", "windows", "shred", "snow", "parking", "security"]),
    "construction": ("Builder or contractor", ['["office"="construction_company"]["name"]', '["craft"~"^(builder|construction)$"]["name"]'], 4,
                     ["construction_clean", "restrooms", "junk", "rental", "waste", "pressure", "security"]),
    "venue": ("Event venue", ['["amenity"~"^(events_venue|conference_centre|theatre|cinema)$"]["name"]', '["leisure"="stadium"]["name"]'], 4,
              ["janitorial", "restrooms", "security", "waste", "parking", "pressure", "pest"]),
}

# Large US metros: (name, state, lat, lon, radius km). The radius covers the core city and
# the commercial ring around it.
CITIES = [
    ("New York", "NY", 40.7128, -74.0060, 18), ("Los Angeles", "CA", 34.0522, -118.2437, 30),
    ("Chicago", "IL", 41.8781, -87.6298, 25), ("Houston", "TX", 29.7604, -95.3698, 30),
    ("Phoenix", "AZ", 33.4484, -112.0740, 30), ("Philadelphia", "PA", 39.9526, -75.1652, 20),
    ("San Antonio", "TX", 29.4241, -98.4936, 25), ("San Diego", "CA", 32.7157, -117.1611, 25),
    ("Dallas", "TX", 32.7767, -96.7970, 30), ("Fort Worth", "TX", 32.7555, -97.3308, 20),
    ("Austin", "TX", 30.2672, -97.7431, 25), ("Jacksonville", "FL", 30.3322, -81.6557, 25),
    ("San Jose", "CA", 37.3382, -121.8863, 20), ("Columbus", "OH", 39.9612, -82.9988, 20),
    ("Charlotte", "NC", 35.2271, -80.8431, 25), ("Indianapolis", "IN", 39.7684, -86.1581, 20),
    ("San Francisco", "CA", 37.7749, -122.4194, 15), ("Seattle", "WA", 47.6062, -122.3321, 20),
    ("Denver", "CO", 39.7392, -104.9903, 25), ("Washington", "DC", 38.9072, -77.0369, 20),
    ("Nashville", "TN", 36.1627, -86.7816, 25), ("Oklahoma City", "OK", 35.4676, -97.5164, 25),
    ("El Paso", "TX", 31.7619, -106.4850, 20), ("Boston", "MA", 42.3601, -71.0589, 18),
    ("Portland", "OR", 45.5152, -122.6784, 20), ("Las Vegas", "NV", 36.1699, -115.1398, 25),
    ("Detroit", "MI", 42.3314, -83.0458, 25), ("Memphis", "TN", 35.1495, -90.0490, 20),
    ("Louisville", "KY", 38.2527, -85.7585, 20), ("Baltimore", "MD", 39.2904, -76.6122, 18),
    ("Milwaukee", "WI", 43.0389, -87.9065, 20), ("Albuquerque", "NM", 35.0844, -106.6504, 20),
    ("Tucson", "AZ", 32.2226, -110.9747, 20), ("Fresno", "CA", 36.7378, -119.7871, 18),
    ("Sacramento", "CA", 38.5816, -121.4944, 20), ("Kansas City", "MO", 39.0997, -94.5786, 25),
    ("Atlanta", "GA", 33.7490, -84.3880, 25), ("Omaha", "NE", 41.2565, -95.9345, 20),
    ("Raleigh", "NC", 35.7796, -78.6382, 20), ("Miami", "FL", 25.7617, -80.1918, 25),
    ("Minneapolis", "MN", 44.9778, -93.2650, 20), ("Tampa", "FL", 27.9506, -82.4572, 25),
    ("Orlando", "FL", 28.5383, -81.3792, 25), ("New Orleans", "LA", 29.9511, -90.0715, 18),
    ("Cleveland", "OH", 41.4993, -81.6944, 20), ("Pittsburgh", "PA", 40.4406, -79.9959, 18),
    ("Cincinnati", "OH", 39.1031, -84.5120, 20), ("St. Louis", "MO", 38.6270, -90.1994, 20),
    ("Salt Lake City", "UT", 40.7608, -111.8910, 20), ("Richmond", "VA", 37.5407, -77.4360, 18),
]


def slug(city, state):
    return f"{city}-{state}".lower().replace(" ", "-").replace(".", "")
