import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client.ts'
import type { AuthUser } from '../types/index.ts'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const checked = ref(false)

  async function fetchMe(): Promise<AuthUser | null> {
    try {
      user.value = await api.get<AuthUser>('/auth/me')
    } catch {
      user.value = null
    } finally {
      checked.value = true
    }
    return user.value
  }

  async function login(username: string, password: string): Promise<void> {
    await api.postForm('/auth/login', { username, password })
    await fetchMe()
  }

  async function logout(): Promise<void> {
    try { await api.post('/auth/logout') } catch { /* 忽略 */ }
    user.value = null
  }

  return { user, checked, fetchMe, login, logout }
})
