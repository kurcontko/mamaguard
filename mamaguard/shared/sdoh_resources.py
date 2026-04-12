"""
Curated offline SDOH resource map -- fallback when findhelp.org/211 APIs
are unreachable or unconfigured.

This is a deliberately small, US-national, non-exhaustive list. Each entry
is verifiable, high-signal, and safe to recommend sight-unseen:

- National hotlines (211, WIC, SAMHSA, DV hotline) that route by ZIP
- Federal programs (SNAP, WIC, HUD) with public directory URLs
- CDC/HHS-endorsed navigators

The `find_sdoh_resources` tool tries a configured external API first
(MAMAGUARD_SDOH_API_URL) and falls back to this map when the API is
down, missing, or unconfigured -- so the SDOH agent is always actionable.

Keyed by normalized category. Category inference also accepts ICD-10
Z-codes (Z55-Z65) and common SNOMED SDOH codes.
"""

from __future__ import annotations

# Z-code → category. Covers ICD-10 Z55-Z65 sub-ranges used by
# Gravity Project / USCDI v3 SDOH terminology bindings.
_Z_CODE_TO_CATEGORY: dict[str, str] = {
    # Housing
    "Z59.0": "housing",   # Homelessness
    "Z59.00": "housing",  # Homelessness, unspecified
    "Z59.01": "housing",  # Sheltered homelessness
    "Z59.02": "housing",  # Unsheltered homelessness
    "Z59.1": "housing",   # Inadequate housing
    "Z59.10": "housing",
    "Z59.11": "housing",  # Inadequate housing environmental temperature
    "Z59.12": "housing",  # Inadequate housing utilities
    "Z59.19": "housing",
    "Z59.2": "housing",   # Discord with neighbors/landlord
    # Food / economic
    "Z59.41": "food",     # Food insecurity
    "Z59.48": "food",     # Other specified lack of adequate food
    "Z59.4": "food",
    "Z59.5": "economic",  # Extreme poverty
    "Z59.6": "economic",  # Low income
    "Z59.7": "economic",  # Insufficient social insurance
    "Z59.8": "economic",
    "Z59.86": "utilities", # Financial insecurity re: utilities
    "Z59.87": "transportation", # Material hardship - transportation
    # Education / employment
    "Z55": "education",
    "Z56": "employment",
    "Z56.0": "employment",
    "Z56.9": "employment",
    # Social / interpersonal
    "Z60.2": "social_support", # Problems related to living alone
    "Z60.4": "social_support", # Social exclusion and rejection
    "Z63.0": "social_support",
    "Z63.4": "social_support", # Disappearance/death of family member
    "Z65.4": "violence",       # Victim of crime / terrorism
    # Healthcare access
    "Z75.3": "healthcare_access",
    "Z75.4": "healthcare_access",
}

# Common SNOMED codes (from Gravity) → category. Conservative subset.
_SNOMED_TO_CATEGORY: dict[str, str] = {
    "32911000":  "housing",           # Homelessness (disorder)
    "105531004": "housing",           # Housing problem
    "160932005": "economic",          # Low income
    "422650009": "social_support",    # Social isolation
    "445281000124101": "food",        # Food insecurity
    "733423003": "food",              # Food insecurity (finding)
    "423315002": "interpreter",       # Limited access/limited English
    "266948004": "social_support",    # No family support
    "160903007": "employment",        # Full-time employment
    "160904001": "employment",        # Unemployed
    "73595000":  "mental_health",     # Stress
}

