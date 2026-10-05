import {
  ActionIcon,
  Button,
  Group,
  Image,
  Text,
  Title,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core'
import { IconMoon, IconPlus, IconSun } from '@tabler/icons-react'

interface HeaderProps {
  onNewChat: () => void
  newChatDisabled: boolean
}

export function Header({ onNewChat, newChatDisabled }: HeaderProps) {
  const { setColorScheme } = useMantineColorScheme()
  const colorScheme = useComputedColorScheme('light')
  const nextColorScheme = colorScheme === 'dark' ? 'light' : 'dark'

  return (
    <Group h="100%" px="md" justify="space-between" wrap="nowrap">
      <Group gap="xs" wrap="nowrap">
        <Image src="/logo.svg" alt="" w={28} h={28} />
        <Title order={1} size="h4">
          Zoomerfume
        </Title>
        <Text c="dimmed" size="sm" visibleFrom="sm">
          Zoomer, AI shop assistant
        </Text>
      </Group>
      <Group gap="xs" wrap="nowrap">
        <Button
          variant="default"
          leftSection={<IconPlus size={16} />}
          onClick={onNewChat}
          disabled={newChatDisabled}
        >
          New chat
        </Button>
        <ActionIcon
          variant="default"
          size="input-sm"
          onClick={() => setColorScheme(nextColorScheme)}
          aria-label={`Switch to ${nextColorScheme} mode`}
        >
          {colorScheme === 'dark' ? (
            <IconSun size={18} />
          ) : (
            <IconMoon size={18} />
          )}
        </ActionIcon>
      </Group>
    </Group>
  )
}
