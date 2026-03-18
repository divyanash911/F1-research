"""
F1 Research Program - Static Schedule Fallback
Used when FastF1 cannot reach the F1 API (offline, sandbox, etc.).
Provides 2024 and 2026 season data as a reliable fallback.
"""

# 2026 F1 Season Schedule (as of March 2026)
SCHEDULE_2026 = [
    {"round": 1,  "name": "Bahrain Grand Prix",          "circuit": "Bahrain International Circuit",         "location": "Sakhir",        "country": "Bahrain",      "race_date": "2026-03-16"},
    {"round": 2,  "name": "Saudi Arabian Grand Prix",    "circuit": "Jeddah Corniche Circuit",               "location": "Jeddah",        "country": "Saudi Arabia", "race_date": "2026-03-23"},
    {"round": 3,  "name": "Australian Grand Prix",       "circuit": "Albert Park Circuit",                   "location": "Melbourne",     "country": "Australia",    "race_date": "2026-03-30"},
    {"round": 4,  "name": "Japanese Grand Prix",         "circuit": "Suzuka International Racing Course",    "location": "Suzuka",        "country": "Japan",        "race_date": "2026-04-06"},
    {"round": 5,  "name": "Chinese Grand Prix",          "circuit": "Shanghai International Circuit",        "location": "Shanghai",      "country": "China",        "race_date": "2026-04-20"},
    {"round": 6,  "name": "Miami Grand Prix",            "circuit": "Miami International Autodrome",         "location": "Miami",         "country": "USA",          "race_date": "2026-05-04"},
    {"round": 7,  "name": "Emilia Romagna Grand Prix",   "circuit": "Autodromo Enzo e Dino Ferrari",         "location": "Imola",         "country": "Italy",        "race_date": "2026-05-18"},
    {"round": 8,  "name": "Monaco Grand Prix",           "circuit": "Circuit de Monaco",                     "location": "Monte Carlo",   "country": "Monaco",       "race_date": "2026-05-25"},
    {"round": 9,  "name": "Spanish Grand Prix",          "circuit": "Circuit de Barcelona-Catalunya",        "location": "Barcelona",     "country": "Spain",        "race_date": "2026-06-01"},
    {"round": 10, "name": "Canadian Grand Prix",         "circuit": "Circuit Gilles Villeneuve",             "location": "Montreal",      "country": "Canada",       "race_date": "2026-06-15"},
    {"round": 11, "name": "Austrian Grand Prix",         "circuit": "Red Bull Ring",                         "location": "Spielberg",     "country": "Austria",      "race_date": "2026-06-29"},
    {"round": 12, "name": "British Grand Prix",          "circuit": "Silverstone Circuit",                   "location": "Silverstone",   "country": "UK",           "race_date": "2026-07-06"},
    {"round": 13, "name": "Belgian Grand Prix",          "circuit": "Circuit de Spa-Francorchamps",          "location": "Spa",           "country": "Belgium",      "race_date": "2026-07-27"},
    {"round": 14, "name": "Hungarian Grand Prix",        "circuit": "Hungaroring",                           "location": "Budapest",      "country": "Hungary",      "race_date": "2026-08-03"},
    {"round": 15, "name": "Dutch Grand Prix",            "circuit": "Circuit Zandvoort",                     "location": "Zandvoort",     "country": "Netherlands",  "race_date": "2026-08-31"},
    {"round": 16, "name": "Italian Grand Prix",          "circuit": "Autodromo Nazionale Monza",             "location": "Monza",         "country": "Italy",        "race_date": "2026-09-07"},
    {"round": 17, "name": "Azerbaijan Grand Prix",       "circuit": "Baku City Circuit",                     "location": "Baku",          "country": "Azerbaijan",   "race_date": "2026-09-21"},
    {"round": 18, "name": "Singapore Grand Prix",        "circuit": "Marina Bay Street Circuit",             "location": "Singapore",     "country": "Singapore",    "race_date": "2026-10-05"},
    {"round": 19, "name": "United States Grand Prix",    "circuit": "Circuit of the Americas",               "location": "Austin",        "country": "USA",          "race_date": "2026-10-19"},
    {"round": 20, "name": "Mexico City Grand Prix",      "circuit": "Autodromo Hermanos Rodriguez",          "location": "Mexico City",   "country": "Mexico",       "race_date": "2026-10-26"},
    {"round": 21, "name": "São Paulo Grand Prix",        "circuit": "Autodromo Jose Carlos Pace",            "location": "São Paulo",     "country": "Brazil",       "race_date": "2026-11-09"},
    {"round": 22, "name": "Las Vegas Grand Prix",        "circuit": "Las Vegas Street Circuit",              "location": "Las Vegas",     "country": "USA",          "race_date": "2026-11-22"},
    {"round": 23, "name": "Qatar Grand Prix",            "circuit": "Losail International Circuit",          "location": "Lusail",        "country": "Qatar",        "race_date": "2026-11-30"},
    {"round": 24, "name": "Abu Dhabi Grand Prix",        "circuit": "Yas Marina Circuit",                    "location": "Abu Dhabi",     "country": "UAE",          "race_date": "2026-12-07"},
]

