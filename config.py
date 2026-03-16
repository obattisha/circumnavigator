"""Constants and configuration for the circumnavigation optimizer."""

import os

# --------------------------------------------------------------------------- #
# Guinness rules
# --------------------------------------------------------------------------- #
RECORD_TIME_SECONDS = 44 * 3600 + 33 * 60 + 39   # 44h 33m 39s
MIN_LONGITUDE_COVERAGE = 360.0                     # degrees

# Guinness minimum distance: circumference of the Tropic of Cancer/Capricorn
# (both at |23.4366°| latitude → 2π × 6371 × cos(23.4366°) ≈ 36,788 km).
# Routes shorter than this are invalid under Guinness rules.
# NOTE: HKG→YVR→FRA→HKG great-circle total is only ~27,500 km — this does
# NOT qualify.  Enforce by default; pass --skip-min-distance to disable.
GUINNESS_MIN_DISTANCE_KM = 36_787.559

# --------------------------------------------------------------------------- #
# OpenFlights data URLs
# --------------------------------------------------------------------------- #
AIRPORTS_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
)
ROUTES_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
AIRPORTS_FILE = os.path.join(DATA_DIR, "airports.dat")
ROUTES_FILE = os.path.join(DATA_DIR, "routes.dat")

# --------------------------------------------------------------------------- #
# Flight graph filters
# --------------------------------------------------------------------------- #
MIN_ROUTE_DISTANCE_KM = 3_000   # only keep long-haul nonstop legs
MIN_OUTBOUND_EDGES = 2          # airport must have ≥ 2 qualifying outbound edges
MAX_LEGS = 5                    # DFS depth limit

# Widebody / long-haul capable IATA equipment codes.
# Empty field in routes.dat is treated as "include" (conservative).
WIDEBODY_EQUIPMENT = {
    "380", "388",                           # A380
    "359", "351",                           # A350
    "346", "345", "343", "342",             # A340
    "333", "332", "330",                    # A330
    "77W", "77L", "77X", "772", "773",      # B777
    "789", "788", "787",                    # B787 Dreamliner
    "748", "744", "74F", "74H",             # B747
    "763", "764", "762",                    # B767
    "321", "320",                           # A321XLR / A320neo (medium-haul sometimes included)
    "359", "35K",
    "223",                                  # A220 (sometimes used long-haul)
    "76W", "76X",
    "738", "73H", "73J",                    # B737 MAX long-haul rare, omit? included for completeness
}

# --------------------------------------------------------------------------- #
# Minimum connection times by country code (minutes)
# --------------------------------------------------------------------------- #
MIN_CONNECTION_MINUTES: dict[str, int] = {
    "default": 60,
    "US": 75,   # US customs / CBP takes time
    "CA": 60,
    "AE": 45,
    "QA": 45,
    "JP": 60,
    "SG": 60,
    "AU": 90,   # Australian border force
    "NZ": 90,
    "GB": 75,
    "DE": 60,
    "FR": 60,
    "NL": 60,
}

# --------------------------------------------------------------------------- #
# Supplemental route pairs missing from OpenFlights (e.g. Qatar Airways)
# These are fetched from AirLabs regardless of whether they appear in the
# OpenFlights graph, so the time-space search can find record-level routes
# like LAX → DOH → BNE → LAX.
# --------------------------------------------------------------------------- #
SUPPLEMENTAL_PAIRS: list[tuple[str, str]] = [
    ("LAX", "DOH"), ("DOH", "BNE"), ("BNE", "LAX"),
    ("LAX", "AUH"), ("AUH", "BNE"),
    ("DOH", "SYD"), ("SYD", "DOH"),
    ("DOH", "MEL"), ("MEL", "DOH"),
    ("DOH", "PER"), ("PER", "DOH"),
    ("DOH", "LAX"),
    ("AUH", "LAX"), ("LAX", "AUH"),
    ("AUH", "SYD"), ("SYD", "AUH"),
    ("AUH", "MEL"), ("MEL", "AUH"),
]

