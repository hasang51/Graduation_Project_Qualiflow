from __future__ import annotations

import ast
import unittest
from pathlib import Path


def _load_prompt_constant(name: str) -> str:
    source_path = Path(__file__).resolve().parents[1] / "app" / "services" / "extraction_pipeline.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                value = ast.literal_eval(node.value)
                if isinstance(value, str):
                    return value
    raise AssertionError(f"{name} constant not found")


METADATA_PROMPT = _load_prompt_constant("METADATA_PROMPT")
ITEM_PROMPT = _load_prompt_constant("ITEM_PROMPT")


class ExtractionPromptTraceabilityTests(unittest.TestCase):
    def test_metadata_prompt_requires_directly_readable_identifiers(self):
        self.assertIn("STRICT IDENTIFIER TRACEABILITY RULE", METADATA_PROMPT)
        self.assertIn("heat_number, batch_number, certificate_number, and order_number", METADATA_PROMPT)
        self.assertIn("every character must be directly readable from the document image", METADATA_PROMPT)
        self.assertIn("return null for that identifier", METADATA_PROMPT)
        self.assertIn("Identifiers must not be inferred from nearby rows", METADATA_PROMPT)
        self.assertIn("Never complete a partially visible identifier sequence", METADATA_PROMPT)
        self.assertIn("Do not use pattern completion for identifiers", METADATA_PROMPT)
        self.assertIn("critical_identifier_unverified", METADATA_PROMPT)

    def test_item_prompt_requires_directly_readable_identifiers(self):
        self.assertIn("RULE 2 — STRICT NULL POLICY", ITEM_PROMPT)
        self.assertIn("heat_number, item_id, batch_number, certificate_number, order_number", ITEM_PROMPT)
        self.assertIn("return null", ITEM_PROMPT)
        self.assertIn("Do not complete partial sequences", ITEM_PROMPT)
        self.assertIn("Do not infer from adjacent rows", ITEM_PROMPT)
        self.assertIn("set needs_review=true for the row", ITEM_PROMPT)
        self.assertIn("RULE 6 — CRITICAL: DO NOT CONTRADICT YOUR OWN AUDIT", ITEM_PROMPT)

    def test_identifier_prompts_do_not_reintroduce_best_effort_language(self):
        combined = f"{METADATA_PROMPT} {ITEM_PROMPT}".lower()
        forbidden_phrases = (
            "best guess",
            "best-guess",
            "capture the visible value",
            "complete a sequence based on",
            "infer values from context",
            "use pattern completion for identifiers unless",
        )
        for phrase in forbidden_phrases:
            self.assertNotIn(phrase, combined)


if __name__ == "__main__":
    unittest.main()
