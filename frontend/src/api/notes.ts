import { getJson, postJson } from './client.ts'
import type { NoteOut } from './schema.d.ts'

export type Note = NoteOut

/** A note Zoomer proposed, as the card under its reply shows it. */
export type ProposedNote = Pick<Note, 'id' | 'text' | 'status'>

/** The customer's answer to a note Zoomer proposed. */
export type NoteDecision = 'confirm' | 'reject'

/** The signed-in user's notes, the newest first. Pending ones are included. */
export function fetchNotes(): Promise<Note[]> {
  return getJson<Note[]>('/api/notes')
}

/** Confirm or reject a note Zoomer proposed, and get it back with its new status. */
export function decideNote(id: string, decision: NoteDecision): Promise<Note> {
  return postJson<Note>(`/api/notes/${id}/${decision}`)
}