# 2024 F1 Season Schedule (complete)
SCHEDULE_2024 = [
    {"round": 1,  "name": "Bahrain Grand Prix",          "circuit": "Bahrain International Circuit",         "location": "Sakhir",        "country": "Bahrain",      "race_date": "2024-03-02"},
    {"round": 2,  "name": "Saudi Arabian Grand Prix",    "circuit": "Jeddah Corniche Circuit",               "location": "Jeddah",        "country": "Saudi Arabia", "race_date": "2024-03-09"},
    {"round": 3,  "name": "Australian Grand Prix",       "circuit": "Albert Park Circuit",                   "location": "Melbourne",     "country": "Australia",    "race_date": "2024-03-24"},
    {"round": 4,  "name": "Japanese Grand Prix",         "circuit": "Suzuka International Racing Course",    "location": "Suzuka",        "country": "Japan",        "race_date": "2024-04-07"},
    {"round": 5,  "name": "Chinese Grand Prix",          "circuit": "Shanghai International Circuit",        "location": "Shanghai",      "country": "China",        "race_date": "2024-04-21"},
    {"round": 6,  "name": "Miami Grand Prix",            "circuit": "Miami International Autodrome",         "location": "Miami",         "country": "USA",          "race_date": "2024-05-05"},
    {"round": 7,  "name": "Emilia Romagna Grand Prix",   "circuit": "Autodromo Enzo e Dino Ferrari",         "location": "Imola",         "country": "Italy",        "race_date": "2024-05-19"},
    {"round": 8,  "name": "Monaco Grand Prix",           "circuit": "Circuit de Monaco",                     "location": "Monte Carlo",   "country": "Monaco",       "race_date": "2024-05-26"},
    {"round": 9,  "name": "Canadian Grand Prix",         "circuit": "Circuit Gilles Villeneuve",             "location": "Montreal",      "country": "Canada",       "race_date": "2024-06-09"},
    {"round": 10, "name": "Spanish Grand Prix",          "circuit": "Circuit de Barcelona-Catalunya",        "location": "Barcelona",     "country": "Spain",        "race_date": "2024-06-23"},
    {"round": 11, "name": "Austrian Grand Prix",         "circuit": "Red Bull Ring",                         "location": "Spielberg",     "country": "Austria",      "race_date": "2024-06-30"},
    {"round": 12, "name": "British Grand Prix",          "circuit": "Silverstone Circuit",                   "location": "Silverstone",   "country": "UK",           "race_date": "2024-07-07"},
    {"round": 13, "name": "Hungarian Grand Prix",        "circuit": "Hungaroring",                           "location": "Budapest",      "country": "Hungary",      "race_date": "2024-07-21"},
    {"round": 14, "name": "Belgian Grand Prix",          "circuit": "Circuit de Spa-Francorchamps",          "location": "Spa",           "country": "Belgium",      "race_date": "2024-07-28"},
    {"round": 15, "name": "Dutch Grand Prix",            "circuit": "Circuit Zandvoort",                     "location": "Zandvoort",     "country": "Netherlands",  "race_date": "2024-08-25"},
    {"round": 16, "name": "Italian Grand Prix",          "circuit": "Autodromo Nazionale Monza",             "location": "Monza",         "country": "Italy",        "race_date": "2024-09-01"},
    {"round": 17, "name": "Azerbaijan Grand Prix",       "circuit": "Baku City Circuit",                     "location": "Baku",          "country": "Azerbaijan",   "race_date": "2024-09-15"},
    {"round": 18, "name": "Singapore Grand Prix",        "circuit": "Marina Bay Street Circuit",             "location": "Singapore",     "country": "Singapore",    "race_date": "2024-09-22"},
    {"round": 19, "name": "United States Grand Prix",    "circuit": "Circuit of the Americas",               "location": "Austin",        "country": "USA",          "race_date": "2024-10-20"},
    {"round": 20, "name": "Mexico City Grand Prix",      "circuit": "Autodromo Hermanos Rodriguez",          "location": "Mexico City",   "country": "Mexico",       "race_date": "2024-10-27"},
    {"round": 21, "name": "São Paulo Grand Prix",        "circuit": "Autodromo Jose Carlos Pace",            "location": "São Paulo",     "country": "Brazil",       "race_date": "2024-11-03"},
    {"round": 22, "name": "Las Vegas Grand Prix",        "circuit": "Las Vegas Street Circuit",              "location": "Las Vegas",     "country": "USA",          "race_date": "2024-11-23"},
    {"round": 23, "name": "Qatar Grand Prix",            "circuit": "Losail International Circuit",          "location": "Lusail",        "country": "Qatar",        "race_date": "2024-12-01"},
    {"round": 24, "name": "Abu Dhabi Grand Prix",        "circuit": "Yas Marina Circuit",                    "location": "Abu Dhabi",     "country": "UAE",          "race_date": "2024-12-08"},
]

