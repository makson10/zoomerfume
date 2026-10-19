import {
  Alert,
  Badge,
  Code,
  Group,
  Loader,
  Modal,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import { useEffect, useState } from 'react'
import { fetchToolSchemas, type ToolSchema } from '../api/tools.ts'

function ToolList() {
  const [tools, setTools] = useState<ToolSchema[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let ignore = false
    fetchToolSchemas().then(
      (loaded) => {
        if (!ignore) setTools(loaded)
      },
      () => {
        if (!ignore) setError(true)
      },
    )
    return () => {
      ignore = true
    }
  }, [])

  if (error) {
    return <Alert color="red">Couldn't load the tools. Please try again.</Alert>
  }
  if (!tools) return <Loader type="dots" />

  return (
    <Stack gap="lg">
      <Text size="sm" c="dimmed">
        These are the exact tool schemas the model receives with every message.
      </Text>
      {tools.map((tool) => (
        <Stack key={tool.name} gap="xs">
          <Group gap="xs">
            <Title order={3} size="h4" ff="monospace">
              {tool.name}
            </Title>
            {tool.strict && <Badge variant="light">strict</Badge>}
          </Group>
          <Text size="sm">{tool.description}</Text>
          <Code block style={{ whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(tool.parameters, null, 2)}
          </Code>
        </Stack>
      ))}
    </Stack>
  )
}

interface ToolsModalProps {
  opened: boolean
  onClose: () => void
}

/** A window with every tool Zoomer can call and its JSON schema. */
export function ToolsModal({ opened, onClose }: ToolsModalProps) {
  return (
    <Modal opened={opened} onClose={onClose} title="Zoomer's tools" size="xl">
      {opened && <ToolList />}
    </Modal>
  )
}
