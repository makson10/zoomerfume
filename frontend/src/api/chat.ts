import { postJson } from './client.ts'

interface ChatResponse {
  reply: string
}

/** Send one message to Zoomer in a conversation and return the reply. */
export async function sendMessage(
  conversationId: string,
  message: string,
): Promise<string> {
  const data = await postJson<ChatResponse>('/api/chat', {
    conversation_id: conversationId,
    message,
  })
  return data.reply
}