# Circuit characteristics knowledge base
CIRCUIT_PROFILES = {
    "Bahrain International Circuit": {
        "type": "permanent",
        "downforce_level": "medium-high",
        "tyre_demands": "high",
        "overtaking": "medium",
        "key_characteristics": ["technical middle sector", "long straight DRS zone", "dusty off-line"],
        "favoured_traits": ["good mechanical grip", "tyre management"],
    },
    "Jeddah Corniche Circuit": {
        "type": "street",
        "downforce_level": "medium",
        "tyre_demands": "medium",
        "overtaking": "medium-high",
        "key_characteristics": ["high speed", "walls close", "DRS trains form easily"],
        "favoured_traits": ["power unit", "qualifying pace"],
    },
    "Albert Park Circuit": {
        "type": "street-style",
        "downforce_level": "medium",
        "tyre_demands": "low-medium",
        "overtaking": "low-medium",
        "key_characteristics": ["bumpy", "safety car likely", "track evolution significant"],
        "favoured_traits": ["one-lap pace", "adaptability"],
    },
    "Suzuka International Racing Course": {
        "type": "permanent",
        "downforce_level": "high",
        "tyre_demands": "medium-high",
        "overtaking": "low",
        "key_characteristics": ["figure of 8", "fast flowing S-curves", "technical"],
        "favoured_traits": ["aero balance", "driver skill"],
    },
    "Circuit de Monaco": {
        "type": "street",
        "downforce_level": "maximum",
        "tyre_demands": "low",
        "overtaking": "very low",
        "key_characteristics": ["no overtaking", "qualifying everything", "safety car likely"],
        "favoured_traits": ["qualifying", "concentration"],
    },
    "Circuit de Barcelona-Catalunya": {
        "type": "permanent",
        "downforce_level": "medium-high",
        "tyre_demands": "high",
        "overtaking": "medium",
        "key_characteristics": ["tyre deg circuit", "long corners", "well-known track"],
        "favoured_traits": ["tyre management", "race pace"],
    },
    "Silverstone Circuit": {
        "type": "permanent",
        "downforce_level": "medium-high",
        "tyre_demands": "medium-high",
        "overtaking": "medium-high",
        "key_characteristics": ["fast flowing", "famous corners (Maggotts/Becketts)", "variable weather"],
        "favoured_traits": ["aero balance", "wet weather capability"],
    },
    "Circuit de Spa-Francorchamps": {
        "type": "traditional",
        "downforce_level": "low-medium",
        "tyre_demands": "medium",
        "overtaking": "high",
        "key_characteristics": ["Eau Rouge", "Raidillon", "unpredictable weather", "power circuit"],
        "favoured_traits": ["power unit", "bravery"],
    },
    "Autodromo Nazionale Monza": {
        "type": "permanent",
        "downforce_level": "minimum",
        "tyre_demands": "low",
        "overtaking": "high",
        "key_characteristics": ["lowest drag setup", "DRS highways", "slipstream battles"],
        "favoured_traits": ["power unit", "low drag setup"],
    },
    "Marina Bay Street Circuit": {
        "type": "street",
        "downforce_level": "maximum",
        "tyre_demands": "medium",
        "overtaking": "low",
        "key_characteristics": ["night race", "safety car very likely", "bumpy"],
        "favoured_traits": ["qualifying", "strategy with SC windows"],
    },
    "Circuit of the Americas": {
        "type": "permanent",
        "downforce_level": "high",
        "tyre_demands": "medium-high",
        "overtaking": "medium-high",
        "key_characteristics": ["Turn 1 overtaking", "technical sector 3", "bumpy"],
        "favoured_traits": ["all-round performance"],
    },
}

