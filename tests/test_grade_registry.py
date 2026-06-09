from __future__ import annotations

import unittest

from app.domain.grade_registry import resolve_grade


class ResolveGradeSingleTests(unittest.TestCase):
    def test_clean_s235jr(self):
        resolution = resolve_grade("S235JR")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "S235JR")
        self.assertEqual(resolution.candidates, ("S235JR",))
        self.assertFalse(resolution.dual_designation)

    def test_s355j2_with_whitespace_and_case(self):
        resolution = resolve_grade("  s355 j2  ")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "S355J2")

    def test_s355j2_plus_n_delivery_condition(self):
        resolution = resolve_grade("S355J2+N")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "S355J2+N")

    def test_api_5l_x65(self):
        resolution = resolve_grade("API 5L X65")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "API 5L X65")

    def test_api_5l_x65_compact(self):
        resolution = resolve_grade("API5LX65")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "API 5L X65")

    def test_stainless_1_4301(self):
        resolution = resolve_grade("1.4301")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "1.4301")
        self.assertEqual(resolution.family_group, "stainless_austenitic")

    def test_stainless_304_aisi(self):
        resolution = resolve_grade("AISI 304")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "304")

    def test_welding_wire_supplier_grade(self):
        resolution = resolve_grade("NOVOFIL SG2/NOVOBRONZE SG2")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "SG2")

    def test_astm_tp317l_case_insensitive(self):
        resolution = resolve_grade("tp317l")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "TP317L")
        self.assertEqual(resolution.family_group, "astm_pipe")

    def test_astm_a312_tp317l_alias(self):
        resolution = resolve_grade("ASTM A312 TP317L")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "TP317L")

    def test_317l_short_alias(self):
        resolution = resolve_grade("317L")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "317L")

    def test_tp304_tp316l_pipe_grades(self):
        self.assertEqual(resolve_grade("TP304").canonical, "TP304")
        self.assertEqual(resolve_grade("TP316L").canonical, "TP316L")
        self.assertEqual(resolve_grade("TP321H").canonical, "TP321H")
        self.assertEqual(resolve_grade("TP347").canonical, "TP347")


class ResolveGradeDualDesignationTests(unittest.TestCase):
    def test_304_304l_composite(self):
        resolution = resolve_grade("304/304L")
        self.assertEqual(resolution.status, "resolved_dual")
        self.assertTrue(resolution.dual_designation)
        self.assertIn("304", resolution.candidates)
        self.assertIn("304L", resolution.candidates)

    def test_1_4301_1_4307_composite(self):
        resolution = resolve_grade("1.4301 / 1.4307")
        self.assertEqual(resolution.status, "resolved_dual")
        self.assertIn("1.4301", resolution.candidates)
        self.assertIn("1.4307", resolution.candidates)

    def test_316_316l_composite(self):
        resolution = resolve_grade("316/316L")
        self.assertEqual(resolution.status, "resolved_dual")
        self.assertIn("316", resolution.candidates)
        self.assertIn("316L", resolution.candidates)

    def test_1_4401_1_4404_composite(self):
        resolution = resolve_grade("1.4401/1.4404")
        self.assertEqual(resolution.status, "resolved_dual")

    def test_noisy_321_321h_composite_with_uns_suffix(self):
        resolution = resolve_grade("1.4541/321 1.4878/321H UNS S32100")
        self.assertEqual(resolution.status, "resolved_dual")
        self.assertIn("1.4541", resolution.candidates)
        self.assertIn("321H", resolution.candidates)
        self.assertEqual(resolution.family_group, "stainless_austenitic")

    def test_cross_family_composite_is_ambiguous(self):
        resolution = resolve_grade("S355J2/304L")
        self.assertEqual(resolution.status, "ambiguous")


class ResolveGradeUnknownTests(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(resolve_grade("").status, "empty")
        self.assertEqual(resolve_grade(None).status, "empty")
        self.assertEqual(resolve_grade("   ").status, "empty")

    def test_mystery_grade_is_unknown(self):
        resolution = resolve_grade("MYSTERY-GRADE-42")
        self.assertEqual(resolution.status, "unknown")
        self.assertIsNone(resolution.canonical)

    def test_near_match_not_auto_mapped(self):
        """Supplier noise that *could* be S355 must not be silently mapped."""

        resolution = resolve_grade("St 52-3")
        self.assertEqual(resolution.status, "unknown")

    def test_s235jrh_hollow_section_alias(self):
        resolution = resolve_grade("S235JRH")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "S235JR")

    def test_grade_prefix_noise_s235jrh(self):
        resolution = resolve_grade("GRADE S235JRH")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "S235JR")

    def test_s275j0h_hollow_section_alias(self):
        resolution = resolve_grade("S275J0H")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "S275JR")

    def test_s355j2h_hollow_section_alias(self):
        resolution = resolve_grade("S355J2H")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "S355J2")

    def test_bare_s355_is_ambiguous(self):
        resolution = resolve_grade("S355")
        self.assertEqual(resolution.status, "ambiguous")
        self.assertEqual(resolution.candidates, ("S355JR", "S355J2"))

    def test_en_1_4550_maps_to_347(self):
        resolution = resolve_grade("1.4550")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "347")

    def test_en_1_4571_maps_to_316ti(self):
        resolution = resolve_grade("1.4571")
        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.canonical, "316Ti")


if __name__ == "__main__":
    unittest.main()
