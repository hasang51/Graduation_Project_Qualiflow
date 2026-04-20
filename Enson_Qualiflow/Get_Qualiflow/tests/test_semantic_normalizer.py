from __future__ import annotations

import unittest

from app.services.semantic_normalizer import normalize_rows_semantics


class SemanticNormalizationTests(unittest.TestCase):
    def test_field_synonym_heat_cast_schmelze_canonicalization(self):
        rows = [
            {"Heat No": "H-01", "Grade": "S355J2"},
            {"Cast No": "C-02", "Grade": "S355J2"},
            {"Schmelze No": "M-03", "Grade": "S355J2"},
        ]
        normalized = normalize_rows_semantics(rows)
        self.assertEqual(normalized[0].canonical_values["heat_number"], "H-01")
        self.assertEqual(normalized[1].canonical_values["heat_number"], "C-02")
        self.assertEqual(normalized[2].canonical_values["heat_number"], "M-03")

    def test_composite_grade_tokenization(self):
        rows = [{"grade": "304/304L 1.4301/1.4307"}]
        normalized = normalize_rows_semantics(rows)
        tokens = normalized[0].canonical_values["grade_tokens"]
        self.assertTrue(any("304" in token for token in tokens))
        self.assertTrue(any("1.4307" in token for token in tokens))

    def test_ambiguous_grade_is_marked(self):
        rows = [{"grade": "S355J2/304L"}]
        normalized = normalize_rows_semantics(rows)
        self.assertIn("grade", normalized[0].ambiguous_fields)
        self.assertTrue(normalized[0].grade_resolution.ambiguous)


if __name__ == "__main__":
    unittest.main()
