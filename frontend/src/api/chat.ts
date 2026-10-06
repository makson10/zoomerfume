import { postJson } from './client.ts'

interface ChatResponse {
  reply: string
}

/** Send one message to Zoomer and return the reply. */
export async function sendMessage(
  sessionId: string,
  message: string,
): Promise<string> {
  const data = await postJson<ChatResponse>('/api/chat', {
    session_id: sessionId,
    message,
  })
  return data.reply
}