# --------------------------------------------------------------------------- #
# Six-continent world record
# Current record: SYD → SCL → PTY → MAD → ALG → DXB → SYD  (56h 56m)
# --------------------------------------------------------------------------- #
SIX_CONTINENT_RECORD_SECONDS = 56 * 3600 + 56 * 60   # 204,960 s

# ISO-3166-1 alpha-2 country code → continent code
# AF=Africa, AS=Asia, EU=Europe, NA=North America, OC=Oceania, SA=South America
COUNTRY_TO_CONTINENT: dict[str, str] = {
    # Africa
    "DZ": "AF", "EG": "AF", "MA": "AF", "TN": "AF", "LY": "AF", "MR": "AF",
    "ML": "AF", "SN": "AF", "GN": "AF", "CI": "AF", "GH": "AF", "BJ": "AF",
    "TG": "AF", "NG": "AF", "CM": "AF", "NE": "AF", "TD": "AF", "SD": "AF",
    "SS": "AF", "ET": "AF", "SO": "AF", "KE": "AF", "TZ": "AF", "UG": "AF",
    "RW": "AF", "BI": "AF", "CD": "AF", "AO": "AF", "ZM": "AF", "MW": "AF",
    "MZ": "AF", "ZW": "AF", "BW": "AF", "NA": "AF", "ZA": "AF", "SZ": "AF",
    "LS": "AF", "MG": "AF", "MU": "AF", "SC": "AF", "KM": "AF", "DJ": "AF",
    "ER": "AF", "GA": "AF", "GQ": "AF", "CG": "AF", "CF": "AF", "ST": "AF",
    "CV": "AF", "GM": "AF", "GW": "AF", "SL": "AF", "LR": "AF", "BF": "AF",
    "GR": "AF",  # Placeholder — see below for actual Greece
    # Asia
    "AE": "AS", "AF": "AS", "AM": "AS", "AZ": "AS", "BH": "AS", "BD": "AS",
    "BT": "AS", "BN": "AS", "KH": "AS", "CN": "AS", "GE": "AS", "HK": "AS",
    "IN": "AS", "ID": "AS", "IR": "AS", "IQ": "AS", "IL": "AS", "JP": "AS",
    "JO": "AS", "KZ": "AS", "KW": "AS", "KG": "AS", "LA": "AS", "LB": "AS",
    "MO": "AS", "MY": "AS", "MV": "AS", "MN": "AS", "MM": "AS", "NP": "AS",
    "KP": "AS", "KR": "AS", "OM": "AS", "PK": "AS", "PH": "AS", "QA": "AS",
    "SA": "AS", "SG": "AS", "LK": "AS", "SY": "AS", "TW": "AS", "TJ": "AS",
    "TH": "AS", "TL": "AS", "TM": "AS", "UZ": "AS", "VN": "AS", "YE": "AS",
    "PS": "AS", "CY": "AS",
    # Europe
    "AD": "EU", "AL": "EU", "AT": "EU", "BY": "EU", "BE": "EU", "BA": "EU",
    "BG": "EU", "HR": "EU", "CZ": "EU", "DK": "EU", "EE": "EU", "FI": "EU",
    "FR": "EU", "DE": "EU", "GR": "EU", "HU": "EU", "IS": "EU", "IE": "EU",
    "IT": "EU", "LV": "EU", "LI": "EU", "LT": "EU", "LU": "EU", "MT": "EU",
    "MD": "EU", "MC": "EU", "ME": "EU", "NL": "EU", "MK": "EU", "NO": "EU",
    "PL": "EU", "PT": "EU", "RO": "EU", "RU": "EU", "SM": "EU", "RS": "EU",
    "SK": "EU", "SI": "EU", "ES": "EU", "SE": "EU", "CH": "EU", "TR": "EU",
    "UA": "EU", "GB": "EU", "VA": "EU", "XK": "EU", "FO": "EU",
    # North America (includes Central America and Caribbean)
    "AG": "NA", "AI": "NA", "AW": "NA", "BB": "NA", "BL": "NA", "BM": "NA",
    "BS": "NA", "BZ": "NA", "CA": "NA", "CR": "NA", "CU": "NA", "DM": "NA",
    "DO": "NA", "GD": "NA", "GP": "NA", "GT": "NA", "HN": "NA", "HT": "NA",
    "JM": "NA", "KN": "NA", "KY": "NA", "LC": "NA", "MF": "NA", "MQ": "NA",
    "MS": "NA", "MX": "NA", "NI": "NA", "PA": "NA", "PM": "NA", "PR": "NA",
    "SV": "NA", "SX": "NA", "TC": "NA", "TT": "NA", "US": "NA", "VC": "NA",
    "VG": "NA", "VI": "NA", "CW": "NA",
    # South America
    "AR": "SA", "BO": "SA", "BR": "SA", "CL": "SA", "CO": "SA", "EC": "SA",
    "FK": "SA", "GF": "SA", "GY": "SA", "PE": "SA", "PY": "SA", "SR": "SA",
    "UY": "SA", "VE": "SA",
    # Oceania
    "AS": "OC", "AU": "OC", "CK": "OC", "FJ": "OC", "FM": "OC", "GU": "OC",
    "KI": "OC", "MH": "OC", "MP": "OC", "NC": "OC", "NF": "OC", "NR": "OC",
    "NZ": "OC", "PF": "OC", "PG": "OC", "PW": "OC", "SB": "OC", "TO": "OC",
    "TV": "OC", "VU": "OC", "WF": "OC", "WS": "OC",
}
# Fix the duplicate GR entry (Greece = EU, not AF — coding error above corrected)
COUNTRY_TO_CONTINENT["GR"] = "EU"

