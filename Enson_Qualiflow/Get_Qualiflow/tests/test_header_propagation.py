from __future__ import annotations

import unittest

from app.domain.header_propagation import apply_updates, propagate_to_rows


class HeaderPropagationBackfillTests(unittest.TestCase):
    def test_missing_row_grade_is_backfilled_from_header(self):
        rows = [
            {"grade": None, "heat_number": "H1"},
            {"grade": "", "heat_number": "H2"},
        ]
        result = propagate_to_rows(
            rows,
            metadata={"default_grade_hint": "S355J2"},
        )
        self.assertEqual(len(result.updates), 2)
        for update in result.updates:
            self.assertEqual(update.field, "grade")
            self.assertEqual(update.new_value, "S355J2")
            self.assertEqual(update.provenance, "header_propagated")

        apply_updates(rows, result)
        self.assertEqual(rows[0]["grade"], "S355J2")
        self.assertEqual(rows[0]["grade_provenance"], "header_propagated")

    def test_row_grade_is_never_overwritten(self):
        rows = [{"grade": "S275JR", "heat_number": "H1"}]
        result = propagate_to_rows(rows, metadata={"header_grade": "S355J2"})
        self.assertEqual(result.updates, [])

    def test_conflicting_row_and_header_grade_produces_conflict_token(self):
        rows = [{"grade": "S275JR", "heat_number": "H1"}]
        result = propagate_to_rows(rows, metadata={"header_grade": "S355J2"})
        self.assertIn("header_row_conflict:grade:row0", result.conflicts)

    def test_unknown_header_grade_does_not_propagate(self):
        rows = [{"grade": None, "heat_number": "H1"}]
        result = propagate_to_rows(rows, metadata={"header_grade": "MYSTERY-X"})
        self.assertEqual(result.updates, [])
        self.assertIsNotNone(result.header_grade_resolution)
        self.assertEqual(result.header_grade_resolution.status, "unknown")

    def test_no_header_is_a_noop(self):
        rows = [{"grade": None}]
        result = propagate_to_rows(rows, metadata=None, ai_remarks=None)
        self.assertEqual(result.updates, [])
        self.assertEqual(result.conflicts, [])


if __name__ == "__main__":
    unittest.main()
