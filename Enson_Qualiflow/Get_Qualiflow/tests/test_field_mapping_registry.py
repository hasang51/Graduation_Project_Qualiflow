from __future__ import annotations

import unittest

from app.domain.field_mapping_registry import (
    CANONICAL_FIELDS,
    explain_mapping,
    normalize_header,
    resolve_canonical_field,
)


class NormalizeHeaderTests(unittest.TestCase):
    def test_lowercase_is_uppercased(self):
        self.assertEqual(normalize_header("heat no"), "HEAT NO")

    def test_turkish_characters_are_folded(self):
        self.assertEqual(normalize_header("DÖKÜM NO"), "DOKUM NO")

    def test_separators_are_collapsed(self):
        self.assertEqual(normalize_header(" heat/no :"), "HEAT NO")

    def test_rp02_variants_collapse_to_canonical_form(self):
        for text in ("RP 0.2", "RP 0,2", "RP0,2"):
            with self.subTest(text=text):
                self.assertEqual(normalize_header(text), "RP0.2")


class ResolveCanonicalFieldTests(unittest.TestCase):
    def test_canonical_name_is_resolvable(self):
        self.assertEqual(resolve_canonical_field("heat_number"), "heat_number")

    def test_english_synonym(self):
        self.assertEqual(resolve_canonical_field("HEAT NO"), "heat_number")

    def test_turkish_synonym_with_diacritics(self):
        self.assertEqual(resolve_canonical_field("DÖKÜM NO"), "heat_number")

    def test_yield_rp02_synonym(self):
        self.assertEqual(resolve_canonical_field("RP 0,2"), "yield_strength_mpa")

    def test_unknown_header_is_none(self):
        self.assertIsNone(resolve_canonical_field("NOT A FIELD"))

    def test_empty_string_is_none(self):
        self.assertIsNone(resolve_canonical_field(""))


class ExplainMappingTests(unittest.TestCase):
    def test_explanation_contains_canonical_target(self):
        result = explain_mapping("HEAT NO")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("matched_canonical_field"), "heat_number")
        self.assertEqual(result.get("matched_synonym"), "HEAT NO")

    def test_explanation_for_unresolved_header(self):
        result = explain_mapping("NOT A REAL HEADER")
        self.assertIsNone(result.get("matched_canonical_field"))
        self.assertEqual(result.get("confidence"), 0.0)


class CanonicalFieldsIntegrityTests(unittest.TestCase):
    def test_every_canonical_field_resolves_to_itself(self):
        for canonical_name in CANONICAL_FIELDS:
            with self.subTest(field=canonical_name):
                self.assertEqual(resolve_canonical_field(canonical_name), canonical_name)

    def test_every_declared_synonym_resolves_to_its_canonical_name(self):
        for canonical_name, definition in CANONICAL_FIELDS.items():
            for synonym in definition.supported_header_synonyms:
                with self.subTest(field=canonical_name, synonym=synonym):
                    self.assertEqual(resolve_canonical_field(synonym), canonical_name)


if __name__ == "__main__":
    unittest.main()
