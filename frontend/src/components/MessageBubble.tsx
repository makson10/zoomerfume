import { Paper, Text, Typography } from '@mantine/core'
import Markdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage } from '../hooks/useChat.ts'

const markdownComponents: Components = {
  a: ({ node: _node, ...props }) => (
    <a {...props} target="_blank" rel="noreferrer" />
  ),
}

interface MessageBubbleProps {
  message: ChatMessage
}

export function MessageBubble({ message }: MessageBubbleProps) {
  if (message.role === 'user') {
    return (
      <Paper
        px="md"
        py="xs"
        maw="85%"
        bg="var(--mantine-primary-color-light)"
        style={{ alignSelf: 'flex-end' }}
      >
        <Text style={{ whiteSpace: 'pre-wrap' }}>{message.content}</Text>
      </Paper>
    )
  }

  return (
    <Paper
      px="md"
      py="xs"
      maw="85%"
      withBorder
      style={{ alignSelf: 'flex-start' }}
    >
      <Typography>
        <Markdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {message.content}
        </Markdown>
      </Typography>
    </Paper>
  )
}
