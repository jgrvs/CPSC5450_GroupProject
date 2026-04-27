import { getToken } from './auth'

const API_BASE = 'http://localhost:8000/api/v1'

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...init?.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })

  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`)
  }

  return res.json()
}

export type EmailEventResponse = {
  event_id: string
  source_filename: string
  raw_path: string
  status: 'queued' | 'processing' | 'done' | 'failed'
  error: string | null
  created_at: string
  updated_at: string
  processed_at: string | null
}

export type EmailParsedResponse = {
  event_id: string
  fingerprint: string
  canonical_fingerprint: string | null
  duplicate_of: string | null
  from_address: string | null
  to_address: string | null
  subject: string | null
  date: string | null
  parsed_payload: Record<string, unknown>
}

export type MessageDetailResponse = {
  event: EmailEventResponse
  message: EmailParsedResponse | null
}

export function fetchMessages(): Promise<EmailEventResponse[]> {
  return apiFetch('/email/messages')
}

export function fetchMessageDetail(eventId: string): Promise<MessageDetailResponse> {
  return apiFetch(`/email/message/${eventId}`)
}

export async function fetchRawEmail(eventId: string): Promise<string> {
  const token = getToken()
  const res = await fetch(`${API_BASE}/email/message/${eventId}/raw`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
  return res.text()
}
