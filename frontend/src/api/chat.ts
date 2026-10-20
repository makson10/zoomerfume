import { postStream } from './client.ts'
import { readEvents } from './sse.ts'

/** A turn's state: `running` while Zoomer answers, then how the turn ended. */
export type TurnStatus = 'running' | 'ok' | 'max_steps' | 'cancelled' | 'failed'

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

/** The events of a streamed reply, in the order the server sends them. */
export type ChatEvent =
  | { event: 'token'; data: { text: string } }
  | {
      event: 'tool_call'
      data: { tool: string; args: Record<string, unknown> }
    }
  | { event: 'tool_result'; data: Step }
  | { event: 'citation'; data: Citations }
  /** `reply` is the stored reply, which replaces the streamed text. */
  | {
      event: 'done'
      data: { turn_id: string; status: TurnStatus; reply: string }
    }
  | { event: 'error'; data: { code: string; message: string } }

/**
 * Send one message to Zoomer in a conversation and yield the reply's events as they
 * arrive. Aborting `signal` closes the stream, and the server stops the turn.
 */
export async function* streamMessage(
  conversationId: string,
  message: string,
  signal: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const body = await postStream(
    '/api/chat/stream',
    { conversation_id: conversationId, message },
    signal,
  )
  for await (const { event, data } of readEvents(body)) {
    yield { event, data: JSON.parse(data) } as ChatEvent
  }
}
