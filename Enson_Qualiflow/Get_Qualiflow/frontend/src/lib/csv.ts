import type { ExtractedItem } from '../types/qualiflow'
import { renderCriticalIdentifier } from './critical-identifiers'

function escapeCsv(value: string): string {
  const escaped = value.replace(/"/g, '""')
  return `"${escaped}"`
}

export function buildItemsCsv(items: ExtractedItem[]): string {
  const headers = [
    'Heat / Batch No.',
    'Item ID (Pipe/Coil)',
    'Grade',
    'Weight/Length',
    'Yield',
    'Tensile',
    'Elongation',
    'Row Compliance',
    'Validation Deviations',
  ]

  const rows = items.map((item) => {
    let rowCompliance = 'Not validated'
    if (
      (item.validation?.outcome === 'COMPLIANT' || item.validation?.is_compliant === true) &&
      item.traceability_status !== 'VERIFIED'
    ) {
      rowCompliance = 'Needs review'
    } else if (item.needs_review === true) {
      rowCompliance = 'Needs review'
    } else if (item.validation?.is_compliant === true) {
      rowCompliance = 'Compliant'
    } else if (item.validation?.is_compliant === false) {
      rowCompliance = 'Non-compliant'
    }

    return [
      renderCriticalIdentifier(
        item,
        [
          'traceability_identifier_value',
          'heat_number',
          'batch_number',
          'colata_number',
          'lot_number',
          'cast_number',
          'charge_number',
        ],
        '',
      ),
      renderCriticalIdentifier(
        item,
        ['item_id', 'pipe_id', 'pipe_coil_id'],
        '',
        { allowCrossFieldFallback: false, allowTraceabilityShortcut: false },
      ),
      item.grade ?? '',
      item.weight_or_length ?? '',
      item.mechanical_properties?.yield_strength_mpa?.toString() ?? '',
      item.mechanical_properties?.tensile_strength_mpa?.toString() ?? '',
      item.mechanical_properties?.elongation_percentage?.toString() ?? '',
      rowCompliance,
      (item.validation?.deviations ?? []).join(' | '),
    ]
      .map((value) => escapeCsv(value))
      .join(',')
  })

  return [headers.map(escapeCsv).join(','), ...rows].join('\n')
}
