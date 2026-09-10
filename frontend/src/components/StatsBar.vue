<script setup>
import { computed, ref, watch, onMounted } from 'vue'

const props = defineProps({
  stats: { type: Object, default: () => ({}) },
  serverIp: String,
})

const items = computed(() => [
  { key: 'total_nodes', label: '节点', accent: '#0ea5a4' },
  { key: 'active_nodes', label: '启用', accent: '#22c55e' },
  { key: 'total_subs', label: '订阅', accent: '#6366f1' },
])

// 数字滚动计数动画
const display = ref({ total_nodes: 0, active_nodes: 0, total_subs: 0 })

function animateTo(target) {
  const keys = ['total_nodes', 'active_nodes', 'total_subs']
  keys.forEach((k) => {
    const to = target[k] ?? 0
    const from = display.value[k] ?? 0
    if (from === to) return
    const steps = 24
    let i = 0
    const tick = () => {
      i++
      const p = i / steps
      const eased = 1 - Math.pow(1 - p, 3) // ease-out cubic
      display.value[k] = Math.round(from + (to - from) * eased)
      if (i < steps) requestAnimationFrame(tick)
      else display.value[k] = to
    }
    requestAnimationFrame(tick)
  })
}

watch(() => props.stats, (v) => animateTo(v || {}), { deep: true })
onMounted(() => animateTo(props.stats || {}))
</script>

<template>
  <div class="stats">
    <div v-for="(it, idx) in items" :key="it.label" class="stat"
         :style="{ '--accent': it.accent, 'animation-delay': (idx * 0.08) + 's' }">
      <div class="num">{{ display[it.key] }}</div>
      <div class="lbl">{{ it.label }}</div>
      <div class="glow"></div>
    </div>
  </div>
</template>

<style scoped>
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.stat {
  position: relative; overflow: hidden;
  padding: 18px 16px; border-radius: 16px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.18);
  opacity: 0; transform: translateY(14px);
  animation: rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}
.stat:hover {
  transform: translateY(-4px);
  box-shadow: 0 14px 32px color-mix(in srgb, var(--accent) 30%, rgba(0,0,0,0.3));
}
@keyframes rise {
  to { opacity: 1; transform: translateY(0); }
}
/* hover 时浮现的光晕 */
.glow {
  position: absolute; inset: 0; pointer-events: none; opacity: 0;
  background: radial-gradient(120px 80px at 80% 20%, color-mix(in srgb, var(--accent) 35%, transparent), transparent 70%);
  transition: opacity 0.3s ease;
}
.stat:hover .glow { opacity: 1; }
:global(html[data-theme='dark']) .stat {
  background: linear-gradient(145deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
  border: 1px solid rgba(255,255,255,0.07);
}
:global(html[data-theme='light']) .stat {
  background: linear-gradient(145deg, rgba(255,255,255,0.9), rgba(255,255,255,0.6));
  border: 1px solid rgba(0,0,0,0.06);
}
.stat::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--accent); box-shadow: 0 0 16px var(--accent);
}
.num {
  font-size: 30px; font-weight: 700; line-height: 1;
  color: var(--accent); text-shadow: 0 0 18px color-mix(in srgb, var(--accent) 40%, transparent);
}
.lbl { margin-top: 8px; font-size: 12px; }
:global(html[data-theme='dark']) .lbl { color: rgba(255,255,255,0.55); }
:global(html[data-theme='light']) .lbl { color: rgba(0,0,0,0.5); }
</style>
