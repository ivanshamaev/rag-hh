const BASE = import.meta.env.VITE_API_URL || '/api'

async function request(path, options = {}) {
  const url = path.startsWith('http') ? path : `${BASE}${path}`
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export async function getStats() {
  return request('/stats')
}

export async function search(q, limit = 10) {
  const params = new URLSearchParams({ q: q.trim(), limit: String(limit) })
  return request(`/search?${params}`)
}

export async function rag(q, limit = 5) {
  const params = new URLSearchParams({ q: q.trim(), limit: String(limit) })
  return request(`/rag?${params}`)
}

export async function health() {
  return request('/health')
}

export async function getSkills(limit = 50) {
  const res = await request(`/skills?limit=${limit}`)
  return res.skills || []
}
