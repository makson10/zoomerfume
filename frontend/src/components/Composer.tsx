import { ActionIcon, Group, Textarea } from '@mantine/core'
import { IconSend } from '@tabler/icons-react'
import { useState, type KeyboardEvent } from 'react'

const MAX_MESSAGE_LENGTH = 4000

interface ComposerProps {
  onSend: (text: string) => void
  disabled: boolean
  placeholder?: string
}

/** The message box. It keeps its own draft, so typing doesn't re-render the chat. */
export function Composer({
  onSend,
  disabled,
  placeholder = 'Message Zoomer…',
}: ComposerProps) {
  const [draft, setDraft] = useState('')
  const canSend = !disabled && draft.trim().length > 0

  function send() {
    if (!canSend) return
    onSend(draft.trim())
    setDraft('')
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === 'Enter' &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault()
      send()
    }
  }

  return (
    <Group align="flex-end" gap="xs" py="md" wrap="nowrap">
      <Textarea
        flex={1}
        placeholder={placeholder}
        aria-label="Message"
        autosize
        minRows={1}
        maxRows={6}
        maxLength={MAX_MESSAGE_LENGTH}
        value={draft}
        onChange={(event) => setDraft(event.currentTarget.value)}
        onKeyDown={handleKeyDown}
        autoFocus
      />
      <ActionIcon
        size="input-sm"
        onClick={send}
        disabled={!canSend}
        aria-label="Send"
      >
        <IconSend size={18} />
      </ActionIcon>
    </Group>
  )
}
