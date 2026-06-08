from __future__ import annotations

import unittest

from app.services.ocr_service import (
    _parse_by_field,
    normalize_ocr_text,
    parse_grade,
    parse_heat_number,
    parse_item_id,
    parse_numeric_strength,
    parse_percentage,
    select_ocr_strategy,
)


class SelectOcrStrategyTests(unittest.TestCase):
    def test_numeric_fields_use_numeric_strategy(self):
        for field in ("yield_strength_mpa", "tensile_strength_mpa", "elongation_percentage"):
            with self.subTest(field=field):
                self.assertEqual(select_ocr_strategy(field), "numeric")

    def test_alphanumeric_fields_use_alphanumeric_strategy(self):
        for field in ("heat_number", "item_id", "grade", "weight_or_length"):
            with self.subTest(field=field):
                self.assertEqual(select_ocr_strategy(field), "alphanumeric")

    def test_unknown_field_falls_back(self):
        self.assertEqual(select_ocr_strategy("not_a_field"), "fallback")
        self.assertEqual(select_ocr_strategy(None), "fallback")


class NormalizeOcrTextNumericTests(unittest.TestCase):
    def test_decimal_comma_is_converted_to_dot(self):
        decision = normalize_ocr_text(
            canonical_field="yield_strength_mpa",
            raw_text="355,0",
            confidence=0.9,
        )
        self.assertEqual(decision.normalized_text, "355.0")
        self.assertTrue(decision.normalization_applied)
        self.assertTrue(
            any("decimal comma" in note for note in decision.normalization_notes)
        )

    def test_whitespace_is_stripped_in_numeric_field(self):
        decision = normalize_ocr_text(
            canonical_field="tensile_strength_mpa",
            raw_text="  470 ",
            confidence=0.95,
        )
        self.assertEqual(decision.normalized_text, "470")

    def test_high_confidence_confusion_repair(self):
        decision = normalize_ocr_text(
            canonical_field="yield_strength_mpa",
            raw_text="3SS",
            confidence=0.9,
        )
        self.assertEqual(decision.normalized_text, "355")

    def test_low_confidence_keeps_confusion_characters(self):
        decision = normalize_ocr_text(
            canonical_field="yield_strength_mpa",
            raw_text="3SS",
            confidence=0.4,
        )
        self.assertEqual(decision.normalized_text, "3SS")
        self.assertTrue(
            any("low confidence" in note for note in decision.normalization_notes)
        )


class NormalizeOcrTextAlphanumericTests(unittest.TestCase):
    def test_alphanumeric_text_is_uppercased(self):
        decision = normalize_ocr_text(
            canonical_field="heat_number",
            raw_text="s1200594",
            confidence=0.9,
        )
        self.assertEqual(decision.normalized_text, "S1200594")

    def test_alphanumeric_illegal_chars_are_stripped(self):
        decision = normalize_ocr_text(
            canonical_field="item_id",
            raw_text="IPE*100*&^",
            confidence=0.8,
        )
        self.assertEqual(decision.normalized_text, "IPE100")


class ParseHeatNumberTests(unittest.TestCase):
    def test_valid_heat_numbers(self):
        self.assertEqual(parse_heat_number("812003694", "812003694"), "812003694")
        self.assertEqual(parse_heat_number("S1200594", "S1200594"), "S1200594")

    def test_too_short_is_rejected(self):
        self.assertIsNone(parse_heat_number("A1", "A1"))

    def test_non_alphanumeric_is_rejected(self):
        self.assertIsNone(parse_heat_number("HN 42!", "HN 42!"))


class ParseItemIdTests(unittest.TestCase):
    def test_valid_item_id(self):
        self.assertEqual(parse_item_id("IPE-100", "IPE-100"), "IPE-100")

    def test_too_short_is_rejected(self):
        self.assertIsNone(parse_item_id("I1", "I1"))


class ParseGradeTests(unittest.TestCase):
    def test_valid_grade_with_plus(self):
        self.assertEqual(parse_grade("S355J2+N", "S355J2+N"), "S355J2+N")

    def test_too_short_is_rejected(self):
        self.assertIsNone(parse_grade("X", "X"))


class ParseNumericStrengthTests(unittest.TestCase):
    def test_integer_and_decimal_values(self):
        self.assertEqual(parse_numeric_strength("355", "355"), 355.0)
        self.assertEqual(parse_numeric_strength("355.5", "355.5"), 355.5)

    def test_value_above_upper_cap_is_rejected(self):
        self.assertIsNone(parse_numeric_strength("2500", "2500"))

    def test_zero_is_rejected(self):
        self.assertIsNone(parse_numeric_strength("0", "0"))

    def test_non_numeric_text_is_rejected(self):
        self.assertIsNone(parse_numeric_strength("abc", "abc"))


class ParsePercentageTests(unittest.TestCase):
    def test_valid_percentage(self):
        self.assertEqual(parse_percentage("25%", "25"), 25.0)
        self.assertEqual(parse_percentage("25.5%", "25.5"), 25.5)

    def test_percentage_above_100_is_rejected(self):
        self.assertIsNone(parse_percentage("150%", "150"))


class ParseByFieldTests(unittest.TestCase):
    def test_numeric_field_routes_to_strength_parser(self):
        result = _parse_by_field("yield_strength_mpa", "355", "355")
        self.assertFalse(result.unresolved)
        self.assertEqual(result.parsed_value, 355.0)

    def test_elongation_routes_to_percentage_parser(self):
        result = _parse_by_field("elongation_percentage", "25", "25")
        self.assertFalse(result.unresolved)
        self.assertEqual(result.parsed_value, 25.0)

    def test_heat_number_routes_to_heat_parser(self):
        result = _parse_by_field("heat_number", "812003694", "812003694")
        self.assertFalse(result.unresolved)
        self.assertEqual(result.parsed_value, "812003694")

    def test_unknown_field_is_unresolved(self):
        result = _parse_by_field("mystery_field", "abc", "abc")
        self.assertTrue(result.unresolved)
        self.assertIsNone(result.parsed_value)

    def test_weight_or_length_keeps_normalized_string(self):
        result = _parse_by_field("weight_or_length", "12000 KG", "12000 KG")
        self.assertFalse(result.unresolved)
        self.assertEqual(result.parsed_value, "12000 KG")


if __name__ == "__main__":
    unittest.main()
