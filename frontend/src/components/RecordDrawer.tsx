import {
  Alert,
  Badge,
  Drawer,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import { useEffect, useState } from 'react'
import { ApiError } from '../api/client.ts'
import { fetchRecord, type KbRecord } from '../api/records.ts'
import { MarkdownText } from './MarkdownText.tsx'

function RecordView({ recordId }: { recordId: string }) {
  const [record, setRecord] = useState<KbRecord | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    fetchRecord(recordId).then(
      (loaded) => {
        if (!ignore) setRecord(loaded)
      },
      (error) => {
        if (ignore) return
        setError(
          error instanceof ApiError && error.code
            ? error.message
            : "Couldn't load this record. Please try again.",
        )
      },
    )
    return () => {
      ignore = true
    }
  }, [recordId])

  if (error) return <Alert color="red">{error}</Alert>
  if (!record) return <Loader type="dots" />

  return (
    <Stack gap="sm">
      <Title order={2} size="h3">
        {record.title}
      </Title>
      <Group gap="xs">
        <Badge variant="light">{record.id}</Badge>
        <Badge variant="default">{record.type}</Badge>
        <Text size="sm" c="dimmed">
          Updated {record.updated}
        </Text>
      </Group>
      <MarkdownText>{record.body}</MarkdownText>
    </Stack>
  )
}

interface RecordDrawerProps {
  recordId: string | null
  onClose: () => void
}

/** A side panel with the full text of a cited knowledge base record. */
export function RecordDrawer({ recordId, onClose }: RecordDrawerProps) {
  return (
    <Drawer
      opened={recordId !== null}
      onClose={onClose}
      position="right"
      size="lg"
      title="Knowledge base record"
    >
      {recordId && <RecordView key={recordId} recordId={recordId} />}
    </Drawer>
  )
}
