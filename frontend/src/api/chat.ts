import { postJson } from './client.ts'

/** The `[KB-042]` citations of one answer, checked against the records the tools returned. */
export interface Citations {
  valid: string[]
  /** Cited ids that no tool returned in this conversation. */
  invalid: string[]
  /** This turn retrieved records, but the answer cites none of them. */
  missing: boolean
}

/** One tool call Zoomer made while answering. */
export interface Step {
  step: number
  tool: string
  args: Record<string, unknown>
  success: boolean
  /** The error code of a failed call, e.g. `NOT_FOUND`. */
  code: string | null
  record_ids: string[]
  duration_ms: number
}

export interface ChatReply {
  reply: string
  turn_id: string
  citations: Citations
  steps: Step[]
}

/** Send one message to Zoomer in a conversation and return the reply with its citations and steps. */
export function sendMessage(
  conversationId: string,
  message: string,
): Promise<ChatReply> {
  return postJson<ChatReply>('/api/chat', {
    conversation_id: conversationId,
    message,
  })
}
