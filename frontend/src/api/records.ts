import { getJson } from './client.ts'

/** A full knowledge base record. */
export interface KbRecord {
  id: string
  title: string
  type: 'product' | 'policy' | 'company' | 'faq' | 'news'
  /** The date of the last update, e.g. `2026-09-08`. */
  updated: string
  header: Record<string, unknown>
  /** Markdown. */
  body: string
}

export function fetchRecord(id: string): Promise<KbRecord> {
  return getJson<KbRecord>(`/api/records/${id}`)
}
