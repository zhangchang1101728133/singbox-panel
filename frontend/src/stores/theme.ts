import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const KEY = 'panel-theme'

export const useThemeStore = defineStore('theme', () => {
  const saved = (() => {
    try { return localStorage.getItem(KEY) } catch { return null }
  })()
  const mode = ref<'dark' | 'light'>(saved === 'light' ? 'light' : 'dark')

  function apply(m: 'dark' | 'light'): void {
    try { document.documentElement.setAttribute('data-theme', m) } catch { /* ssr */ }
  }
  apply(mode.value)

  watch(mode, (m) => {
    apply(m)
    try { localStorage.setItem(KEY, m) } catch { /* 忽略 */ }
  })

  function toggle(): void {
    mode.value = mode.value === 'dark' ? 'light' : 'dark'
  }

  return { mode, toggle }
})
