import { getJson } from './client.ts'

export interface ToolSchema {
  name: string
  description: string
  /** The JSON schema of the tool's arguments. */
  parameters: Record<string, unknown>
  strict: boolean
}

/** Zoomer's tools, exactly as the model receives them. */
export function fetchToolSchemas(): Promise<ToolSchema[]> {
  return getJson<ToolSchema[]>('/api/tools/schema')
}
