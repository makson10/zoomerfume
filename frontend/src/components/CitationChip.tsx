import { Badge, Tooltip } from '@mantine/core'

interface CitationChipProps {
  recordId: string
  /** The answer cites a record that no tool returned in this chat. */
  invalid?: boolean
  onOpen: (recordId: string) => void
}

/** A cited record. Clicking it opens the full record. */
export function CitationChip({ recordId, invalid, onOpen }: CitationChipProps) {
  const chip = (
    <Badge
      component="button"
      type="button"
      size="sm"
      variant="light"
      color={invalid ? 'red' : undefined}
      style={{ cursor: 'pointer', verticalAlign: 'baseline' }}
      onClick={() => onOpen(recordId)}
    >
      {recordId}
    </Badge>
  )
  if (!invalid) return chip
  return (
    <Tooltip label="No tool returned this record in this chat">{chip}</Tooltip>
  )
}
