export interface MechanicalProperties {
  yield_strength_mpa: number | null
  tensile_strength_mpa: number | null
  elongation_percentage: number | null
}

export type ValidationOutcome =
  | 'RESOLVED_COMPLIANT'
  | 'RESOLVED_NON_COMPLIANT'
  | 'UNRESOLVED_SPEC'
  | 'UNKNOWN_GRADE'
  | 'AMBIGUOUS_GRADE'
  | 'NOT_APPLICABLE'
  | 'EXTRACTION_UNCERTAIN'

export interface ValidationResult {
  is_compliant: boolean | null
  deviations: string[]
  outcome?: ValidationOutcome | null
}

export interface GradeResolutionPayload {
  raw?: string
  normalized?: string
  status?: string
  canonical?: string | null
  candidates?: string[]
  family_group?: string | null
  dual_designation?: boolean
  reason?: string
  confidence?: number
  spec?: Record<string, unknown> | null
}

export interface ExtractedItem {
  item_id: string | null
  heat_number: string | null
  grade: string | null
  weight_or_length: string | null
  mechanical_properties: MechanicalProperties | null
  validation: ValidationResult | null
  row_confidence?: number | null
  needs_review?: boolean
  grade_resolution?: GradeResolutionPayload | null
  grade_provenance?: string | null
}

export interface ExtractionResponse {
  supplier_name: string
  document_type: string
  certificate_date: string | null
  total_items_detected: number
  items: ExtractedItem[]
  confidence_score: number
  ai_analysis_remarks: string | null
  is_compliant: boolean | null
  needs_review?: boolean
  review_reasons?: string[]
}

export interface HealthResponse {
  status: string
  service: string
  version: string
  model: string
  engine: string
  known_grades: string[]
  supported_documents: string[]
}

export type ComplianceState = 'compliant' | 'non-compliant' | 'not-validated'

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface MeResponse {
  id: number
  email: string
  created_at: string
}

export interface AnalysisListItem {
  id: number
  document_id: number
  status: 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'NEEDS_REVIEW'
  extraction_confidence: number | null
  global_is_compliant: boolean | null
  supplier_name: string | null
  document_type: string | null
  total_items_detected: number | null
  created_at: string
  updated_at: string
}

export interface AnalysisDetail {
  id: number
  document_id: number
  status: 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'NEEDS_REVIEW'
  extraction_confidence: number | null
  global_is_compliant: boolean | null
  supplier_name: string | null
  document_type: string | null
  certificate_date: string | null
  total_items_detected: number | null
  ai_analysis_remarks: string | null
  raw_response_json: Record<string, unknown> | null
  preprocessing_meta_json: Record<string, unknown> | null
  error_message: string | null
  created_at: string
  updated_at: string
  extraction: ExtractionResponse | null
}
