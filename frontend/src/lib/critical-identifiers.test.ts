import { renderCriticalIdentifier } from './critical-identifiers'

const suppressedRendered = renderCriticalIdentifier(
  {
    accepted_identifier_values: { heat_number: null, traceability_identifier_value: null },
    heat_number: '12345678',
    raw_identifier_candidates: { heat_number: '12345678' },
    review_reasons: ['critical_identifier_unverified'],
    row_status: 'NEEDS_REVIEW',
  },
  ['heat_number', 'heat_no'],
)

if (suppressedRendered !== '—') {
  throw new Error('Expected accepted null critical identifier to render as dash.')
}

const doc001Rendered = renderCriticalIdentifier(
  {
    accepted_identifier_values: {
      traceability_identifier_value: '410537',
      heat_number: null,
      batch_number: '410537',
    },
    traceability_identifier_value: '410537',
    heat_number: null,
    batch_number: '410537',
    identifier_visibility_verified: true,
    review_reasons: ['unresolved_spec'],
    row_status: 'NEEDS_REVIEW',
  },
  ['traceability_identifier_value', 'heat_number', 'batch_number'],
)

if (doc001Rendered !== '410537') {
  throw new Error('Expected readable heat number to stay visible for non-identifier review reasons.')
}

const batchFallbackRendered = renderCriticalIdentifier(
  {
    accepted_identifier_values: { heat_number: null, batch_number: '410537' },
    heat_number: null,
    batch_number: '410537',
    identifier_visibility_verified: true,
  },
  ['traceability_identifier_value', 'heat_number', 'batch_number'],
)

if (batchFallbackRendered !== '410537') {
  throw new Error('Expected accepted batch_number to render when heat_number is null.')
}

/** Item ID column must never borrow Heat/Batch traceability for display when strict options are used. */
const strictItemColumn = renderCriticalIdentifier(
  {
    accepted_identifier_values: {
      traceability_identifier_value: '10113084',
      heat_number: '10113084',
      item_id: null,
    },
    heat_number: '10113084',
    item_id: null,
    traceability_identifier_value: '10113084',
    identifier_visibility_verified: true,
    review_reasons: [],
  },
  ['item_id', 'pipe_id', 'pipe_coil_id'],
  '—',
  { allowCrossFieldFallback: false, allowTraceabilityShortcut: false },
)

if (strictItemColumn !== '—') {
  throw new Error('Expected strict Item ID renderer to omit heat_number / traceability fallback.')
}

const castCandidateRendered = renderCriticalIdentifier(
  {
    accepted_identifier_values: { cast_number: null, traceability_identifier_value: null },
    cast_number: null,
    raw_identifier_candidates: {
      cast_number: [{ value: '9316704', reason: 'low_identifier_confidence', accepted: false }],
    },
    traceability_identifier_type: 'cast_number',
    identifier_visibility_verified: false,
    review_reasons: ['traceability_unverified'],
  },
  ['cast_number'],
)

if (castCandidateRendered !== '9316704 (needs verification)') {
  throw new Error('Expected suppressed cast_number candidate to render with needs verification label.')
}
