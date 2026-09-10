<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  useMessage, useDialog,
  NCard, NSpace, NButton, NModal, NForm, NFormItem, NInput, NText, NCheckbox,
} from 'naive-ui'
import { api } from '../api/client'
import AppIcon from './AppIcon.vue'
import type { ProtocolsResponse, Protocol, SingboxVersion } from '../types/index'

const props = defineProps({
  hasNodes: Boolean,
  serverIp: String,
})
const emit = defineEmits(['refresh'])
const message = useMessage()
const dialog = useDialog()

const protocols = ref<Protocol[]>([])
const coreVersion = ref<string | null>(null)

// ── 一键配置 ──
const quickShow = ref(false)
const qServer = ref('')
const qSni = ref('www.taobao.com')
const qSelected = ref<string[]>([])
const quickLoading = ref(false)

const availableProtocols = computed(() => protocols.value.filter((p) => p.available))

function openQuick() {
  qServer.value = props.serverIp || ''
  qSni.value = 'www.taobao.com'
  qSelected.value = availableProtocols.value.map((p) => p.id)
  quickShow.value = true
}

async function doQuick() {
  if (!qServer.value.trim()) { message.warning('请输入服务器地址'); return }
  if (!qSelected.value.length) { message.warning('请至少选择一个协议'); return }
  quickLoading.value = true
  try {
    const r = await api.post('/api/quick-setup', {
      server: qServer.value.trim(),
      sni: qSni.value.trim() || 'www.taobao.com',
      protocols: qSelected.value,
    })
    message.success(r.message || '配置成功')
    quickShow.value = false
    emit('refresh')
  } catch (e) {
    message.error(e.message)
  } finally {
    quickLoading.value = false
  }
}

// ── 导出配置 ──
async function doExport() {
  try {
    const data = await api.get('/api/export')
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `singbox-config-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success('配置已导出')
  } catch (e) {
    message.error(e.message)
  }
}

// ── 清空配置 ──
function confirmClear() {
  dialog.error({
    title: '清空配置',
    content: '将删除所有节点和订阅，sing-box 恢复默认状态。此操作不可恢复！',
    positiveText: '确认清空',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.post('/api/clear-all')
        message.success('已清空')
        emit('refresh')
      } catch (e) {
        message.error(e.message)
      }
    },
  })
}

// ── 检查更新 ──
const updateShow = ref(false)
const updateInfo = ref('正在检查...')
const updateAvailable = ref(false)
const updating = ref(false)
const updateLog = ref<string[]>([])

async function openUpdate() {
  updateShow.value = true
  updateInfo.value = '正在检查...'
  updateAvailable.value = false
  updateLog.value = []
  try {
    const r = await api.get<SingboxVersion>('/api/singbox/version')
    if (r.error) {
      updateInfo.value = r.error
      return
    }
    if (r.update_available) {
      updateInfo.value = `发现新版本 ${r.latest_version}，当前 ${r.version}`
      updateAvailable.value = true
    } else {
      updateInfo.value = `已是最新版本 ${r.version}`
    }
  } catch (e) {
    updateInfo.value = `检查失败：${e.message}`
  }
}

async function doUpdate() {
  updating.value = true
  updateInfo.value = '正在拉取镜像并重建容器，请稍候...'
  updateLog.value = []
  try {
    const r = await api.post('/api/singbox/update')
    updateInfo.value = r.message || '更新成功'
    updateLog.value = r.log || []
    message.success('sing-box 已更新')
    updateAvailable.value = false
  } catch (e) {
    updateInfo.value = `更新失败：${e.message}`
  } finally {
    updating.value = false
  }
}

function toggleProtocol(id, checked) {
  if (checked) {
    if (!qSelected.value.includes(id)) qSelected.value.push(id)
  } else {
    qSelected.value = qSelected.value.filter((x) => x !== id)
  }
}

async function loadProtocols() {
  try {
    const r = await api.get<ProtocolsResponse>('/api/protocols')
    protocols.value = r.protocols
    coreVersion.value = r.core_version
  } catch {
    // 静默失败：一键配置仍可用，只是没有可选协议列表
  }
}

onMounted(loadProtocols)
</script>

<template>
  <n-card title="快捷操作" size="small">
    <div class="qa-grid">
      <n-button type="primary" @click="openQuick">
        <template #icon><app-icon name="bolt" :size="17" /></template>
        一键配置
      </n-button>
      <n-button @click="doExport">
        <template #icon><app-icon name="download" :size="17" /></template>
        导出配置
      </n-button>
      <n-button @click="openUpdate">
        <template #icon><app-icon name="refresh" :size="17" /></template>
        检查更新
      </n-button>
      <n-button type="error" ghost @click="confirmClear">
        <template #icon><app-icon name="trash" :size="17" /></template>
        清空配置
      </n-button>
    </div>

    <!-- 一键配置弹窗 -->
    <n-modal v-model:show="quickShow" preset="card" title="一键配置" style="max-width: 420px" :auto-focus="false">
      <n-form>
        <n-form-item label="服务器地址">
          <n-input v-model:value="qServer" placeholder="公网 IP 或域名" />
        </n-form-item>
        <n-form-item label="伪装域名 (SNI)">
          <n-input v-model:value="qSni" placeholder="www.taobao.com" />
        </n-form-item>
        <n-form-item label="协议">
          <n-space vertical :size="6" style="width: 100%">
            <n-checkbox
              v-for="p in availableProtocols"
              :key="p.id"
              :value="p.id"
              :checked="qSelected.includes(p.id)"
              @update:checked="(v) => toggleProtocol(p.id, v)"
            >
              {{ p.label }}
            </n-checkbox>
            <n-text depth="3" style="font-size: 12px" v-if="!availableProtocols.length">
              正在加载协议列表...
            </n-text>
          </n-space>
        </n-form-item>
      </n-form>
      <n-text depth="3" style="font-size: 12px">
        将生成 {{ qSelected.length }} 个协议节点和默认订阅
      </n-text>
      <template #footer>
        <n-space justify="end">
          <n-button @click="quickShow = false">取消</n-button>
          <n-button type="primary" :loading="quickLoading" @click="doQuick">开始配置</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 检查更新弹窗 -->
    <n-modal v-model:show="updateShow" preset="card" title="检查更新" style="max-width: 420px" :auto-focus="false">
      <n-text>{{ updateInfo }}</n-text>
      <ul v-if="updateLog.length" class="update-log">
        <li v-for="(line, i) in updateLog" :key="i">{{ line }}</li>
      </ul>
      <template #footer>
        <n-space justify="end">
          <n-button @click="updateShow = false">关闭</n-button>
          <n-button v-if="updateAvailable" type="primary" :loading="updating" @click="doUpdate">立即更新</n-button>
        </n-space>
      </template>
    </n-modal>
  </n-card>
</template>

<style scoped>
.qa-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.qa-grid :deep(.n-button) { width: 100%; }
/* 宽屏：四个按钮一行平铺 */
@media (min-width: 600px) {
  .qa-grid { grid-template-columns: repeat(4, 1fr); }
}
.update-log {
  margin: 10px 0 0;
  padding-left: 18px;
  font-size: 12px;
  opacity: 0.7;
}
</style>
