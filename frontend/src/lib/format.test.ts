import { formatMpaDisplay } from './format'

if (formatMpaDisplay(1.097) !== '1097') {
  throw new Error('Expected 1.097 MPa display to normalize to 1097.')
}

if (formatMpaDisplay(1.5) !== '1.5') {
  throw new Error('Expected 1.5 MPa to remain a decimal display value.')
}

if (formatMpaDisplay(264) !== '264') {
  throw new Error('Expected integer MPa values to display without decimals.')
}

if (formatMpaDisplay(null) !== '—') {
  throw new Error('Expected null MPa values to render as missing.')
}

console.info('format.test.ts passed')
