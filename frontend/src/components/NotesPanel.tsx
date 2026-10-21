import {
  Alert,
  Loader,
  Paper,
  ScrollArea,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import { useEffect, useState } from 'react'
import { fetchNotes, type Note, type NoteDecision } from '../api/notes.ts'
import { PendingNoteCard } from './PendingNoteCard.tsx'

const savedAt = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

interface NoteListProps {
  notes: Note[]
  onDecide: (id: string, decision: NoteDecision) => Promise<void>
}

function NoteList({ notes, onDecide }: NoteListProps) {
  if (notes.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        No notes yet. Ask Zoomer to add a perfume to your wishlist.
      </Text>
    )
  }
  return (
    <Stack gap="xs">
      {notes.map((note) =>
        note.status === 'pending' ? (
          <PendingNoteCard key={note.id} note={note} onDecide={onDecide} />
        ) : (
          <Paper key={note.id} withBorder p="xs">
            <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
              {note.text}
            </Text>
            <Text size="xs" c="dimmed">
              {savedAt.format(new Date(note.created_at))}
            </Text>
          </Paper>
        ),
      )}
    </Stack>
  )
}

interface NotesPanelProps {
  /** Changes each time the notes change, so the panel reloads. */
  refreshKey: number
  /** Confirms or rejects a pending note. */
  onDecide: (id: string, decision: NoteDecision) => Promise<void>
}

/**
 * The customer's notes, the newest first. Zoomer saves them with `save_note`. Notes
 * that wait for the customer's confirmation show the same card as under the reply.
 */
export function NotesPanel({ refreshKey, onDecide }: NotesPanelProps) {
  const [notes, setNotes] = useState<Note[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let ignore = false
    fetchNotes().then(
      (loaded) => {
        if (ignore) return
        setNotes(loaded)
        setError(false)
      },
      () => {
        if (!ignore) setError(true)
      },
    )
    return () => {
      ignore = true
    }
  }, [refreshKey])

  return (
    <Stack h="100%" gap="sm">
      <Title order={2} size="h5">
        Notes
      </Title>
      <ScrollArea flex={1} mih={0}>
        {error ? (
          <Alert color="red">Couldn't load your notes. Please try again.</Alert>
        ) : notes ? (
          <NoteList notes={notes} onDecide={onDecide} />
        ) : (
          <Loader type="dots" />
        )}
      </ScrollArea>
    </Stack>
  )
}
