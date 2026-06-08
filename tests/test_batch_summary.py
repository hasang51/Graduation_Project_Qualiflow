from __future__ import annotations

import unittest

from scripts.run_batch_extraction import _flatten_summary_row


class BatchSummaryTests(unittest.TestCase):
    def test_flatten_summary_uses_review_reasons_fallback_and_llm_usage(self):
        row = _flatten_summary_row(
            "doc001",
            "doc001.pdf",
            quality_class="severe_scan",
            route_used="preprocessed_multimodal",
            page_count=1,
            mode="D",
            extraction={
                "items": [],
                "total_items_detected": 0,
                "confidence_score": 0.9,
                "needs_review": True,
                "llm_usage": {
                    "total_input_tokens": 123,
                    "total_output_tokens": 45,
                    "pages_sent": 1,
                },
            },
            review={
                "review_reasons": ["missing_critical_field:heat_number"],
                "all_reasons": ["missing_critical_field:heat_number", "confidence_below_threshold"],
            },
            latency_ms=10.0,
            status="OK",
            error=None,
        )

        self.assertEqual(row["structured_review_reasons"], "missing_critical_field:heat_number")
        self.assertEqual(row["input_tokens"], 123)
        self.assertEqual(row["output_tokens"], 45)
        self.assertEqual(row["pages_sent"], 1)


if __name__ == "__main__":
    unittest.main()
