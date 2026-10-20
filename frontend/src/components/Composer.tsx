import { ActionIcon, Group, Textarea } from '@mantine/core'
import { IconPlayerStopFilled, IconSend } from '@tabler/icons-react'
import { useState, type KeyboardEvent } from 'react'

const MAX_MESSAGE_LENGTH = 4000

interface ComposerProps {
  /** Resolving to `false` means the message wasn't sent: the text comes back. */
  onSend: (text: string) => void | Promise<boolean>
  /** When set, a Stop button replaces Send. */
  onStop?: () => void
  disabled: boolean
  placeholder?: string
}

/** The message box. It keeps its own draft, so typing doesn't re-render the chat. */
export function Composer({
  onSend,
  onStop,
  disabled,
  placeholder = 'Message Zoomer…',
}: ComposerProps) {
  const [draft, setDraft] = useState('')
  const canSend = !disabled && draft.trim().length > 0

  async function send() {
    if (!canSend) return
    const text = draft.trim()
    setDraft('')
    if ((await onSend(text)) === false) {
      setDraft((current) => current || text)
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === 'Enter' &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault()
      void send()
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
      {onStop ? (
        <ActionIcon size="input-sm" onClick={onStop} aria-label="Stop">
          <IconPlayerStopFilled size={18} />
        </ActionIcon>
      ) : (
        <ActionIcon
          size="input-sm"
          onClick={() => void send()}
          disabled={!canSend}
          aria-label="Send"
        >
          <IconSend size={18} />
        </ActionIcon>
      )}
    </Group>
  )
}