# Pairs to fetch for the six-continent search (inter-continental bridges).
# Grouped by corridor; both directions included where relevant.
SIX_CONTINENT_PAIRS: list[tuple[str, str]] = [
    # ── Oceania ↔ South America ──────────────────────────────────────────────
    ("SYD", "SCL"), ("SCL", "SYD"),
    ("MEL", "SCL"), ("SCL", "MEL"),
    ("AKL", "SCL"), ("SCL", "AKL"),
    ("SYD", "GRU"), ("GRU", "SYD"),

    # ── South America ↔ North / Central America ───────────────────────────────
    ("SCL", "PTY"), ("PTY", "SCL"),
    ("SCL", "MIA"), ("MIA", "SCL"),
    ("SCL", "JFK"), ("JFK", "SCL"),
    ("SCL", "LAX"), ("LAX", "SCL"),
    ("SCL", "ORD"), ("ORD", "SCL"),
    ("SCL", "IAH"), ("IAH", "SCL"),
    ("GRU", "MIA"), ("MIA", "GRU"),
    ("GRU", "JFK"), ("JFK", "GRU"),
    ("GRU", "ORD"), ("ORD", "GRU"),
    ("GRU", "IAD"), ("IAD", "GRU"),
    ("GRU", "PTY"), ("PTY", "GRU"),
    ("GRU", "LAX"), ("LAX", "GRU"),
    ("GRU", "YYZ"), ("YYZ", "GRU"),
    ("EZE", "MIA"), ("MIA", "EZE"),
    ("EZE", "JFK"), ("JFK", "EZE"),
    ("EZE", "ORD"), ("ORD", "EZE"),
    ("BOG", "MIA"), ("MIA", "BOG"),
    ("BOG", "JFK"), ("JFK", "BOG"),
    ("BOG", "PTY"), ("PTY", "BOG"),
    ("BOG", "IAH"), ("IAH", "BOG"),
    ("BOG", "LAX"), ("LAX", "BOG"),
    ("LIM", "MIA"), ("MIA", "LIM"),
    ("LIM", "JFK"), ("JFK", "LIM"),
    ("LIM", "PTY"), ("PTY", "LIM"),
    ("LIM", "IAH"), ("IAH", "LIM"),

    # ── South America ↔ Europe (direct, skip N. America) ─────────────────────
    ("SCL", "MAD"), ("MAD", "SCL"),
    ("SCL", "LHR"), ("LHR", "SCL"),
    ("SCL", "CDG"), ("CDG", "SCL"),
    ("SCL", "FRA"), ("FRA", "SCL"),
    ("GRU", "MAD"), ("MAD", "GRU"),
    ("GRU", "LHR"), ("LHR", "GRU"),
    ("GRU", "CDG"), ("CDG", "GRU"),
    ("GRU", "FRA"), ("FRA", "GRU"),
    ("GRU", "AMS"), ("AMS", "GRU"),
    ("GRU", "FCO"), ("FCO", "GRU"),
    ("GRU", "LIS"), ("LIS", "GRU"),
    ("EZE", "MAD"), ("MAD", "EZE"),
    ("EZE", "LHR"), ("LHR", "EZE"),
    ("EZE", "CDG"), ("CDG", "EZE"),
    ("EZE", "FRA"), ("FRA", "EZE"),
    ("EZE", "AMS"), ("AMS", "EZE"),
    ("BOG", "MAD"), ("MAD", "BOG"),
    ("BOG", "LHR"), ("LHR", "BOG"),
    ("LIM", "MAD"), ("MAD", "LIM"),

    # ── North / Central America ↔ Europe ─────────────────────────────────────
    ("PTY", "MAD"), ("MAD", "PTY"),
    ("PTY", "LHR"), ("LHR", "PTY"),
    ("PTY", "CDG"), ("CDG", "PTY"),
    ("MIA", "MAD"), ("MAD", "MIA"),
    ("MIA", "LHR"), ("LHR", "MIA"),
    ("MIA", "CDG"), ("CDG", "MIA"),
    ("MIA", "FRA"), ("FRA", "MIA"),
    ("MIA", "AMS"), ("AMS", "MIA"),
    ("MIA", "FCO"), ("FCO", "MIA"),
    ("MIA", "IST"), ("IST", "MIA"),
    ("JFK", "MAD"), ("MAD", "JFK"),
    ("JFK", "LHR"), ("LHR", "JFK"),
    ("JFK", "CDG"), ("CDG", "JFK"),
    ("JFK", "FRA"), ("FRA", "JFK"),
    ("JFK", "AMS"), ("AMS", "JFK"),
    ("JFK", "FCO"), ("FCO", "JFK"),
    ("JFK", "BCN"), ("BCN", "JFK"),
    ("JFK", "IST"), ("IST", "JFK"),
    ("ORD", "LHR"), ("LHR", "ORD"),
    ("ORD", "CDG"), ("CDG", "ORD"),
    ("ORD", "FRA"), ("FRA", "ORD"),
    ("ORD", "AMS"), ("AMS", "ORD"),
    ("LAX", "LHR"), ("LHR", "LAX"),
    ("LAX", "CDG"), ("CDG", "LAX"),
    ("LAX", "FRA"), ("FRA", "LAX"),
    ("LAX", "AMS"), ("AMS", "LAX"),
    ("LAX", "FCO"), ("FCO", "LAX"),
    ("LAX", "BCN"), ("BCN", "LAX"),
    ("IAD", "LHR"), ("LHR", "IAD"),
    ("IAD", "CDG"), ("CDG", "IAD"),
    ("IAD", "FRA"), ("FRA", "IAD"),
    ("IAH", "LHR"), ("LHR", "IAH"),
    ("IAH", "CDG"), ("CDG", "IAH"),

    # ── Europe ↔ Africa ───────────────────────────────────────────────────────
    ("MAD", "ALG"), ("ALG", "MAD"),
    ("MAD", "CMN"), ("CMN", "MAD"),
    ("MAD", "CAI"), ("CAI", "MAD"),
    ("MAD", "NBO"), ("NBO", "MAD"),
    ("MAD", "JNB"), ("JNB", "MAD"),
    ("MAD", "DKR"), ("DKR", "MAD"),
    ("LHR", "NBO"), ("NBO", "LHR"),
    ("LHR", "JNB"), ("JNB", "LHR"),
    ("LHR", "CAI"), ("CAI", "LHR"),
    ("LHR", "LOS"), ("LOS", "LHR"),
    ("LHR", "CMN"), ("CMN", "LHR"),
    ("CDG", "ALG"), ("ALG", "CDG"),
    ("CDG", "CMN"), ("CMN", "CDG"),
    ("CDG", "NBO"), ("NBO", "CDG"),
    ("CDG", "LOS"), ("LOS", "CDG"),
    ("CDG", "JNB"), ("JNB", "CDG"),
    ("CDG", "CAI"), ("CAI", "CDG"),
    ("CDG", "DKR"), ("DKR", "CDG"),
    ("FRA", "NBO"), ("NBO", "FRA"),
    ("FRA", "JNB"), ("JNB", "FRA"),
    ("FRA", "CAI"), ("CAI", "FRA"),
    ("FRA", "LOS"), ("LOS", "FRA"),
    ("AMS", "NBO"), ("NBO", "AMS"),
    ("AMS", "JNB"), ("JNB", "AMS"),
    ("AMS", "CAI"), ("CAI", "AMS"),
    ("AMS", "LOS"), ("LOS", "AMS"),
    ("IST", "NBO"), ("NBO", "IST"),
    ("IST", "JNB"), ("JNB", "IST"),
    ("IST", "CAI"), ("CAI", "IST"),
    ("IST", "LOS"), ("LOS", "IST"),
    ("IST", "CMN"), ("CMN", "IST"),
    ("IST", "ALG"), ("ALG", "IST"),
    ("FCO", "NBO"), ("NBO", "FCO"),
    ("FCO", "JNB"), ("JNB", "FCO"),
    ("FCO", "CAI"), ("CAI", "FCO"),
    ("BCN", "ALG"), ("ALG", "BCN"),
    ("BCN", "CMN"), ("CMN", "BCN"),
    ("LIS", "CMN"), ("CMN", "LIS"),

    # ── Africa ↔ Asia ─────────────────────────────────────────────────────────
    ("ALG", "DXB"), ("DXB", "ALG"),
    ("ALG", "DOH"), ("DOH", "ALG"),
    ("ALG", "AUH"), ("AUH", "ALG"),
    ("ALG", "IST"), ("IST", "ALG"),
    ("CMN", "DXB"), ("DXB", "CMN"),
    ("CMN", "DOH"), ("DOH", "CMN"),
    ("CMN", "AUH"), ("AUH", "CMN"),
    ("NBO", "DXB"), ("DXB", "NBO"),
    ("NBO", "DOH"), ("DOH", "NBO"),
    ("NBO", "AUH"), ("AUH", "NBO"),
    ("NBO", "SIN"), ("SIN", "NBO"),
    ("NBO", "BOM"), ("BOM", "NBO"),
    ("JNB", "DXB"), ("DXB", "JNB"),
    ("JNB", "DOH"), ("DOH", "JNB"),
    ("JNB", "AUH"), ("AUH", "JNB"),
    ("JNB", "SIN"), ("SIN", "JNB"),
    ("JNB", "HKG"), ("HKG", "JNB"),
    ("CAI", "DXB"), ("DXB", "CAI"),
    ("CAI", "DOH"), ("DOH", "CAI"),
    ("CAI", "AUH"), ("AUH", "CAI"),
    ("CAI", "SIN"), ("SIN", "CAI"),
    ("LOS", "DXB"), ("DXB", "LOS"),
    ("LOS", "DOH"), ("DOH", "LOS"),
    ("CPT", "DXB"), ("DXB", "CPT"),
    ("CPT", "DOH"), ("DOH", "CPT"),
    ("DKR", "DXB"), ("DXB", "DKR"),

    # ── Asia ↔ Oceania (supplement existing circumnavigation cache) ────────────
    ("SIN", "SYD"), ("SYD", "SIN"),
    ("SIN", "MEL"), ("MEL", "SIN"),
    ("SIN", "BNE"), ("BNE", "SIN"),
    ("SIN", "PER"), ("PER", "SIN"),
    ("SIN", "AKL"), ("AKL", "SIN"),
    ("HKG", "SYD"), ("SYD", "HKG"),
    ("HKG", "MEL"), ("MEL", "HKG"),
    ("ICN", "SYD"), ("SYD", "ICN"),
    ("ICN", "MEL"), ("MEL", "ICN"),
    ("NRT", "SYD"), ("SYD", "NRT"),
    ("NRT", "MEL"), ("MEL", "NRT"),
    ("BKK", "SYD"), ("SYD", "BKK"),
    ("KUL", "SYD"), ("SYD", "KUL"),
    ("KUL", "MEL"), ("MEL", "KUL"),
    ("PEK", "SYD"), ("SYD", "PEK"),
    ("BOM", "SYD"), ("SYD", "BOM"),
    ("DEL", "SYD"), ("SYD", "DEL"),
    ("DEL", "MEL"), ("MEL", "DEL"),
    # Gulf hubs ↔ Oceania (Emirates EK, Qatar QR, Etihad EY key routes)
    ("DXB", "SYD"), ("SYD", "DXB"),
    ("DXB", "MEL"), ("MEL", "DXB"),
    ("DXB", "BNE"), ("BNE", "DXB"),
    ("DXB", "PER"), ("PER", "DXB"),
    ("DXB", "AKL"), ("AKL", "DXB"),
    ("DOH", "SYD"), ("SYD", "DOH"),
    ("DOH", "MEL"), ("MEL", "DOH"),
    ("DOH", "BNE"), ("BNE", "DOH"),
    ("DOH", "PER"), ("PER", "DOH"),
    ("DOH", "AKL"), ("AKL", "DOH"),
    ("AUH", "SYD"), ("SYD", "AUH"),
    ("AUH", "MEL"), ("MEL", "AUH"),
    ("AUH", "BNE"), ("BNE", "AUH"),

    # ── North America ↔ Asia (for westbound possibilities) ────────────────────
    ("JFK", "NRT"), ("NRT", "JFK"),
    ("JFK", "ICN"), ("ICN", "JFK"),
    ("JFK", "HKG"), ("HKG", "JFK"),
    ("JFK", "SIN"), ("SIN", "JFK"),
    ("JFK", "DXB"), ("DXB", "JFK"),
    ("JFK", "BOM"), ("BOM", "JFK"),
    ("LAX", "NRT"), ("NRT", "LAX"),
    ("LAX", "ICN"), ("ICN", "LAX"),
    ("LAX", "HKG"), ("HKG", "LAX"),
    ("LAX", "SIN"), ("SIN", "LAX"),
    ("LAX", "BKK"), ("BKK", "LAX"),
    ("LAX", "PEK"), ("PEK", "LAX"),

    # ── South America ↔ Asia (rare but worth checking) ────────────────────────
    ("GRU", "DXB"), ("DXB", "GRU"),
    ("GRU", "DOH"), ("DOH", "GRU"),
]

# --------------------------------------------------------------------------- #
# AirLabs API  (free tier — sign up at airlabs.co)
# --------------------------------------------------------------------------- #
AIRLABS_API_KEY = os.environ.get("AIRLABS_API_KEY", "")
AIRLABS_ROUTES_URL = "https://airlabs.co/api/v9/routes"

# --------------------------------------------------------------------------- #
# Output paths
# --------------------------------------------------------------------------- #
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
API_CACHE_DIR = os.path.join(OUTPUT_DIR, "api_cache")
RESULTS_FILE = os.path.join(OUTPUT_DIR, "results.json")
