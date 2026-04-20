from __future__ import annotations

import unittest

from app.domain.document_context import build_document_context, propagate_context_to_rows


class DocumentContextPropagationTests(unittest.TestCase):
    def test_strong_header_propagates_to_missing_row(self):
        rows = [{"grade": None, "heat_number": "H1"}]
        context = build_document_context(rows, metadata={"header_grade": "S355J2"})
        tokens = propagate_context_to_rows(rows, context)
        self.assertEqual(rows[0]["grade"], "S355J2")
        self.assertIn("context_propagation:grade_from_header", tokens)

    def test_existing_row_value_is_not_overwritten(self):
        rows = [{"grade": "S275JR", "heat_number": "H1"}]
        context = build_document_context(rows, metadata={"header_grade": "S355J2"})
        propagate_context_to_rows(rows, context)
        self.assertEqual(rows[0]["grade"], "S275JR")
        self.assertIn("header_row_conflict:grade:row0", context.conflicts)

    def test_cross_page_identifier_indexing(self):
        rows = [
            {"item_id": "A-10", "heat_number": "H1", "grade": None},
            {"item_id": "A-10", "heat_number": "H2", "grade": None},
        ]
        context = build_document_context(rows, metadata={"header_grade": "S355J2"})
        self.assertIn("A-10", context.identifier_index)
        self.assertEqual(context.identifier_index["A-10"]["rows"], [0, 1])


if __name__ == "__main__":
    unittest.main()
