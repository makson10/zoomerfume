/** An error response from the API. */
export class ApiError extends Error {
  readonly status: number
  /** The API's error code, or null when the response had no JSON error body. */
  readonly code: string | null

  constructor(status: number, code: string | null, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

interface ErrorBody {
  error?: { code: string; message: string }
}

async function toApiError(response: Response): Promise<ApiError> {
  const body = (await response.json().catch(() => null)) as ErrorBody | null
  if (body?.error) {
    return new ApiError(response.status, body.error.code, body.error.message)
  }
  return new ApiError(
    response.status,
    null,
    `${response.status} ${response.statusText}`,
  )
}

async function request<T>(
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers:
      body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    throw await toApiError(response)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

/** GET a JSON response from the API. */
export function getJson<T>(path: string): Promise<T> {
  return request<T>('GET', path)
}

/** POST to the API, with an optional JSON body, and return the parsed JSON response. */
export function postJson<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('POST', path, body)
}
