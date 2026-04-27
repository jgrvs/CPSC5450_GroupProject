import type { EmailEventResponse, MessageDetailResponse } from '@/lib/api'
import type { ParsedEmail, QueueItem, Severity, TriageLabel } from './types'

function deriveSeverity(parsed: ParsedEmail): Severity {
  const flags = parsed.derived_flags
  const urls = parsed.indicators.urls.length
  const ips = parsed.indicators.ip_addresses.length
  const strongSignals =
    Number(flags.display_name_mismatch) +
    Number(flags.sender_domain_mismatch) +
    Number(flags.unicode_trick_detected) +
    Number(urls >= 3) +
    Number(ips >= 1)

  if (strongSignals >= 4 || parsed.label === 'phishing') return 'critical'
  if (strongSignals >= 3) return 'high'
  if (strongSignals >= 1 || parsed.label === 'suspicious') return 'medium'
  return 'low'
}

function deriveConfidence(label: TriageLabel): number {
  if (label === 'phishing') return 0.9
  if (label === 'suspicious') return 0.65
  if (label === 'benign') return 0.8
  return 0.5
}

function deriveRationale(parsed: ParsedEmail): string {
  const signals: string[] = []
  if (parsed.derived_flags.display_name_mismatch) signals.push('display-name mismatch')
  if (parsed.derived_flags.sender_domain_mismatch) signals.push('sender-domain mismatch')
  if (parsed.derived_flags.unicode_trick_detected) signals.push('unicode trick signal')
  if (parsed.indicators.urls.length > 0)
    signals.push(`${parsed.indicators.urls.length} URL indicators`)
  if (parsed.indicators.ip_addresses.length > 0)
    signals.push(`${parsed.indicators.ip_addresses.length} IP indicators`)

  if (signals.length === 0) return 'Low-risk indicator profile with no major mismatch signals.'
  return signals.join(', ')
}

function parsedPayloadToParsedEmail(
  eventId: string,
  payload: Record<string, unknown>,
): ParsedEmail {
  const headers = (payload.headers as Record<string, unknown>) ?? {}
  const indicators = (payload.indicators as Record<string, unknown>) ?? {}
  const flags = (payload.derived_flags as Record<string, unknown>) ?? {}

  return {
    email_id: (payload.email_id as string) ?? eventId,
    canonical_fingerprint: (payload.canonical_fingerprint as string) ?? null,
    duplicate_of: null,
    headers: {
      from_address: (headers.from_address as string) ?? null,
      subject: (headers.subject as string) ?? null,
      date: (headers.date as string) ?? null,
    },
    indicators: {
      urls: (indicators.urls as ParsedEmail['indicators']['urls']) ?? [],
      domains: (indicators.domains as string[]) ?? [],
      ip_addresses: (indicators.ip_addresses as string[]) ?? [],
    },
    derived_flags: {
      display_name_mismatch: Boolean(flags.display_name_mismatch),
      sender_domain_mismatch: Boolean(flags.sender_domain_mismatch),
      unicode_trick_detected: Boolean(flags.unicode_trick_detected),
    },
    label: (payload.label as TriageLabel) ?? null,
  }
}

/** Convert a message detail response (event + parsed payload) into a QueueItem. */
export function fromMessageDetail(detail: MessageDetailResponse): QueueItem | null {
  if (!detail.message?.parsed_payload) return null

  const parsed = parsedPayloadToParsedEmail(
    detail.event.event_id,
    detail.message.parsed_payload,
  )
  parsed.duplicate_of = detail.message.duplicate_of

  return {
    event_id: detail.event.event_id,
    parsed,
    ui: {
      status: 'needs review',
      severity: deriveSeverity(parsed),
      confidence: deriveConfidence(parsed.label),
      rationale: deriveRationale(parsed),
      duplicateCount: 0,
    },
  }
}

/** Convert a flat event (from the list endpoint) into a minimal QueueItem placeholder. */
export function fromEmailEvent(event: EmailEventResponse): QueueItem {
  const parsed: ParsedEmail = {
    email_id: event.event_id,
    canonical_fingerprint: null,
    duplicate_of: null,
    headers: {
      from_address: null,
      subject: event.source_filename.replace(/\.eml$/i, ''),
      date: event.created_at,
    },
    indicators: { urls: [], domains: [], ip_addresses: [] },
    derived_flags: {
      display_name_mismatch: false,
      sender_domain_mismatch: false,
      unicode_trick_detected: false,
    },
    label: null,
  }

  return {
    event_id: event.event_id,
    parsed,
    ui: {
      status: 'needs review',
      severity: 'low',
      confidence: 0.5,
      rationale:
        event.status === 'done'
          ? 'Parsed — loading details...'
          : `Status: ${event.status}`,
      duplicateCount: 0,
    },
  }
}
