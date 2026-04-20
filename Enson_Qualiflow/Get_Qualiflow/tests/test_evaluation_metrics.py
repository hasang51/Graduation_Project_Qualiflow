from __future__ import annotations

import unittest

from scripts.evaluate_outputs import (
    aggregate_metrics,
    compare_field,
    evaluate_document,
    predicted_fields_from_extraction,
)


def _make_extraction(
    *,
    heat_numbers,
    grades,
    yields,
    tensiles,
    elongs,
    is_compliant=True,
    supplier="ACME Steel",
    document_type="Mill Test Certificate",
    needs_review=False,
):
    items = []
    for heat, grade, y, t, e in zip(heat_numbers, grades, yields, tensiles, elongs):
        items.append(
            {
                "heat_number": heat,
                "grade": grade,
                "mechanical_properties": {
                    "yield_strength_mpa": y,
                    "tensile_strength_mpa": t,
                    "elongation_percentage": e,
                },
            }
        )
    return {
        "supplier_name": supplier,
        "document_type": document_type,
        "certificate_date": "2024-01-01",
        "is_compliant": is_compliant,
        "items": items,
        "needs_review": needs_review,
    }


class CompareFieldTests(unittest.TestCase):
    def test_simple_string_case_insensitive(self):
        comp = compare_field("supplier_name", "ACME Steel", "acme   steel")
        self.assertTrue(comp.equal)

    def test_list_string_sorted_and_deduped(self):
        comp = compare_field("heat_numbers", ["H1", "H2"], "H2|H1")
        self.assertTrue(comp.equal)

    def test_list_numeric_tolerance(self):
        comp = compare_field("yield_strength_mpa", [380.0, 400.0], "400|380.5")
        self.assertTrue(comp.equal)

    def test_list_numeric_mismatch_beyond_tolerance(self):
        comp = compare_field("yield_strength_mpa", [380.0, 400.0], [370.0, 400.0])
        self.assertFalse(comp.equal)


