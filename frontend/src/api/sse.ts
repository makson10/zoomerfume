/** One server-sent event: its name and its raw `data` field. */
export interface ServerSentEvent {
  event: string
  data: string
}

function parseEvent(block: string): ServerSentEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice('event: '.length)
    else if (line.startsWith('data: ')) data.push(line.slice('data: '.length))
  }
  return data.length > 0 ? { event, data: data.join('\n') } : null
}

/**
 * Read a `text/event-stream` body event by event.
 *
 * Network chunks don't follow event boundaries, so text is buffered until a blank
 * line ends an event. Blocks without data, like the server's `: ping` keep-alive
 * comments, are skipped.
 */
export async function* readEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<ServerSentEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) return
    buffer += decoder.decode(value, { stream: true })
    let end = buffer.indexOf('\n\n')
    while (end !== -1) {
      const event = parseEvent(buffer.slice(0, end))
      if (event) yield event
      buffer = buffer.slice(end + 2)
      end = buffer.indexOf('\n\n')
    }
  }
}
