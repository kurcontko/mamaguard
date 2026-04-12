"""
Dedicated unit tests for mamaguard.shared.sdoh_resources.

Pins the Z-code → category mapping, SNOMED → category mapping,
keyword classification, prefix-walking algorithm, curated resource
shape, and the GENERIC_211 fallback.
"""

import unittest

from mamaguard.shared.sdoh_resources import (
    GENERIC_211,
    all_categories,
    classify_category,
    curated_resources,
)


class TestClassifyCategoryZCodes(unittest.TestCase):
    """Z-code → category classification."""

    # -- Housing Z59.0x / Z59.1x / Z59.2 --

    def test_z59_0_homelessness(self):
        self.assertEqual(classify_category("Z59.0"), "housing")

    def test_z59_00_homelessness_unspecified(self):
        self.assertEqual(classify_category("Z59.00"), "housing")

    def test_z59_01_sheltered(self):
        self.assertEqual(classify_category("Z59.01"), "housing")

    def test_z59_02_unsheltered(self):
        self.assertEqual(classify_category("Z59.02"), "housing")

    def test_z59_1_inadequate_housing(self):
        self.assertEqual(classify_category("Z59.1"), "housing")

    def test_z59_10(self):
        self.assertEqual(classify_category("Z59.10"), "housing")

    def test_z59_11_temperature(self):
        self.assertEqual(classify_category("Z59.11"), "housing")

    def test_z59_12_utilities(self):
        self.assertEqual(classify_category("Z59.12"), "housing")

    def test_z59_19(self):
        self.assertEqual(classify_category("Z59.19"), "housing")

    def test_z59_2_discord(self):
        self.assertEqual(classify_category("Z59.2"), "housing")

    # -- Food Z59.4x --

    def test_z59_4_food(self):
        self.assertEqual(classify_category("Z59.4"), "food")

    def test_z59_41_food_insecurity(self):
        self.assertEqual(classify_category("Z59.41"), "food")

    def test_z59_48_lack_of_food(self):
        self.assertEqual(classify_category("Z59.48"), "food")

    # -- Economic Z59.5-Z59.8 --

    def test_z59_5_extreme_poverty(self):
        self.assertEqual(classify_category("Z59.5"), "economic")

    def test_z59_6_low_income(self):
        self.assertEqual(classify_category("Z59.6"), "economic")

    def test_z59_7_insufficient_insurance(self):
        self.assertEqual(classify_category("Z59.7"), "economic")

    def test_z59_8_economic(self):
        self.assertEqual(classify_category("Z59.8"), "economic")

    # -- Utilities / transportation --

    def test_z59_86_utilities(self):
        self.assertEqual(classify_category("Z59.86"), "utilities")

    def test_z59_87_transportation(self):
        self.assertEqual(classify_category("Z59.87"), "transportation")

    # -- Education / Employment --

    def test_z55_education(self):
        self.assertEqual(classify_category("Z55"), "education")

    def test_z56_employment(self):
        self.assertEqual(classify_category("Z56"), "employment")

    def test_z56_0_employment(self):
        self.assertEqual(classify_category("Z56.0"), "employment")

    def test_z56_9_employment(self):
        self.assertEqual(classify_category("Z56.9"), "employment")

    # -- Social / interpersonal --

    def test_z60_2_living_alone(self):
        self.assertEqual(classify_category("Z60.2"), "social_support")

    def test_z60_4_social_exclusion(self):
        self.assertEqual(classify_category("Z60.4"), "social_support")

    def test_z63_0(self):
        self.assertEqual(classify_category("Z63.0"), "social_support")

    def test_z63_4_family_death(self):
        self.assertEqual(classify_category("Z63.4"), "social_support")

    def test_z65_4_violence(self):
        self.assertEqual(classify_category("Z65.4"), "violence")

    # -- Healthcare access --

    def test_z75_3_healthcare_access(self):
        self.assertEqual(classify_category("Z75.3"), "healthcare_access")

    def test_z75_4_healthcare_access(self):
        self.assertEqual(classify_category("Z75.4"), "healthcare_access")


class TestClassifyCategoryZCodePrefixWalking(unittest.TestCase):
    """Prefix-walking: Z59.01 → Z59.0 when Z59.01 is in the table,
    and unknown sub-codes fall back to parent prefix."""

    def test_walks_one_dot_level(self):
        # Z56.5 not in table; walk strips ".5" → Z56 which IS in table → employment
        self.assertEqual(classify_category("Z56.5"), "employment")

    def test_walk_does_not_find_intermediate(self):
        # Z59.13: walk strips ".13" → Z59, which is NOT in table → None
        # (The walk does NOT go Z59.13 → Z59.1; it strips the full last segment)
        self.assertIsNone(classify_category("Z59.13"))

    def test_z59_49_walk_to_z59_gives_none(self):
        # Z59.49 → Z59 (not in table) → None
        self.assertIsNone(classify_category("Z59.49"))

    def test_z59_88_walk_to_z59_gives_none(self):
        # Z59.88 �� Z59 (not in table) → None
        self.assertIsNone(classify_category("Z59.88"))

    def test_no_prefix_match_returns_none(self):
        # Z99.9 — neither exact nor any prefix is in the table
        self.assertIsNone(classify_category("Z99.9"))

    def test_z_without_dot_no_prefix_walk(self):
        # Z99 — no dot, no prefix walking, not in table → None
        self.assertIsNone(classify_category("Z99"))