class EvaluateDocumentTests(unittest.TestCase):
    def test_perfect_match(self):
        extraction = _make_extraction(
            heat_numbers=["H1", "H2"],
            grades=["S355J2", "S355J2"],
            yields=[380.0, 390.0],
            tensiles=[500.0, 510.0],
            elongs=[25.0, 24.0],
        )
        per_doc = {"document_id": "d1", "filename": "a.pdf", "latency_ms": 1200.0, "extraction": extraction, "mode": "D", "route_used": "rendered_multimodal"}
        gold = {
            "document_id": "d1",
            "filename": "a.pdf",
            "supplier_name": "ACME Steel",
            "document_type": "Mill Test Certificate",
            "certificate_date": "2024-01-01",
            "is_compliant": True,
            "heat_numbers": ["H1", "H2"],
            "grades": ["S355J2"],
            "yield_strength_mpa": ["380", "390"],
            "tensile_strength_mpa": [500.0, 510.0],
            "elongation_percentage": [25.0, 24.0],
        }
        ev = evaluate_document(gold_record=gold, per_document=per_doc)
        # Most fields match (grades may mismatch since gold is de-duped, predicted isn't)
        self.assertGreaterEqual(ev.field_hits, ev.field_total - 1)
        self.assertEqual(ev.compliance_correct, True)
        self.assertAlmostEqual(ev.completeness, 1.0)

    def test_partial_match(self):
        extraction = _make_extraction(
            heat_numbers=["H1"],
            grades=["S355J2"],
            yields=[380.0],
            tensiles=[500.0],
            elongs=[25.0],
            is_compliant=False,
        )
        per_doc = {"document_id": "d2", "filename": "b.pdf", "extraction": extraction, "mode": "D", "route_used": "rendered_multimodal"}
        gold = {
            "document_id": "d2",
            "filename": "b.pdf",
            "supplier_name": "Other Supplier",
            "document_type": "CoA",
            "certificate_date": "2024-02-02",
            "is_compliant": True,
            "heat_numbers": ["H1"],
            "grades": ["S355J2"],
            "yield_strength_mpa": [380.0],
            "tensile_strength_mpa": [500.0],
            "elongation_percentage": [25.0],
        }
        ev = evaluate_document(gold_record=gold, per_document=per_doc)
        self.assertEqual(ev.compliance_correct, False)
        self.assertLess(ev.field_hits, ev.field_total)

    def test_aggregate_metrics_toy_example(self):
        evs = [
            evaluate_document(
                gold_record={
                    "document_id": "d1",
                    "filename": "a.pdf",
                    "supplier_name": "ACME",
                    "document_type": "MTC",
                    "certificate_date": "2024-01-01",
                    "is_compliant": True,
                    "heat_numbers": ["H1"],
                    "grades": ["S355J2"],
                    "yield_strength_mpa": [380.0],
                    "tensile_strength_mpa": [500.0],
                    "elongation_percentage": [25.0],
                },
                per_document={
                    "document_id": "d1",
                    "filename": "a.pdf",
                    "latency_ms": 1000.0,
                    "extraction": _make_extraction(
                        heat_numbers=["H1"],
                        grades=["S355J2"],
                        yields=[380.0],
                        tensiles=[500.0],
                        elongs=[25.0],
                        is_compliant=True,
                        supplier="ACME",
                        document_type="MTC",
                        needs_review=False,
                    ),
                },
            ),
            evaluate_document(
                gold_record={
                    "document_id": "d2",
                    "filename": "b.pdf",
                    "supplier_name": "WrongCorp",
                    "document_type": "MTC",
                    "certificate_date": "2024-02-02",
                    "is_compliant": False,
                    "heat_numbers": ["H2"],
                    "grades": ["S235JR"],
                    "yield_strength_mpa": [250.0],
                    "tensile_strength_mpa": [400.0],
                    "elongation_percentage": [25.0],
                },
                per_document={
                    "document_id": "d2",
                    "filename": "b.pdf",
                    "latency_ms": 2000.0,
                    "extraction": _make_extraction(
                        heat_numbers=["H2"],
                        grades=["S235JR"],
                        yields=[250.0],
                        tensiles=[400.0],
                        elongs=[25.0],
                        is_compliant=True,
                        supplier="OtherCorp",
                        document_type="MTC",
                        needs_review=True,
                    ),
                },
            ),
        ]
        aggregate = aggregate_metrics(evs)
        self.assertEqual(aggregate["n"], 2)
        self.assertGreater(aggregate["field_accuracy"], 0.0)
        self.assertLessEqual(aggregate["field_accuracy"], 1.0)
        # First doc: compliance correct; second doc: wrong.
        self.assertAlmostEqual(aggregate["compliance_decision_accuracy"], 0.5, places=2)
        self.assertAlmostEqual(aggregate["review_rate"], 0.5, places=2)
        self.assertAlmostEqual(aggregate["stp_rate"], 0.5, places=2)
        self.assertEqual(aggregate["average_latency_ms"], 1500.0)
        # p95 uses nearest-rank interpolation => on two samples, equals max.
        self.assertEqual(aggregate["p95_latency_ms"], 2000.0)


class PredictedFieldsTests(unittest.TestCase):
    def test_predicted_fields_flatten_correctly(self):
        extraction = _make_extraction(
            heat_numbers=["H1", "H2"],
            grades=["A", "B"],
            yields=[100, 200],
            tensiles=[300, 400],
            elongs=[10, 20],
        )
        fields = predicted_fields_from_extraction(extraction)
        self.assertEqual(fields["heat_numbers"], ["H1", "H2"])
        self.assertEqual(fields["grades"], ["A", "B"])
        self.assertEqual(fields["yield_strength_mpa"], [100.0, 200.0])
        self.assertEqual(fields["tensile_strength_mpa"], [300.0, 400.0])
        self.assertEqual(fields["elongation_percentage"], [10.0, 20.0])


if __name__ == "__main__":
    unittest.main()
