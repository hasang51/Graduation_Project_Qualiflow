from __future__ import annotations

import unittest

from app.domain.outcome_taxonomy import aggregate_document_outcome


class OutcomeTaxonomyTests(unittest.TestCase):
    def test_unresolved_rows_not_non_compliant(self):
        outcome = aggregate_document_outcome(["UNRESOLVED_SPEC", "NOT_VALIDATED"])
        self.assertEqual(outcome, "NEEDS_REVIEW")

    def test_skipped_validation_not_non_compliant(self):
        outcome = aggregate_document_outcome(["NOT_VALIDATED"])
        self.assertEqual(outcome, "NOT_VALIDATED")

    def test_unsupported_family_not_non_compliant(self):
        outcome = aggregate_document_outcome(["UNSUPPORTED_SPEC_FAMILY"])
        self.assertEqual(outcome, "NEEDS_REVIEW")

    def test_explicit_unmapped_grade_not_non_compliant(self):
        outcome = aggregate_document_outcome(["EXPLICIT_UNMAPPED_GRADE"])
        self.assertEqual(outcome, "NEEDS_REVIEW")

    def test_missing_critical_field_grade_not_non_compliant(self):
        outcome = aggregate_document_outcome(["MISSING_CRITICAL_FIELD_GRADE"])
        self.assertEqual(outcome, "NEEDS_REVIEW")

    def test_true_violation_is_non_compliant(self):
        outcome = aggregate_document_outcome(["COMPLIANT", "NON_COMPLIANT"])
        self.assertEqual(outcome, "NON_COMPLIANT")


if __name__ == "__main__":
    unittest.main()
