import { Badge, Stack, Text, Tooltip } from '@mantine/core'
import { IconShield, IconShieldOff } from '@tabler/icons-react'
import type { SecurityPolicy } from '../api/auth.ts'

const DEFENSES: [keyof Omit<SecurityPolicy, 'mode'>, string][] = [
  ['untrusted_wrap', 'Knowledge base text marked as untrusted'],
  ['rw_separation', 'No notes after reading the knowledge base'],
  ['confirm_notes', 'Notes need your confirmation'],
]

function modeColor(mode: string): string {
  if (mode === 'hardened') return 'green'
  if (mode === 'vulnerable') return 'red'
  return 'orange'
}

/**
 * The security mode the server runs in, read-only: the prompt-injection defenses that
 * are on. A tooltip lists each one. It changes only with the server's settings.
 */
export function ModeBadge({ security }: { security: SecurityPolicy }) {
  const Icon = security.mode === 'vulnerable' ? IconShieldOff : IconShield
  return (
    <Tooltip
      label={
        <Stack gap={2}>
          {DEFENSES.map(([key, label]) => (
            <Text key={key} size="xs">
              {security[key] ? 'On' : 'Off'}: {label}
            </Text>
          ))}
        </Stack>
      }
    >
      <Badge
        color={modeColor(security.mode)}
        variant="light"
        leftSection={<Icon size={12} />}
      >
        {security.mode}
      </Badge>
    </Tooltip>
  )
}
