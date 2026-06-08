# Phase 1 Validation Notes

Thesis-scope notes on how QualiFlow resolves grades into material specifications
in Phase 1. Intentionally short: this is design documentation, not a standards
reference.

## Scope

Phase 1 replaces the single flat `MATERIAL_SPECS` lookup with three
responsibilities separated into pure modules:

1. `app/domain/grade_registry.py` - alias / canonicalisation layer.
2. `app/domain/spec_registry.py` - spec-lookup layer.
3. `app/domain/numeric_parser.py` - locale-safe numeric normalisation.
4. `app/domain/header_propagation.py` - header-to-row metadata lift.

The validator no longer decides compliance on an unresolved grade. Unknown or
ambiguous grades route to review instead of false-negative `NON_COMPLIANT`.

## Grade aliasing sources

All aliasing rules are conservative. A mapping is only added when:

- two public designations are standardised as equivalent (e.g. DIN / EN steel
  number vs. AISI name), or
- the variant is a direct compositional shorthand of the same family
  (`S355J2+N` vs. `S355J2` - the `+N` is a delivery condition, not a separate
  alloy family).

### Structural carbon steel (EN 10025-2)

The existing QualiFlow `MATERIAL_SPECS` baseline is preserved. Minimum yield
and minimum elongation match EN 10025-2 for plate up to 16 mm thickness
(S235JR 235 MPa / >=26 %, S275JR 275 MPa / >=23 %, S355J2 355 MPa / >=22 %).
Tensile bands in-repo are slightly wider than the EN 10025-2 headline ranges
to absorb supplier reporting variance; this matches the existing thesis
baseline and is not changed in Phase 1.

Aliasing rules:

- `S235JR`, `S275JR`, `S355JR`, `S355J2`, `S355J2+N` are canonicalised with
  whitespace / case / punctuation noise removed.
- `+N`, `+AR`, `+M` delivery conditions do *not* change the canonical family
  but are preserved in `raw`.
- Legacy DIN grades `St 37-2` / `St 52-3` are *not* auto-mapped to
  `S235JR` / `S355J2` - the equivalence depends on delivery condition and the
  Phase 1 registry errs on the side of routing to review.

### Line-pipe steel (API 5L)

- `API 5L X65` / `L450` are treated as the same family.
- Suffix variants `X65M`, `X65Q`, `X65MS`, `X65QS` are recognised as
  candidates of the same family but the spec lookup stays unresolved in
  Phase 1 because PSL1 vs. PSL2 yield/tensile bands differ and the
  prototype does not yet model PSL level.

### Austenitic stainless (EN 10088-1 dual designation)

The following dual designations are standardised and are recognised by the
alias registry:

| EN steel number | AISI / ASTM | Chemical form (EN 10027-1) |
|-----------------|-------------|----------------------------|
| 1.4301          | 304         | X5CrNi18-10                |
| 1.4307          | 304L        | X2CrNi18-9                 |
| 1.4401          | 316         | X5CrNiMo17-12-2            |
| 1.4404          | 316L        | X2CrNiMo17-12-2            |

The registry also recognises explicit dual-certification strings that appear
on Mill Test Certificates in the wild, e.g.:

- `304 / 304L`
- `1.4301 / 1.4307`
- `316/316L`
- `1.4401 / 1.4404`

For these composites, the registry returns **both** canonical forms as
candidates and marks the resolution as `dual_designation=True`. Downstream,
the spec-resolver intentionally leaves stainless specs unresolved in Phase 1:

- Mechanical minima for austenitic stainless vary by product form (sheet,
  plate, bar, tube) and supply condition (annealed, cold-worked, ...), so a
  single `min_yield` / `min_tensile` number would silently fabricate a
  specification. The thesis explicitly avoids that.
- Instead, `spec_registry.resolve_spec` returns `SpecResolution(status=UNRESOLVED_SPEC, reason="stainless product-form dependent")`, and
  the validator emits an `unresolved_spec:<canonical>` review token.

This is the "prefer review over false compliance" rule applied concretely.

## Locale-safe numeric parsing

QualiFlow receives mechanical values both as LLM-returned floats and as raw
cell text (when the LLM includes a string). The parser in
`app/domain/numeric_parser.py` is field-aware:

- `yield_mpa`, `tensile_mpa`: expected plausible range 80-1500 / 120-1800 MPa
  (`quality_thresholds.YIELD_STRENGTH_MPA` / `TENSILE_STRENGTH_MPA`).
  Values like `1.097` or `1,097` that fall **below** the plausible range but
  whose thousand-separator-promoted form (`1097`) falls **inside** the
  plausible range are promoted. If neither form is plausible, the parser
  flags the value as `uncertain=True` and preserves the raw string; the row
  is then routed to review rather than silently coerced.
- `elongation_pct`: expected 1-80 %. `26,5` / `26.5%` both resolve to
  `26.5`. Values where decimal-comma vs. decimal-point interpretations are
  both plausible stay uncertain.
- Short numbers without separators stay unchanged.

The parser is conservative: ambiguity is represented, never hidden.

## Header-to-row propagation

`app/domain/header_propagation.propagate_to_rows` backfills `item.grade` only
when:

1. the row has no grade at all, and
2. the header/metadata carries a grade that resolves in the grade registry,
   and
3. every row that already has a grade agrees with it.

If a row contradicts the header grade, both are preserved and the row is
routed to review via a `header_row_conflict:grade` structured reason. This
keeps header propagation a strictly additive, auditable operation and
prevents the propagation layer from silently overwriting extraction output.

## What remains intentionally unresolved

- Full EN 10088 / ASTM A240 stainless mechanical-property tables (product-form
  dependent). Phase 2 could introduce them behind an explicit product-form
  selector.
- Legacy DIN vs. EN structural equivalence.
- PSL1 vs. PSL2 for API 5L.
- Cross-document header propagation (same-supplier memory).
