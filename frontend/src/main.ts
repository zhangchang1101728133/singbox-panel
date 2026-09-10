import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'

createApp(App).use(createPinia()).use(router).mount('#app')

document.addEventListener('pointerdown', (e: PointerEvent) => {
  const target = e.target as Element
  const btn = target.closest('button, .n-button, .theme-btn')
  if (!btn) return
  const rect = btn.getBoundingClientRect()
  const size = Math.max(rect.width, rect.height)
  const ripple = document.createElement('span')
  ripple.className = 'global-ripple'
  ripple.style.width = ripple.style.height = size + 'px'
  ripple.style.left = (e.clientX - rect.left - size / 2) + 'px'
  ripple.style.top = (e.clientY - rect.top - size / 2) + 'px'
  const cs = getComputedStyle(btn as HTMLElement)
  if (cs.position === 'static') (btn as HTMLElement).style.position = 'relative'
  if (cs.overflow !== 'hidden') (btn as HTMLElement).style.overflow = 'hidden'
  btn.appendChild(ripple)
  ripple.addEventListener('animationend', () => ripple.remove())
}, { passive: true })

if (window.visualViewport) {
  const vv = window.visualViewport
  const onResize = () => {
    const keyboardOpen = (window.innerHeight - vv.height) > 150
    document.body.classList.toggle('kb-open', keyboardOpen)
  }
  vv.addEventListener('resize', onResize)
  document.addEventListener('focusout', () => {
    setTimeout(onResize, 100)
  }, true)
}
