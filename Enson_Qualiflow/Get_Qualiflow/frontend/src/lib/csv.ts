import type { ExtractedItem } from '../types/qualiflow'

function escapeCsv(value: string): string {
  const escaped = value.replace(/"/g, '""')
  return `"${escaped}"`
}

export function buildItemsCsv(items: ExtractedItem[]): string {
  const headers = [
    'Heat No.',
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
    const rowCompliance =
      item.validation?.is_compliant === true
        ? 'Compliant'
        : item.validation?.is_compliant === false
          ? 'Non-compliant'
          : 'Not validated'

    return [
      item.heat_number ?? '',
      item.item_id ?? '',
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