# 2024 Driver Championship final standings (for training/reference)
DRIVERS_2024 = {
    "VER": {"full_name": "Max Verstappen",    "team": "Red Bull Racing", "champion_2024": True},
    "NOR": {"full_name": "Lando Norris",      "team": "McLaren"},
    "LEC": {"full_name": "Charles Leclerc",   "team": "Ferrari"},
    "PIA": {"full_name": "Oscar Piastri",     "team": "McLaren"},
    "SAI": {"full_name": "Carlos Sainz",      "team": "Ferrari"},
    "HAM": {"full_name": "Lewis Hamilton",    "team": "Mercedes"},
    "RUS": {"full_name": "George Russell",    "team": "Mercedes"},
    "PER": {"full_name": "Sergio Perez",      "team": "Red Bull Racing"},
    "ALO": {"full_name": "Fernando Alonso",   "team": "Aston Martin"},
    "STR": {"full_name": "Lance Stroll",      "team": "Aston Martin"},
    "TSU": {"full_name": "Yuki Tsunoda",      "team": "RB"},
    "LAW": {"full_name": "Liam Lawson",       "team": "RB"},
    "ALB": {"full_name": "Alexander Albon",   "team": "Williams"},
    "SAR": {"full_name": "Logan Sargeant",    "team": "Williams"},
    "GAS": {"full_name": "Pierre Gasly",      "team": "Alpine"},
    "OCO": {"full_name": "Esteban Ocon",      "team": "Alpine"},
    "HUL": {"full_name": "Nico Hulkenberg",   "team": "Haas"},
    "MAG": {"full_name": "Kevin Magnussen",   "team": "Haas"},
    "BOT": {"full_name": "Valtteri Bottas",   "team": "Kick Sauber"},
    "ZHO": {"full_name": "Zhou Guanyu",       "team": "Kick Sauber"},
}

# 2026 Driver lineup
DRIVERS_2026 = {
    "VER": {"full_name": "Max Verstappen",    "team": "Red Bull Racing",     "car_num": 1},
    "NOR": {"full_name": "Lando Norris",      "team": "McLaren",             "car_num": 4},
    "LEC": {"full_name": "Charles Leclerc",   "team": "Ferrari",             "car_num": 16},
    "HAM": {"full_name": "Lewis Hamilton",    "team": "Ferrari",             "car_num": 44},
    "RUS": {"full_name": "George Russell",    "team": "Mercedes",            "car_num": 63},
    "ANT": {"full_name": "Andrea Kimi Antonelli", "team": "Mercedes",        "car_num": 12},
    "PIA": {"full_name": "Oscar Piastri",     "team": "McLaren",             "car_num": 81},
    "SAI": {"full_name": "Carlos Sainz",      "team": "Williams",            "car_num": 55},
    "ALO": {"full_name": "Fernando Alonso",   "team": "Aston Martin",        "car_num": 14},
    "STR": {"full_name": "Lance Stroll",      "team": "Aston Martin",        "car_num": 18},
    "TSU": {"full_name": "Yuki Tsunoda",      "team": "Red Bull Racing",     "car_num": 22},
    "LAW": {"full_name": "Liam Lawson",       "team": "RB",                  "car_num": 30},
    "HAD": {"full_name": "Isack Hadjar",      "team": "RB",                  "car_num": 6},
    "ALB": {"full_name": "Alexander Albon",   "team": "Williams",            "car_num": 23},
    "GAS": {"full_name": "Pierre Gasly",      "team": "Alpine",              "car_num": 10},
    "DOO": {"full_name": "Jack Doohan",       "team": "Alpine",              "car_num": 7},
    "HUL": {"full_name": "Nico Hulkenberg",   "team": "Kick Sauber",         "car_num": 27},
    "BEA": {"full_name": "Oliver Bearman",    "team": "Haas",                "car_num": 87},
    "OCO": {"full_name": "Esteban Ocon",      "team": "Haas",                "car_num": 31},
    "BOT": {"full_name": "Valtteri Bottas",   "team": "Kick Sauber",         "car_num": 77},
}


def get_schedule(year: int) -> list:
    """Return static schedule for given year."""
    if year == 2026:
        return SCHEDULE_2026
    elif year == 2024:
        return SCHEDULE_2024
    else:
        return SCHEDULE_2026  # fallback to 2026


def get_circuit_profile(circuit_name: str) -> dict:
    """Return circuit characteristics by name (partial match)."""
    circuit_name_lower = circuit_name.lower()
    for circuit, profile in CIRCUIT_PROFILES.items():
        if any(word in circuit.lower() for word in circuit_name_lower.split()):
            return {"circuit": circuit, **profile}
    return {"circuit": circuit_name, "type": "unknown", "note": "Profile not in database"}


def get_drivers(year: int) -> dict:
    """Return driver lineup for given year."""
    if year == 2026:
        return DRIVERS_2026
    return DRIVERS_2024
