import { getJson } from './client.ts'
import type { RecordOut } from './schema.d.ts'

/** A full knowledge base record. `body` is Markdown. */
export type KbRecord = RecordOut

export function fetchRecord(id: string): Promise<KbRecord> {
  return getJson<KbRecord>(`/api/records/${id}`)
}
