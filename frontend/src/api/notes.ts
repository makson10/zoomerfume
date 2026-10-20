import { getJson } from './client.ts'
import type { NoteOut } from './schema.d.ts'

export type Note = NoteOut

/** The signed-in user's notes, the newest first. */
export function fetchNotes(): Promise<Note[]> {
  return getJson<Note[]>('/api/notes')
}
