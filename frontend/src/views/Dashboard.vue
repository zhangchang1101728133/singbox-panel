<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  useMessage, useDialog,
  NLayout, NLayoutHeader, NLayoutContent, NButton, NSpace, NText, NIcon,
} from 'naive-ui'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import NodeList from '../components/NodeList.vue'
import SubscriptionList from '../components/SubscriptionList.vue'
import QuickActions from '../components/QuickActions.vue'
import AppIcon from '../components/AppIcon.vue'
import StatsBar from '../components/StatsBar.vue'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const auth = useAuthStore()
const themeStore = useThemeStore()

const nodes = ref([])
const subs = ref([])
const serverIp = ref('')
const stats = ref({ total_nodes: 0, active_nodes: 0, total_subs: 0, active_subs: 0 })
const loading = ref(false)

async function loadAll() {
  loading.value = true
  try {
    const [n, s, info, st] = await Promise.all([
      api.get('/nodes/api'),
      api.get('/sub/api'),
      api.get('/api/server-info'),
      api.get('/api/stats'),
    ])
    nodes.value = n
    subs.value = s
    serverIp.value = info.server_ip
    stats.value = st
  } catch (e) {
    message.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function onLogout() {
  await auth.logout()
  router.push({ name: 'login' })
}

onMounted(loadAll)
</script>

<template>
  <n-layout style="min-height: 100vh; background: transparent">
    <n-layout-header class="header">
      <div class="header-inner">
        <div class="brand">
          <span class="logo">◆</span>
          <span class="brand-name">sing-box</span>
        </div>
        <n-space :size="10" align="center">
          <n-button quaternary circle @click="themeStore.toggle()"
                    :title="themeStore.mode === 'dark' ? '切换亮色' : '切换暗色'">
            <template #icon>{{ themeStore.mode === 'dark' ? '☀' : '☾' }}</template>
          </n-button>
          <span class="user-chip">{{ auth.user?.username }}</span>
          <n-button quaternary circle type="error" title="登出" @click="onLogout">
            <template #icon><app-icon name="power" :size="16" /></template>
          </n-button>
        </n-space>
      </div>
    </n-layout-header>

    <n-layout-content class="content" style="background: transparent">
      <div class="container">
        <stats-bar :stats="stats" :server-ip="serverIp" />

        <quick-actions
          :has-nodes="nodes.length > 0"
          :server-ip="serverIp"
          @refresh="loadAll" />

        <node-list
          :nodes="nodes"
          :loading="loading"
          @refresh="loadAll" />

        <subscription-list
          :subs="subs"
          :nodes="nodes"
          :server-ip="serverIp"
          @refresh="loadAll" />
      </div>
    </n-layout-content>
  </n-layout>
</template>

<style scoped>
.header {
  position: sticky; top: 0; z-index: 10;
  backdrop-filter: blur(12px);
  background: rgba(11, 13, 18, 0.6);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.header-inner {
  max-width: 760px; margin: 0 auto; padding: 14px 16px;
  display: flex; align-items: center; justify-content: space-between;
}
.brand { display: flex; align-items: center; gap: 8px; }
.logo {
  font-size: 18px; color: #0ea5a4;
  text-shadow: 0 0 14px rgba(14, 165, 164, 0.7);
}
.brand-name {
  font-size: 17px; font-weight: 700; letter-spacing: 0.3px;
  background: linear-gradient(90deg, #2dd4bf, #5eead4, #6366f1, #2dd4bf);
  background-size: 250% 100%;
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer 5s linear infinite;
}
@keyframes shimmer {
  0% { background-position: 0% 0%; }
  100% { background-position: 250% 0%; }
}
.user-chip {
  font-size: 12px; color: rgba(255,255,255,0.65);
  padding: 3px 10px; border-radius: 999px;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08);
}
.content { padding: 16px 0 48px; }
.container { max-width: 760px; margin: 0 auto; padding: 0 16px; display: flex; flex-direction: column; gap: 16px; }
/* 卡片入场 + hover 悬浮 */
.container > :deep(.n-card) {
  opacity: 0; transform: translateY(16px);
  animation: cardrise 0.6s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}
.container > :deep(.n-card):hover {
  transform: translateY(-3px);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.28);
}
.container > :deep(.n-card):nth-child(2) { animation-delay: 0.10s; }
.container > :deep(.n-card):nth-child(3) { animation-delay: 0.18s; }
.container > :deep(.n-card):nth-child(4) { animation-delay: 0.26s; }
@keyframes cardrise {
  to { opacity: 1; transform: translateY(0); }
}
</style>

