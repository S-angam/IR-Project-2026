export const API = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? '/api' : '')
export const METHODS = {
  bm25: 'BM25',
  tfidf: 'TF-IDF',
  dense: 'Dense',
  hybrid: 'Hybrid',
  hybrid_relaxed: 'Hybrid + clue relaxation',
}

export async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options)
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body?.detail
    throw new Error(
      Array.isArray(detail)
        ? detail.map(item => item.msg).join('; ')
        : detail || `Request failed (${response.status}). Check that the backend is running.`,
    )
  }
  return body
}

export function sendJson(path, method, body) {
  return request(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
