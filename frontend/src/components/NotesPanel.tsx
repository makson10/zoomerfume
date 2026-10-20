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
import { fetchNotes, type Note } from '../api/notes.ts'

const savedAt = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

function NoteList({ notes }: { notes: Note[] }) {
  if (notes.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        No notes yet. Ask Zoomer to add a perfume to your wishlist.
      </Text>
    )
  }
  return (
    <Stack gap="xs">
      {notes.map((note) => (
        <Paper key={note.id} withBorder p="xs">
          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
            {note.text}
          </Text>
          <Text size="xs" c="dimmed">
            {savedAt.format(new Date(note.created_at))}
          </Text>
        </Paper>
      ))}
    </Stack>
  )
}

interface NotesPanelProps {
  /** Changes each time Zoomer saves a note, so the panel reloads. */
  refreshKey: number
}

/** The customer's notes, the newest first. Zoomer saves them with `save_note`. */
export function NotesPanel({ refreshKey }: NotesPanelProps) {
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
          <NoteList notes={notes} />
        ) : (
          <Loader type="dots" />
        )}
      </ScrollArea>
    </Stack>
  )
}
