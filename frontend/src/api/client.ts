import router from '../router'
import type { AuthUser } from '../types/index.ts'

interface ApiErrorShape {
  detail?: string | unknown
}

async function request<T>(url: string, opts: RequestInit & { form?: Record<string, string> } = {}): Promise<T> {
  const fetchOpts: RequestInit = { method: opts.method ?? 'GET', credentials: 'same-origin', headers: {} as Record<string, string> }
  const headers = fetchOpts.headers as Record<string, string>

  if (opts.form) {
    fetchOpts.body = new URLSearchParams(opts.form)
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
  } else if (opts.body !== undefined) {
    fetchOpts.body = opts.body
    headers['Content-Type'] = 'application/json'
  }

  let res: Response
  try {
    res = await fetch(url, fetchOpts)
  } catch {
    throw new Error('网络错误，请检查连接')
  }

  if (res.status === 401) {
    if (router.currentRoute.value.name !== 'login') router.push({ name: 'login' })
    throw new Error('未登录')
  }

  let data: unknown = null
  const text = await res.text()
  if (text) {
    try { data = JSON.parse(text) } catch { data = text }
  }

  if (!res.ok) {
    const err = data as ApiErrorShape
    const detail = err?.detail
    throw new Error(typeof detail === 'string' ? detail : `请求失败 (${res.status})`)
  }
  return data as T
}

export const api = {
  get: <T>(url: string) => request<T>(url),
  post: <T>(url: string, body?: unknown) => request<T>(url, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  postForm: <T>(url: string, form: Record<string, string>) => request<T>(url, { method: 'POST', form }),
  put: <T>(url: string, body?: unknown) => request<T>(url, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  del: <T>(url: string) => request<T>(url, { method: 'DELETE' }),
}
