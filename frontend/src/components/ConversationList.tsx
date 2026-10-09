import { Button, NavLink, ScrollArea, Stack } from '@mantine/core'
import { IconMessage, IconPlus } from '@tabler/icons-react'
import type { Conversation } from '../api/conversations.ts'

interface ConversationListProps {
  conversations: Conversation[]
  activeId: string | null
  disabled: boolean
  onSelect: (id: string) => void
  onNewChat: () => void
}

export function ConversationList({
  conversations,
  activeId,
  disabled,
  onSelect,
  onNewChat,
}: ConversationListProps) {
  return (
    <Stack h="100%" gap="xs">
      <Button
        variant="default"
        leftSection={<IconPlus size={16} />}
        onClick={onNewChat}
        disabled={disabled}
      >
        New chat
      </Button>
      <ScrollArea flex={1} mih={0}>
        {conversations.map((conversation) => (
          <NavLink
            key={conversation.id}
            label={conversation.title ?? 'New chat'}
            leftSection={<IconMessage size={16} />}
            active={conversation.id === activeId}
            disabled={disabled}
            noWrap
            onClick={() => onSelect(conversation.id)}
          />
        ))}
      </ScrollArea>
    </Stack>
  )
}
