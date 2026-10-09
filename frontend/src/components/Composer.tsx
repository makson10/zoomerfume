import { ActionIcon, Group, Textarea } from '@mantine/core'
import { IconSend } from '@tabler/icons-react'
import type { KeyboardEvent } from 'react'

const MAX_MESSAGE_LENGTH = 4000

interface ComposerProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  disabled: boolean
  placeholder?: string
}

export function Composer({
  value,
  onChange,
  onSend,
  disabled,
  placeholder = 'Message Zoomer…',
}: ComposerProps) {
  const canSend = !disabled && value.trim().length > 0

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === 'Enter' &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault()
      if (canSend) onSend()
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
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
        onKeyDown={handleKeyDown}
        autoFocus
      />
      <ActionIcon
        size="input-sm"
        onClick={onSend}
        disabled={!canSend}
        aria-label="Send"
      >
        <IconSend size={18} />
      </ActionIcon>
    </Group>
  )
}
