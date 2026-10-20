/**
 * lib/api.ts
 * Typed fetch helpers for all backend REST endpoints.
 */

import type { TokenResponse, AuthUser, UserRecord } from '../types'

const BASE = '/api'

/** Returns the stored JWT token (if any). */
export function getToken(): string | null {
  return localStorage.getItem('ls_token')
}

export function setToken(token: string): void {
  localStorage.setItem('ls_token', token)
}

export function clearToken(): void {
  localStorage.removeItem('ls_token')
}

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = { ...authHeaders(), ...(init?.headers as Record<string, string> | undefined) }
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  // 204 No Content — return undefined cast to T (callers annotate as Promise<void>)
  if (res.status === 204 || res.headers.get('content-length') === '0') {
    return undefined as unknown as T
  }
  return res.json() as Promise<T>
}

// ── Auth ─────────────────────────────────────────────────────────────── //

export const login = (username: string, password: string): Promise<TokenResponse> => {
  const body = new URLSearchParams({ username, password })
  return req<TokenResponse>('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  })
}

export const getMe = (): Promise<AuthUser> => req<AuthUser>('/auth/me')

// ── Users (admin only) ───────────────────────────────────────────────── //

export const listUsers = (): Promise<UserRecord[]> => req<UserRecord[]>('/users')

export const createUser = (data: {
  username: string
  password: string
  full_name?: string
  role?: 'admin' | 'user'
}): Promise<UserRecord> =>
  req<UserRecord>('/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })

export const deactivateUser = (username: string): Promise<void> =>
  req<void>(`/users/${encodeURIComponent(username)}/deactivate`, { method: 'PATCH' })

export const reactivateUser = (username: string): Promise<void> =>
  req<void>(`/users/${encodeURIComponent(username)}/reactivate`, { method: 'PATCH' })

export const deleteUser = (username: string): Promise<void> =>
  req<void>(`/users/${encodeURIComponent(username)}`, { method: 'DELETE' })

// ── Sessions ────────────────────────────────────────────────────────── //

export const listSessions = (params?: { type?: string; status?: string; user?: string; limit?: number; skip?: number }) => {
  const q = new URLSearchParams()
  if (params?.type) q.set('type', params.type)
  if (params?.status) q.set('status', params.status)
  if (params?.user) q.set('user', params.user)
  if (params?.limit) q.set('limit', String(params.limit))
  if (params?.skip) q.set('skip', String(params.skip))
  return req<any[]>(`/sessions?${q}`)
}

export const getSession = (sessionId: string) =>
  req<any>(`/sessions/${sessionId}`)

export const getSessionEvents = (sessionId: string, params?: { speaker_id?: string; limit?: number; skip?: number }) => {
  const q = new URLSearchParams()
  if (params?.speaker_id) q.set('speaker_id', params.speaker_id)
  if (params?.limit) q.set('limit', String(params.limit))
  if (params?.skip) q.set('skip', String(params.skip))
  return req<any>(`/sessions/${sessionId}/events?${q}`)
}

export const getSessionSpeakers = (sessionId: string) =>
  req<any[]>(`/sessions/${sessionId}/speakers`)

export const deleteSession = (sessionId: string) =>
  fetch(`${BASE}/sessions/${sessionId}`, { method: 'DELETE', headers: authHeaders() })

// ── Uploads ─────────────────────────────────────────────────────────── //

export const listUploads = (params?: { status?: string; limit?: number }) => {
  const q = new URLSearchParams()
  if (params?.status) q.set('status', params.status)
  if (params?.limit) q.set('limit', String(params.limit))
  return req<any[]>(`/uploads?${q}`)
}

export const uploadFile = (file: File): Promise<{ session_id: string; status: string; message: string }> => {
  const fd = new FormData()
  fd.append('file', file)
  return req('/uploads', { method: 'POST', body: fd })
}
