import { postStream } from './client.ts'
import type {
  ChatRequest,
  Citations,
  ErrorDetail,
  Step,
  Token,
  ToolCall,
  TurnDone,
} from './schema.d.ts'
import { readEvents } from './sse.ts'

export type { Citations, Step }

/** A turn's state: `running` while Zoomer answers, then how the turn ended. */
export type TurnStatus = 'running' | TurnDone['status']

/** The events of a streamed reply, in the order the server sends them. */
export type ChatEvent =
  | { event: 'token'; data: Token }
  | { event: 'tool_call'; data: ToolCall }
  | { event: 'tool_result'; data: Step }
  | { event: 'citation'; data: Citations }
  /** `reply` is the stored reply, which replaces the streamed text. */
  | { event: 'done'; data: TurnDone }
  | { event: 'error'; data: ErrorDetail }

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
    { conversation_id: conversationId, message } satisfies ChatRequest,
    signal,
  )
  for await (const { event, data } of readEvents(body)) {
    yield { event, data: JSON.parse(data) } as ChatEvent
  }
}
