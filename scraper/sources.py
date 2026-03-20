"""
sources.py  —  search URL configs for each floor plan website.

Each entry needs:
  label       : display name
  search_urls : list of listing pages to paginate through
  img_alt_re  : regex matching floor plan image alt text
"""

SOURCES: dict[str, dict] = {
    "houseplans": {
        "label": "HousePlans.com",
        "search_urls": (
            [f"https://www.houseplans.com/search?style={s}"
             for s in [
                 "ranch", "craftsman", "farmhouse", "traditional", "colonial",
                 "contemporary", "modern", "cottage", "bungalow", "cape-cod",
                 "mediterranean", "tudor", "split-level", "two-story", "one-story",
                 "country", "southern", "victorian", "prairie", "shingle",
                 "transitional", "modern-farmhouse",
             ]]
            + [f"https://www.houseplans.com/search?page={n}" for n in range(24, 500)]
        ),
        "img_alt_re": r"\bfloor\b",
    },
    "architecturaldesigns": {
        "label": "Architectural Designs",
        "search_urls": [
            f"https://www.architecturaldesigns.com/house-plans/search?style={s}"
            for s in [
                "ranch", "craftsman", "farmhouse", "traditional", "colonial",
                "contemporary", "cottage", "bungalow", "cape-cod", "country",
                "southern", "modern-farmhouse", "transitional", "tudor",
                "european", "mediterranean",
            ]
        ],
        "img_alt_re": r"floor.?plan|main.floor|first.floor|second.floor|lower.floor",
    },
    "eplans": {
        "label": "ePlans",
        "search_urls": [
            f"https://www.eplans.com/house-plans/{s}-house-plans"
            for s in [
                "ranch", "craftsman", "farmhouse", "traditional", "colonial",
                "cottage", "bungalow", "contemporary", "country", "southern",
                "cape-cod", "tudor", "european", "mediterranean", "modern",
            ]
        ],
        "img_alt_re": r"floor.?plan|first.floor|main.floor|level",
    },
    "familyhomeplans": {
        "label": "Family Home Plans",
        "search_urls": [
            f"https://www.familyhomeplans.com/house-plans/{s}"
            for s in [
                "ranch", "craftsman", "farmhouse", "traditional", "colonial",
                "country", "southern", "cottage", "contemporary", "bungalow",
            ]
        ],
        "img_alt_re": r"floor.?plan|first.floor|main.floor",
    },
    "dreamhomesource": {
        "label": "Dream Home Source",
        "search_urls": [
            f"https://www.dreamhomesource.com/house-plans/{s}"
            for s in [
                "ranch", "craftsman", "farmhouse", "traditional", "country",
                "colonial", "southern", "cottage", "bungalow", "contemporary",
            ]
        ],
        "img_alt_re": r"floor.?plan|first.floor|main.floor",
    },
    "thehousedesigners": {
        "label": "The House Designers",
        "search_urls": [
            f"https://www.thehousedesigners.com/house-plans/{s}/"
            for s in ["ranch", "craftsman", "farmhouse", "traditional", "country", "colonial"]
        ],
        "img_alt_re": r"floor.?plan|first.floor|main.floor",
    },
    "coolhouseplans": {
        "label": "Cool House Plans",
        "search_urls": [
            f"https://www.coolhouseplans.com/{s}-house-plans.html"
            for s in [
                "ranch", "craftsman", "farmhouse", "traditional", "country",
                "colonial", "cottage", "bungalow", "contemporary",
            ]
        ],
        "img_alt_re": r"floor.?plan|first.floor|main.floor",
    },
    "houseplansandmore": {
        "label": "House Plans and More",
        "search_urls": [
            f"https://www.houseplansandmore.com/house-plans/{s}-house-plans"
            for s in [
                "ranch", "craftsman", "farmhouse", "traditional", "country",
                "colonial", "cottage", "bungalow", "contemporary", "southern",
            ]
        ],
        "img_alt_re": r"floor.?plan|first.floor|main.floor|level",
    },
}