# Category → curated resource list.
# Each resource must have: name, contact, description, url (optional), category.
_RESOURCES: dict[str, list[dict[str, str]]] = {
    "housing": [
        {
            "name": "211 Helpline",
            "contact": "Dial 211",
            "url": "https://www.211.org",
            "description": (
                "Free, confidential 24/7 referral line (United Way). "
                "Connects callers to local emergency shelter, rental "
                "assistance, and housing navigators."
            ),
            "category": "housing",
        },
        {
            "name": "HUD Emergency Housing Voucher Locator",
            "contact": "1-800-569-4287",
            "url": "https://www.hud.gov/topics/rental_assistance",
            "description": (
                "HUD-funded rental assistance and emergency housing "
                "vouchers; search by ZIP for local Public Housing "
                "Agencies."
            ),
            "category": "housing",
        },
        {
            "name": "National Domestic Violence Hotline (safe housing)",
            "contact": "1-800-799-7233",
            "url": "https://www.thehotline.org",
            "description": (
                "Safe-housing referrals for survivors of intimate "
                "partner violence; covers emergency shelter placement."
            ),
            "category": "housing",
        },
    ],
    "food": [
        {
            "name": "WIC (Women, Infants, and Children)",
            "contact": "1-800-942-3678",
            "url": "https://www.fns.usda.gov/wic",
            "description": (
                "USDA nutrition program for pregnant and postpartum "
                "parents and children under 5. Food benefits + "
                "nutrition counseling + breastfeeding support."
            ),
            "category": "food",
        },
        {
            "name": "SNAP (Supplemental Nutrition Assistance Program)",
            "contact": "1-800-221-5689",
            "url": "https://www.fns.usda.gov/snap/state-directory",
            "description": (
                "Federal food assistance; apply through state agency. "
                "Most pregnant and postpartum parents qualify."
            ),
            "category": "food",
        },
        {
            "name": "Feeding America Food Bank Locator",
            "contact": "Dial 211",
            "url": "https://www.feedingamerica.org/find-your-local-foodbank",
            "description": (
                "Search by ZIP for the nearest food bank; most offer "
                "walk-in food pantry hours and home delivery for "
                "homebound clients."
            ),
            "category": "food",
        },
    ],
    "transportation": [
        {
            "name": "Medicaid Non-Emergency Medical Transport",
            "contact": "State Medicaid office",
            "url": "https://www.medicaid.gov/medicaid/benefits/transportation/index.html",
            "description": (
                "Federally required Medicaid benefit. Covers rides to "
                "and from medical appointments; call state Medicaid "
                "office to schedule."
            ),
            "category": "transportation",
        },
        {
            "name": "211 Transportation Referrals",
            "contact": "Dial 211",
            "url": "https://www.211.org",
            "description": (
                "Local ride-share and medical transport referrals; "
                "includes volunteer driver networks."
            ),
            "category": "transportation",
        },
    ],
    "economic": [
        {
            "name": "211 Financial Assistance",
            "contact": "Dial 211",
            "url": "https://www.211.org",
            "description": (
                "Routes callers to local financial assistance, "
                "emergency cash aid, and benefits enrollment help."
            ),
            "category": "economic",
        },
        {
            "name": "Benefits.gov Screener",
            "contact": "benefits.gov",
            "url": "https://www.benefits.gov",
            "description": (
                "Federal benefits eligibility screener covering 1,000+ "
                "programs including TANF, SNAP, Medicaid, housing."
            ),
            "category": "economic",
        },
    ],
    "utilities": [
        {
            "name": "LIHEAP (Low Income Home Energy Assistance)",
            "contact": "1-866-674-6327",
            "url": "https://www.acf.hhs.gov/ocs/programs/liheap",
            "description": (
                "Federal energy bill assistance; covers heating, "
                "cooling, and weatherization. Search by state."
            ),
            "category": "utilities",
        },
    ],
    "employment": [
        {
            "name": "CareerOneStop",
            "contact": "1-877-872-5627",
            "url": "https://www.careeronestop.org",
            "description": (
                "US Department of Labor job-search, training, and "
                "unemployment benefit navigator."
            ),
            "category": "employment",
        },
    ],
    "education": [
        {
            "name": "Adult Education and Literacy (OCTAE)",
            "contact": "1-800-872-5327",
            "url": "https://www.ed.gov/about/offices/list/ovae/pi/AdultEd",
            "description": (
                "Federal directory for adult literacy, ESL, and GED "
                "programs."
            ),
            "category": "education",
        },
    ],
    "social_support": [
        {
            "name": "211 Community Support",
            "contact": "Dial 211",
            "url": "https://www.211.org",
            "description": (
                "Local peer-support groups, faith-based services, and "
                "community health workers."
            ),
            "category": "social_support",
        },
    ],
    "violence": [
        {
            "name": "National Domestic Violence Hotline",
            "contact": "1-800-799-7233",
            "url": "https://www.thehotline.org",
            "description": (
                "24/7 confidential safety planning and shelter "
                "referrals."
            ),
            "category": "violence",
        },
    ],
    "mental_health": [
        {
            "name": "988 Suicide & Crisis Lifeline",
            "contact": "Dial 988",
            "url": "https://988lifeline.org",
            "description": (
                "24/7 free, confidential crisis counseling and "
                "referral to local mental-health resources."
            ),
            "category": "mental_health",
        },
        {
            "name": "Postpartum Support International Helpline",
            "contact": "1-800-944-4773",
            "url": "https://www.postpartum.net",
            "description": (
                "Specialized hotline for perinatal mood and anxiety "
                "disorders; connects to local provider directory."
            ),
            "category": "mental_health",
        },
    ],
    "interpreter": [
        {
            "name": "Language Line Solutions",
            "contact": "1-800-752-6096",
            "url": "https://www.languageline.com",
            "description": (
                "On-demand phone interpretation in 240+ languages; "
                "many hospitals and clinics contract directly."
            ),
            "category": "interpreter",
        },
    ],
    "healthcare_access": [
        {
            "name": "HRSA Health Center Finder",
            "contact": "1-877-464-4772",
            "url": "https://findahealthcenter.hrsa.gov",
            "description": (
                "Locator for federally qualified health centers "
                "(FQHCs) offering sliding-scale maternal and pediatric "
                "care regardless of insurance."
            ),
            "category": "healthcare_access",
        },
        {
            "name": "Medicaid / CHIP Enrollment",
            "contact": "1-877-543-7669",
            "url": "https://www.insurekidsnow.gov",
            "description": (
                "Routes callers to state Medicaid and CHIP "
                "enrollment; many states offer 12-month postpartum "
                "coverage extensions."
            ),
            "category": "healthcare_access",
        },
    ],
}


