from __future__ import annotations

import unittest

from app.domain.numeric_parser import parse_mechanical_properties, parse_numeric


class ThousandsPromotionTests(unittest.TestCase):
    def test_dot_thousands_separator_promoted_for_yield(self):
        """Core Phase 1 bug: '1.097' MPa must resolve to 1097, not 1.097."""

        parsed = parse_numeric("1.097", kind="yield_mpa")
        self.assertEqual(parsed.value, 1097.0)
        self.assertFalse(parsed.uncertain)
        self.assertTrue(parsed.promoted_thousands)

    def test_float_below_band_is_promoted_thousands(self):
        parsed = parse_numeric(1.097, kind="yield_mpa")
        self.assertEqual(parsed.value, 1097.0)
        self.assertTrue(parsed.promoted_thousands)

    def test_tensile_promotion(self):
        parsed = parse_numeric("1.250", kind="tensile_mpa")
        self.assertEqual(parsed.value, 1250.0)
        self.assertTrue(parsed.promoted_thousands)


class LocaleTests(unittest.TestCase):
    def test_comma_decimal_locale_stays_as_decimal(self):
        """With explicit comma-decimal locale, '1,097' is a literal 1.097."""

        parsed = parse_numeric("1,097", kind="yield_mpa", locale="comma_decimal")
        self.assertAlmostEqual(parsed.value, 1.097)
        # Below plausible band -> uncertain
        self.assertTrue(parsed.uncertain)

    def test_auto_locale_resolves_to_thousands_when_possible(self):
        parsed = parse_numeric("1,097", kind="yield_mpa")
        # Auto locale picks the only plausible interpretation.
        self.assertEqual(parsed.value, 1097.0)
        self.assertTrue(parsed.promoted_thousands)

    def test_elongation_comma_decimal(self):
        parsed = parse_numeric("26,5%", kind="elongation_pct")
        self.assertAlmostEqual(parsed.value, 26.5)
        self.assertFalse(parsed.uncertain)

    def test_elongation_dot_decimal(self):
        parsed = parse_numeric("26.5%", kind="elongation_pct")
        self.assertAlmostEqual(parsed.value, 26.5)
        self.assertFalse(parsed.uncertain)


class AmbiguousTests(unittest.TestCase):
    def test_short_number_stays_decimal_and_not_uncertain(self):
        parsed = parse_numeric("1.1", kind="elongation_pct")
        self.assertAlmostEqual(parsed.value, 1.1)
        self.assertFalse(parsed.uncertain)

    def test_three_digit_fractional_in_elongation_is_uncertain(self):
        # Only decimal interpretation is plausible (1097% would be absurd),
        # but the supplier formatting pattern is suspicious -> uncertain.
        parsed = parse_numeric("1.097", kind="elongation_pct")
        self.assertAlmostEqual(parsed.value, 1.097)
        self.assertTrue(parsed.uncertain)

    def test_plain_integer_passthrough(self):
        parsed = parse_numeric("355", kind="yield_mpa")
        self.assertEqual(parsed.value, 355.0)
        self.assertFalse(parsed.uncertain)

    def test_float_in_band_is_kept_as_is(self):
        parsed = parse_numeric(355.0, kind="yield_mpa")
        self.assertEqual(parsed.value, 355.0)
        self.assertFalse(parsed.promoted_thousands)
        self.assertFalse(parsed.uncertain)

    def test_non_digits_string_returns_none_uncertain(self):
        parsed = parse_numeric("n/a", kind="yield_mpa")
        self.assertIsNone(parsed.value)
        self.assertTrue(parsed.uncertain)


class ParseMechanicalPropertiesTests(unittest.TestCase):
    def test_end_to_end_mechanical_parsing(self):
        payload = {
            "yield_strength_mpa": "1.097",
            "tensile_strength_mpa": 520.0,
            "elongation_percentage": "26,5",
        }
        values, trace = parse_mechanical_properties(payload)
        self.assertEqual(values["yield_strength_mpa"], 1097.0)
        self.assertEqual(values["tensile_strength_mpa"], 520.0)
        self.assertAlmostEqual(values["elongation_percentage"], 26.5)
        self.assertTrue(trace["yield_strength_mpa"].promoted_thousands)
        self.assertFalse(trace["tensile_strength_mpa"].uncertain)

    def test_none_payload(self):
        values, trace = parse_mechanical_properties(None)
        self.assertEqual(values["yield_strength_mpa"], None)
        self.assertEqual(trace, {})


if __name__ == "__main__":
    unittest.main()
