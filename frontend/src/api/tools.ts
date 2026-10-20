import { getJson } from './client.ts'
import type { ToolSchema } from './schema.d.ts'

export type { ToolSchema }

/** Zoomer's tools, exactly as the model receives them. */
export function fetchToolSchemas(): Promise<ToolSchema[]> {
  return getJson<ToolSchema[]>('/api/tools/schema')
}