def classify_category(code_or_text: str) -> str | None:
    """
    Normalize an ICD-10 Z-code, SNOMED code, or free-text phrase into
    one of our resource categories. Returns None if nothing plausible
    matches -- caller should fall back to the generic "211" bucket.
    """
    if not code_or_text:
        return None
    raw = code_or_text.strip()

    # Exact Z-code or prefix (Z59.0 → housing, Z59.01 → housing, Z59 → housing)
    upper = raw.upper()
    if upper in _Z_CODE_TO_CATEGORY:
        return _Z_CODE_TO_CATEGORY[upper]
    # Walk Z-code prefixes: "Z59.01" → "Z59.0" → "Z59"
    if upper.startswith("Z") and "." in upper:
        head = upper.rsplit(".", 1)[0]
        if head in _Z_CODE_TO_CATEGORY:
            return _Z_CODE_TO_CATEGORY[head]
    if upper in _Z_CODE_TO_CATEGORY:
        return _Z_CODE_TO_CATEGORY[upper]

    # SNOMED numeric code
    if raw.isdigit() and raw in _SNOMED_TO_CATEGORY:
        return _SNOMED_TO_CATEGORY[raw]

    # Free text keyword match (case-insensitive)
    low = raw.lower()
    keyword_map = [
        ("housing",          ["housing", "homeless", "shelter", "eviction", "rent"]),
        ("food",             ["food", "hunger", "nutrition", "wic", "snap"]),
        ("transportation",   ["transport", "ride", "bus", "car"]),
        ("utilities",        ["utilit", "electric", "heat", "gas bill", "water bill"]),
        ("economic",         ["poverty", "income", "finance", "money", "benefit"]),
        ("employment",       ["unemploy", "job", "work"]),
        ("education",        ["literacy", "education", "esl", "ged"]),
        ("social_support",   ["isolat", "lonely", "family", "social"]),
        ("violence",         ["violence", "abuse", "domestic", "assault"]),
        ("mental_health",    ["depress", "anxiety", "suicid", "stress", "mental"]),
        ("interpreter",      ["language", "english", "interpret", "translat"]),
        ("healthcare_access",["insurance", "uninsured", "medicaid", "chip", "coverage"]),
    ]
    for cat, kws in keyword_map:
        if any(kw in low for kw in kws):
            return cat
    return None


def curated_resources(category: str) -> list[dict[str, str]]:
    """
    Return the curated offline resource list for `category`.
    Unknown category → empty list (caller should fall back to 211).
    """
    return list(_RESOURCES.get(category, []))


def all_categories() -> list[str]:
    return sorted(_RESOURCES.keys())


# Universal fallback: a bare 211 entry used when classification fails
# but we still want to hand the user something actionable.
GENERIC_211 = {
    "name": "211 Helpline",
    "contact": "Dial 211",
    "url": "https://www.211.org",
    "description": (
        "Free, confidential 24/7 information and referral line. "
        "Covers housing, food, utilities, transportation, childcare, "
        "mental health, and benefit enrollment across all 50 states."
    ),
    "category": "general",
}
