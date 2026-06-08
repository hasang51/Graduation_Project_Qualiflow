from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_manifest import build, guess_supplier_hint
from scripts.select_gold_candidates import select_balanced


class SupplierHintTests(unittest.TestCase):
    def test_known_patterns(self):
        self.assertEqual(guess_supplier_hint("Acroni.pdf"), "acroni")
        self.assertEqual(guess_supplier_hint("Outokumpu.pdf"), "outokumpu")
        self.assertEqual(guess_supplier_hint("S355MC-Dry.pdf"), "s235_s275_s355")
        self.assertEqual(guess_supplier_hint("unknown_file.pdf"), "unknown")


class BuildManifestTests(unittest.TestCase):
    def test_merges_discovery_and_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            discovery_path = tmp_path / "discovery.jsonl"
            profile_path = tmp_path / "profile.jsonl"
            output_dir = tmp_path / "out"

            discovery_rows = [
                {
                    "document_id": "abc123",
                    "filename": "Acroni.pdf",
                    "abs_path": "/fake/Acroni.pdf",
                    "size_bytes": 500_000,
                    "sha256": "abc123" + "0" * 58,
                },
                {
                    "document_id": "def456",
                    "filename": "Big-Pipe-Mill.pdf",
                    "abs_path": "/fake/Big-Pipe-Mill.pdf",
                    "size_bytes": 15_000_000,
                    "sha256": "def456" + "0" * 58,
                },
            ]
            profile_rows = [
                {
                    "document_id": "abc123",
                    "filename": "Acroni.pdf",
                    "page_count": 1,
                    "has_text_layer": True,
                    "text_density": 0.4,
                    "blur_score": 220.0,
                    "noise_score": 4.0,
                    "table_presence_hint": True,
                    "quality_class": "digital_clean",
                    "reasons": ["text_layer_present"],
                    "abs_path": "/fake/Acroni.pdf",
                    "sha256": "abc123" + "0" * 58,
                    "size_bytes": 500_000,
                },
                {
                    "document_id": "def456",
                    "filename": "Big-Pipe-Mill.pdf",
                    "page_count": 20,
                    "has_text_layer": False,
                    "text_density": 0.0,
                    "blur_score": 40.0,
                    "noise_score": 30.0,
                    "table_presence_hint": True,
                    "quality_class": "noisy_scan",
                    "reasons": ["blur_high", "noise_high"],
                    "abs_path": "/fake/Big-Pipe-Mill.pdf",
                    "sha256": "def456" + "0" * 58,
                    "size_bytes": 15_000_000,
                },
            ]
            discovery_path.write_text("\n".join(json.dumps(r) for r in discovery_rows), encoding="utf-8")
            profile_path.write_text("\n".join(json.dumps(r) for r in profile_rows), encoding="utf-8")

            manifest_jsonl, manifest_csv = build(discovery_path, profile_path, output_dir)
            self.assertTrue(manifest_jsonl.exists())
            self.assertTrue(manifest_csv.exists())

            merged = [json.loads(line) for line in manifest_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(merged), 2)

            by_id = {row["document_id"]: row for row in merged}
            acroni = by_id["abc123"]
            self.assertEqual(acroni["quality_class"], "digital_clean")
            self.assertEqual(acroni["page_bucket"], "single")
            self.assertEqual(acroni["supplier_hint"], "acroni")

            big = by_id["def456"]
            self.assertEqual(big["quality_class"], "noisy_scan")
            self.assertEqual(big["page_bucket"], "long")
            self.assertEqual(big["size_bucket"], "xl")
            self.assertIn(big["supplier_hint"], {"pipe_mill"})


class SelectBalancedTests(unittest.TestCase):
    def test_round_robin_over_quality_classes(self):
        rows = []
        for i in range(5):
            rows.append({"document_id": f"degraded_{i}", "quality_class": "noisy_scan", "page_bucket": "short"})
        for i in range(5):
            rows.append({"document_id": f"clean_{i}", "quality_class": "scan_clean", "page_bucket": "short"})
        for i in range(5):
            rows.append({"document_id": f"digital_{i}", "quality_class": "digital_clean", "page_bucket": "short"})

        picks = select_balanced(rows, n=6)
        self.assertEqual(len(picks), 6)
        classes = [row["quality_class"] for row in picks]
        # Each class should contribute at least once.
        self.assertIn("noisy_scan", classes)
        self.assertIn("scan_clean", classes)
        self.assertIn("digital_clean", classes)

    def test_respects_n_larger_than_pool(self):
        rows = [{"document_id": "x", "quality_class": "scan_clean", "page_bucket": "short"}]
        picks = select_balanced(rows, n=5)
        self.assertEqual(len(picks), 1)


if __name__ == "__main__":
    unittest.main()
