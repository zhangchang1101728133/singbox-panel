<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, NCard, NForm, NFormItem, NInput, NButton } from 'naive-ui'
import { errMsg } from '../api/client'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)

async function onLogin() {
  if (!username.value || !password.value) {
    message.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    message.success('登录成功')
    router.push({ name: 'dashboard' })
  } catch (e) {
    message.error(errMsg(e) || '登录失败')
  } finally {
    loading.value = false
  }
}

// ── 粒子背景 ──
interface Particle {
  x: number; y: number; vx: number; vy: number
}

const canvas = ref<HTMLCanvasElement | null>(null)
let raf: number | null = null

function initParticles(): (() => void) | undefined {
  const el = canvas.value
  if (!el) return
  const context = el.getContext('2d')
  if (!context) return
  // 显式标注：下面这些变量会在嵌套函数里被引用，TS 不会保留收窄结果
  const c: HTMLCanvasElement = el
  const ctx: CanvasRenderingContext2D = context
  let w = 0
  let h = 0
  let pts: Particle[] = []
  const seed = (n: number) => ((Math.sin(n * 12.9898) * 43758.5453) % 1 + 1) % 1
  function resize() {
    w = c.width = c.offsetWidth
    h = c.height = c.offsetHeight
    pts = Array.from({ length: 56 }, (_, i): Particle => ({
      x: seed(i + 1) * w, y: seed(i + 7) * h,
      vx: (seed(i + 3) - 0.5) * 0.4, vy: (seed(i + 5) - 0.5) * 0.4,
    }))
  }
  resize()
  window.addEventListener('resize', resize)
  function draw() {
    ctx.clearRect(0, 0, w, h)
    for (const p of pts) {
      p.x += p.vx; p.y += p.vy
      if (p.x < 0 || p.x > w) p.vx *= -1
      if (p.y < 0 || p.y > h) p.vy *= -1
    }
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y
        const d = Math.hypot(dx, dy)
        if (d < 130) {
          ctx.strokeStyle = `rgba(45, 212, 191, ${0.16 * (1 - d / 130)})`
          ctx.lineWidth = 1
          ctx.beginPath(); ctx.moveTo(pts[i].x, pts[i].y); ctx.lineTo(pts[j].x, pts[j].y); ctx.stroke()
        }
      }
    }
    for (const p of pts) {
      ctx.fillStyle = 'rgba(94, 234, 212, 0.7)'
      ctx.beginPath(); ctx.arc(p.x, p.y, 1.8, 0, Math.PI * 2); ctx.fill()
    }
    raf = requestAnimationFrame(draw)
  }
  draw()
  return () => window.removeEventListener('resize', resize)
}
let cleanup: (() => void) | undefined
onMounted(() => { cleanup = initParticles() })
onBeforeUnmount(() => { if (raf) cancelAnimationFrame(raf); if (cleanup) cleanup() })
</script>

<template>
  <div class="login-wrap">
    <canvas ref="canvas" class="particles"></canvas>
    <n-card class="login-card" title="sing-box 管理面板">
      <n-form @submit.prevent="onLogin">
        <n-form-item label="用户名">
          <n-input v-model:value="username" placeholder="用户名" @keyup.enter="onLogin" />
        </n-form-item>
        <n-form-item label="密码">
          <n-input v-model:value="password" type="password" placeholder="密码"
                   show-password-on="click" @keyup.enter="onLogin" />
        </n-form-item>
        <n-button type="primary" block :loading="loading" @click="onLogin">登录</n-button>
      </n-form>
    </n-card>
  </div>
</template>

<style scoped>
.login-wrap {
  position: relative; min-height: 100vh;
  display: flex; align-items: center; justify-content: center; padding: 20px;
  overflow: hidden;
}
.particles {
  position: absolute; inset: 0; width: 100%; height: 100%;
  z-index: 0; pointer-events: none;
}
.login-card {
  position: relative; z-index: 1; width: 100%; max-width: 380px;
  backdrop-filter: blur(8px);
  box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.18),
              0 18px 50px rgba(0, 0, 0, 0.45),
              0 0 60px rgba(14, 165, 164, 0.15);
  animation: cardin 0.6s cubic-bezier(0.22, 1, 0.36, 1);
}
@keyframes cardin {
  from { opacity: 0; transform: translateY(20px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
</style>
