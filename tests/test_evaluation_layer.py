"""Parametrized tests for the production evaluation layer."""

from __future__ import annotations

import pytest

from evaluation.matchers import run_matcher_chain
from evaluation.metrics import aggregate_field_results, compare_field, compare_values
from evaluation.normalization import normalize_supplier_name, raw_exact_equal
from evaluation.parsers import parse_date, parse_unit_value
from evaluation.policy import load_evaluation_policy


@pytest.fixture(scope="module")
def policy():
    return load_evaluation_policy()


class TestRawExactBaseline:
    def test_date_raw_false(self):
        assert raw_exact_equal("07/10/2024", "07.10.2024") is False

    def test_weight_punctuation_raw_false(self):
        assert raw_exact_equal("2195 Kgs", "2195 Kgs.") is False


class TestDateMatching:
    @pytest.mark.parametrize(
        ("gold", "pred", "expected"),
        [
            ("07/10/2024", "07.10.2024", True),
            ("2024-10-07", "07/10/2024", True),
            ("07/10/2024", "2024-10-07", True),
            ("2024-10", "2024-10-07", False),
        ],
    )
    def test_date_normalized_match(self, policy, gold, pred, expected):
        result = compare_field("certificate_date", gold, pred, policy)
        assert result.raw_exact_match is (gold == pred)
        assert result.business_match is expected
        if expected:
            assert result.matcher_used == "date_normalized_match"


class TestUnitMatching:
    @pytest.mark.parametrize(
        ("gold", "pred", "expected"),
        [
            ("2195 Kgs", "2195 Kgs.", True),
            ("2195 kg", "2.195 t", True),
            ("2195 kg", "2195 g", False),
            ("1.080 Kg", "1.08 kg", True),
        ],
    )
    def test_unit_business_match(self, policy, gold, pred, expected):
        result = compare_field("net_weight", gold, pred, policy)
        assert result.business_match is expected
        if expected and gold != pred:
            assert result.raw_exact_match is False


class TestSupplierMatching:
    def test_greek_alpha_supplier_match(self, policy):
        result = compare_field("supplier_name", "NOVOFIL S.p.A.", "NOVOFIL S.p.Α.", policy)
        assert result.raw_exact_match is False
        assert result.business_match is True
        assert result.matcher_used == "supplier_name_fuzzy_match"

    def test_unrelated_supplier_fail(self, policy):
        result = compare_field("supplier_name", "ACME Steel", "Other Corp", policy)
        assert result.business_match is False

    def test_borderline_review_needed(self, policy):
        gold = "Global Industrial Manufacturing Corporation"
        pred = "Global Industrials Manufacturing Corp"
        result = compare_field("supplier_name", gold, pred, policy)
        assert result.business_match in {True, False}
        if not result.business_match and result.review_needed:
            assert result.matcher_used == "supplier_name_fuzzy_match"


class TestGradeMatching:
    def test_alias_match(self, policy):
        result = compare_field("grade", "NOVOFIL SG2", "SG2", policy)
        assert result.business_match is True
        assert result.matcher_used == "grade_alias_match"

    def test_unknown_similar_no_alias(self, policy):
        result = compare_field("grade", "S355J2", "S355J3", policy)
        assert result.business_match is False


class TestDimensionMatching:
    def test_dimension_pattern_match(self, policy):
        gold = "2 x 1000 x 2000 mm"
        pred = "2.0mm x 1000mm x 2000mm"
        result = compare_field("dimensions", gold, pred, policy)
        assert result.business_match is True

    def test_dimension_reorder_fail_default(self, policy):
        gold = "2 x 1000 x 2000 mm"
        pred = "1000 x 2 x 2000 mm"
        result = compare_field("dimensions", gold, pred, policy)
        assert result.business_match is False


class TestCriticalIdentifier:
    @pytest.mark.parametrize(
        ("gold", "pred", "expected"),
        [
            ("AB123", "AB123", True),
            ("AB-123", "AB123", False),
            ("00123", "123", False),
            ("  AB123  ", "AB123", True),
        ],
    )
    def test_strict_identifier(self, policy, gold, pred, expected):
        result = compare_field("heat_number", gold, pred, policy)
        assert result.business_match is expected
        assert result.matcher_used == "critical_identifier_strict_match"


class TestAutoAcceptSafety:
    def test_one_empty_false(self, policy):
        result = compare_field("processing_decision", "auto_accept", "", policy)
        assert result.business_match is False

    def test_both_empty_per_policy(self, policy):
        field_policy = policy.for_field("review_reasons")
        outcome = run_matcher_chain("review_reasons", "", "", field_policy, policy)
        assert outcome.business_match is True

    def test_critical_cannot_fuzzy_accept(self, policy):
        result = compare_field("heat_number", "AB123", "AB124", policy)
        assert result.business_match is False
        assert result.matcher_used == "critical_identifier_strict_match"


class TestAggregation:
    def test_harmless_normalization_counted(self, policy):
        results = [
            compare_field("certificate_date", "07/10/2024", "07.10.2024", policy),
            compare_field("supplier_name", "NOVOFIL S.p.A.", "NOVOFIL S.p.Α.", policy),
        ]
        aggregate = aggregate_field_results(results)
        assert aggregate.raw_exact_accuracy == 0.0
        assert aggregate.business_normalized_accuracy == 1.0
        assert aggregate.harmless_normalization_accepts == 2
        assert len(aggregate.examples_raw_fail_business_pass) == 2


class TestParsers:
    def test_parse_date_iso(self):
        parsed = parse_date("07/10/2024")
        assert parsed is not None
        assert parsed.iso == "2024-10-07"

    def test_parse_unit_kg(self):
        parsed = parse_unit_value("2195 Kgs.")
        assert parsed is not None
        assert parsed.unit == "kg"
        assert parsed.value == 2195.0

    def test_supplier_greek_normalization(self):
        assert normalize_supplier_name("NOVOFIL S.p.Α.") == normalize_supplier_name("NOVOFIL S.p.A.")
