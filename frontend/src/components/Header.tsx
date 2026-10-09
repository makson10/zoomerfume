import {
  ActionIcon,
  Group,
  Image,
  Text,
  Title,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core'
import { IconMoon, IconSun } from '@tabler/icons-react'
import type { ReactNode } from 'react'

interface HeaderProps {
  /** The navbar toggle for small screens, on pages with a navbar. */
  burger?: ReactNode
  /** Controls shown before the color scheme toggle. */
  actions?: ReactNode
}

export function Header({ burger, actions }: HeaderProps) {
  const { setColorScheme } = useMantineColorScheme()
  const colorScheme = useComputedColorScheme('light')
  const nextColorScheme = colorScheme === 'dark' ? 'light' : 'dark'

  return (
    <Group h="100%" px="md" justify="space-between" wrap="nowrap">
      <Group gap="xs" wrap="nowrap">
        {burger}
        <Image src="/logo.svg" alt="" w={28} h={28} />
        <Title order={1} size="h4">
          Zoomerfume
        </Title>
        <Text c="dimmed" size="sm" visibleFrom="sm">
          Zoomer, AI shop assistant
        </Text>
      </Group>
      <Group gap="xs" wrap="nowrap">
        {actions}
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
