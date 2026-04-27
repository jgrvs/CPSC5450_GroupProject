export type TriageLabel = 'phishing' | 'suspicious' | 'benign' | null
export type QueueStatus = 'needs review' | 'approved' | 'rejected'
export type Severity = 'critical' | 'high' | 'medium' | 'low'

export type ParsedEmail = {
  email_id: string
  canonical_fingerprint: string | null
  duplicate_of: string | null
  headers: {
    from_address: string | null
    subject: string | null
    date: string | null
  }
  indicators: {
    urls: Array<{
      url_actual: string
      url_display_text: string | null
      domain: string
    }>
    domains: string[]
    ip_addresses: string[]
  }
  derived_flags: {
    display_name_mismatch: boolean
    sender_domain_mismatch: boolean
    unicode_trick_detected: boolean
  }
  label: TriageLabel
}

export type QueueItem = {
  event_id: string
  parsed: ParsedEmail
  ui: {
    status: QueueStatus
    severity: Severity
    confidence: number
    rationale: string
    duplicateCount: number
  }
}

export type DecisionEntry = {
  id: string
  status: QueueStatus
  note: string
  at: string
}