class TestClassifyCategoryCaseInsensitive(unittest.TestCase):
    """Z-codes should match regardless of case."""

    def test_lowercase_z_code(self):
        self.assertEqual(classify_category("z59.0"), "housing")

    def test_mixed_case(self):
        self.assertEqual(classify_category("z59.41"), "food")

    def test_lowercase_with_spaces(self):
        self.assertEqual(classify_category("  z59.0  "), "housing")


class TestClassifyCategorySNOMED(unittest.TestCase):
    """SNOMED code → category classification."""

    def test_homelessness_disorder(self):
        self.assertEqual(classify_category("32911000"), "housing")

    def test_housing_problem(self):
        self.assertEqual(classify_category("105531004"), "housing")

    def test_low_income(self):
        self.assertEqual(classify_category("160932005"), "economic")

    def test_social_isolation(self):
        self.assertEqual(classify_category("422650009"), "social_support")

    def test_food_insecurity_445(self):
        self.assertEqual(classify_category("445281000124101"), "food")

    def test_food_insecurity_733(self):
        self.assertEqual(classify_category("733423003"), "food")

    def test_limited_english(self):
        self.assertEqual(classify_category("423315002"), "interpreter")

    def test_no_family_support(self):
        self.assertEqual(classify_category("266948004"), "social_support")

    def test_full_time_employment(self):
        self.assertEqual(classify_category("160903007"), "employment")

    def test_unemployed(self):
        self.assertEqual(classify_category("160904001"), "employment")

    def test_stress(self):
        self.assertEqual(classify_category("73595000"), "mental_health")

    def test_unknown_snomed_returns_none(self):
        self.assertIsNone(classify_category("999999999"))

    def test_snomed_must_be_all_digits(self):
        # "32911000x" is not all digits → falls through to keyword
        self.assertIsNone(classify_category("32911000x"))


class TestClassifyCategoryKeywords(unittest.TestCase):
    """Free-text keyword → category classification."""

    # One representative test per keyword category

    def test_housing_keyword(self):
        self.assertEqual(classify_category("patient is homeless"), "housing")

    def test_shelter_keyword(self):
        self.assertEqual(classify_category("needs emergency shelter"), "housing")

    def test_eviction_keyword(self):
        self.assertEqual(classify_category("facing eviction"), "housing")

    def test_food_keyword(self):
        self.assertEqual(classify_category("food insecurity"), "food")

    def test_hunger_keyword(self):
        self.assertEqual(classify_category("reports hunger"), "food")

    def test_wic_keyword(self):
        self.assertEqual(classify_category("eligible for WIC"), "food")

    def test_transportation_keyword(self):
        self.assertEqual(classify_category("no transportation to clinic"), "transportation")

    def test_ride_keyword(self):
        self.assertEqual(classify_category("needs a ride"), "transportation")

    def test_utilities_keyword(self):
        self.assertEqual(classify_category("utility bills overdue"), "utilities")

    def test_electric_keyword(self):
        self.assertEqual(classify_category("electric shut off notice"), "utilities")

    def test_economic_poverty(self):
        self.assertEqual(classify_category("living in poverty"), "economic")

    def test_economic_income(self):
        self.assertEqual(classify_category("low income household"), "economic")

    def test_employment_keyword(self):
        self.assertEqual(classify_category("recently unemployed"), "employment")

    def test_job_keyword(self):
        self.assertEqual(classify_category("looking for a job"), "employment")

    def test_education_keyword(self):
        self.assertEqual(classify_category("needs literacy support"), "education")

    def test_esl_keyword(self):
        self.assertEqual(classify_category("enrolled in ESL classes"), "education")

    def test_social_support_isolated(self):
        self.assertEqual(classify_category("socially isolated"), "social_support")

    def test_social_support_lonely(self):
        self.assertEqual(classify_category("feels lonely"), "social_support")

    def test_violence_keyword(self):
        self.assertEqual(classify_category("domestic violence concern"), "violence")

    def test_assault_keyword(self):
        self.assertEqual(classify_category("reports assault"), "violence")

    def test_abuse_substring_collision(self):
        # "abuse" contains "bus" → matches transportation first (substring matching)
        self.assertEqual(classify_category("reports abuse"), "transportation")

    def test_mental_health_depression(self):
        self.assertEqual(classify_category("signs of depression"), "mental_health")

    def test_mental_health_anxiety(self):
        self.assertEqual(classify_category("experiencing anxiety"), "mental_health")

    def test_mental_health_stress(self):
        self.assertEqual(classify_category("high stress levels"), "mental_health")

    def test_interpreter_language(self):
        self.assertEqual(classify_category("language barrier"), "interpreter")

    def test_interpreter_english(self):
        self.assertEqual(classify_category("limited english proficiency"), "interpreter")

    def test_healthcare_access_uninsured(self):
        self.assertEqual(classify_category("patient is uninsured"), "healthcare_access")

    def test_healthcare_access_medicaid(self):
        self.assertEqual(classify_category("needs medicaid enrollment"), "healthcare_access")

    def test_healthcare_access_coverage(self):
        self.assertEqual(classify_category("no coverage"), "healthcare_access")

    def test_keyword_priority_first_match_wins(self):
        # "housing" keyword appears first in the keyword_map
        result = classify_category("housing and food")
        self.assertEqual(result, "housing")


class TestClassifyCategoryEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_empty_string(self):
        self.assertIsNone(classify_category(""))

    def test_whitespace_only(self):
        # After strip(), becomes empty → falsy → None
        self.assertIsNone(classify_category("   "))

    def test_unrecognized_text(self):
        self.assertIsNone(classify_category("random unrelated text"))

    def test_z_code_with_leading_trailing_spaces(self):
        self.assertEqual(classify_category("  Z59.0  "), "housing")

    def test_snomed_with_leading_trailing_spaces(self):
        # strip() removes spaces, then "32911000" is all digits + in table
        self.assertEqual(classify_category("  32911000  "), "housing")


class TestCuratedResources(unittest.TestCase):
    """curated_resources() output shape and contract."""

    def test_known_category_returns_nonempty_list(self):
        for cat in all_categories():
            with self.subTest(category=cat):
                res = curated_resources(cat)
                self.assertIsInstance(res, list)
                self.assertGreater(len(res), 0, f"Category '{cat}' has no resources")

    def test_unknown_category_returns_empty_list(self):
        self.assertEqual(curated_resources("nonexistent_category"), [])

    def test_resource_shape(self):
        """Every resource has name, contact, description, category."""
        required_keys = {"name", "contact", "description", "category"}
        for cat in all_categories():
            for res in curated_resources(cat):
                with self.subTest(category=cat, resource=res["name"]):
                    self.assertTrue(
                        required_keys.issubset(res.keys()),
                        f"Missing keys: {required_keys - res.keys()}",
                    )

    def test_returns_copy_not_reference(self):
        """Mutating the returned list must not affect the internal data."""
        original = curated_resources("housing")
        original.append({"name": "injected"})
        fresh = curated_resources("housing")
        names = [r["name"] for r in fresh]
        self.assertNotIn("injected", names)

    def test_housing_has_211(self):
        names = [r["name"] for r in curated_resources("housing")]
        self.assertIn("211 Helpline", names)

    def test_food_has_wic_and_snap(self):
        names = [r["name"] for r in curated_resources("food")]
        self.assertIn("WIC (Women, Infants, and Children)", names)
        self.assertIn("SNAP (Supplemental Nutrition Assistance Program)", names)

    def test_mental_health_has_988_and_psi(self):
        names = [r["name"] for r in curated_resources("mental_health")]
        self.assertIn("988 Suicide & Crisis Lifeline", names)
        self.assertIn("Postpartum Support International Helpline", names)

    def test_healthcare_access_has_hrsa_and_medicaid(self):
        names = [r["name"] for r in curated_resources("healthcare_access")]
        self.assertIn("HRSA Health Center Finder", names)
        self.assertIn("Medicaid / CHIP Enrollment", names)


class TestAllCategories(unittest.TestCase):

    def test_returns_sorted_list(self):
        cats = all_categories()
        self.assertEqual(cats, sorted(cats))

    def test_contains_expected_categories(self):
        cats = set(all_categories())
        expected = {
            "housing", "food", "transportation", "economic", "utilities",
            "employment", "education", "social_support", "violence",
            "mental_health", "interpreter", "healthcare_access",
        }
        self.assertEqual(cats, expected)

    def test_count(self):
        self.assertEqual(len(all_categories()), 12)


class TestGeneric211(unittest.TestCase):

    def test_shape(self):
        self.assertIn("name", GENERIC_211)
        self.assertIn("contact", GENERIC_211)
        self.assertIn("url", GENERIC_211)
        self.assertIn("description", GENERIC_211)
        self.assertIn("category", GENERIC_211)

    def test_category_is_general(self):
        self.assertEqual(GENERIC_211["category"], "general")

    def test_contact_is_211(self):
        self.assertEqual(GENERIC_211["contact"], "Dial 211")

    def test_url(self):
        self.assertEqual(GENERIC_211["url"], "https://www.211.org")


if __name__ == "__main__":
    unittest.main()
