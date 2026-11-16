<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  useMessage, NModal, NForm, NFormItem, NInput, NInputNumber,
  NButton, NSpace, NText, NAlert, NSwitch, NDivider,
} from 'naive-ui'
import { api, errMsg } from '../api/client'
import type { TrafficInfo, OfficialStatus } from '../types/index'

const emit = defineEmits(['refresh'])
const message = useMessage()

const show = ref(false)
const saving = ref(false)
const syncing = ref(false)
const info = ref<TrafficInfo | null>(null)

const totalGb = ref<number | null>(null)
const resetDay = ref<number | null>(null)
const resetTime = ref('10:31')
const alignGb = ref<number | null>(null)

// ── 官方数据源 ──
const official = ref<OfficialStatus | null>(null)
const oEnabled = ref(false)
const oUsername = ref('')
const oPassword = ref('')
const oProductId = ref('')
const oInterval = ref<number | null>(30)
const oTesting = ref(false)

const GiB = 1024 ** 3
const toGb = (bytes: number) => bytes / GiB

const usedText = computed(() => {
  if (!info.value) return '—'
  const used = toGb(info.value.upload + info.value.download)
  const total = toGb(info.value.total)
  return total > 0
    ? `${used.toFixed(2)} GB / ${total.toFixed(2)} GB`
    : `${used.toFixed(2)} GB（不限量）`
})

const periodText = computed(() => {
  if (!info.value) return '—'
  const fmt = (v: string) => v.replace('T', ' ').slice(0, 16)
  return `${fmt(info.value.period_start)} → ${fmt(info.value.period_end)}`
})

async function load() {
  try {
    const [d, st] = await Promise.all([
      api.get<TrafficInfo>('/api/traffic'),
      api.get<OfficialStatus>('/api/official/status'),
    ])
    info.value = d
    totalGb.value = d.total_gb
    resetDay.value = d.reset_day
    resetTime.value = d.reset_time
    alignGb.value = Number(toGb(d.upload + d.download).toFixed(2))

    official.value = st
    oEnabled.value = st.enabled
    oUsername.value = st.username
    oProductId.value = st.product_id
    oInterval.value = st.interval_min
    oPassword.value = ''
  } catch (e) {
    message.error(errMsg(e))
  }
}

async function saveOfficial(showToast = true) {
  await api.put<OfficialStatus>('/api/official/config', {
    enabled: oEnabled.value,
    username: oUsername.value || undefined,
    password: oPassword.value || undefined,
    product_id: oProductId.value || undefined,
    interval_min: oInterval.value ?? 30,
  })
  oPassword.value = ''
  official.value = await api.get<OfficialStatus>('/api/official/status')
  if (showToast) message.success('官方数据源已保存')
}

async function testOfficial() {
  if (!oUsername.value && !official.value?.has_password) {
    message.warning('请先填写账号')
    return
  }
  if (!oPassword.value && !official.value?.has_password) {
    message.warning('请先填写密码')
    return
  }
  oTesting.value = true
  try {
    await api.post<unknown>('/api/official/sync', {
      username: oUsername.value || undefined,
      password: oPassword.value || undefined,
      product_id: oProductId.value || undefined,
      save: true,
    })
    message.success('抓取成功，已按官方数据更新')
    oPassword.value = ''
    await load()
    emit('refresh')
  } catch (e) {
    message.error(errMsg(e), { duration: 8000 })
  } finally {
    oTesting.value = false
  }
}

function open() {
  show.value = true
  load()
}

async function saveSettings() {
  saving.value = true
  try {
    const d = await api.put<TrafficInfo>('/api/traffic/settings', {
      total_gb: totalGb.value ?? 0,
      reset_day: resetDay.value ?? 15,
      reset_time: resetTime.value || '10:31',
    })
    info.value = d
    message.success('设置已保存')
    emit('refresh')
    show.value = false
  } catch (e) {
    message.error(errMsg(e))
  } finally {
    saving.value = false
  }
}

async function doSync() {
  if (alignGb.value === null || alignGb.value < 0) {
    message.warning('请输入已用流量')
    return
  }
  syncing.value = true
  try {
    const d = await api.post<TrafficInfo>('/api/traffic/sync', { used_gb: alignGb.value })
    info.value = d
    alignGb.value = Number(toGb(d.upload + d.download).toFixed(2))
    message.success('已同步')
    emit('refresh')
  } catch (e) {
    message.error(errMsg(e))
  } finally {
    syncing.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <n-modal v-model:show="show" preset="card" title="流量设置" style="max-width: 500px" :auto-focus="false">
    <n-space vertical :size="14">
      <n-alert type="info" :bordered="false">
        <n-space vertical :size="2">
          <n-text>当前已用：{{ usedText }}</n-text>
          <n-text depth="3" style="font-size: 12px">计费周期：{{ periodText }}</n-text>
        </n-space>
      </n-alert>

      <n-form label-placement="left" label-width="88" :show-feedback="false">
        <n-form-item label="已用流量">
          <n-space align="center" :size="8">
            <n-input-number v-model:value="alignGb" :min="0" :step="0.01" style="width: 128px" />
            <n-text depth="3" style="font-size: 12px">GB</n-text>
            <n-button size="small" :loading="syncing" @click="doSync">按此值同步</n-button>
          </n-space>
        </n-form-item>
        <n-text depth="3" style="font-size: 12px; display: block; margin: 4px 0 14px 88px">
          填服务商控制台显示的已用量，后端按差额补齐
        </n-text>

        <n-form-item label="套餐总量">
          <n-space align="center" :size="8">
            <n-input-number v-model:value="totalGb" :min="0" :step="10" style="width: 128px" />
            <n-text depth="3" style="font-size: 12px">GB，0 表示不限</n-text>
          </n-space>
        </n-form-item>

        <n-form-item label="重置日" style="margin-top: 12px">
          <n-space align="center" :size="8">
            <n-text depth="3" style="font-size: 12px">每月</n-text>
            <n-input-number v-model:value="resetDay" :min="1" :max="28" style="width: 88px" />
            <n-text depth="3" style="font-size: 12px">日</n-text>
          </n-space>
        </n-form-item>

        <n-form-item label="重置时刻" style="margin-top: 12px">
          <n-space align="center" :size="8">
            <n-input v-model:value="resetTime" placeholder="10:31" style="width: 100px" />
            <n-text depth="3" style="font-size: 12px">UTC+8</n-text>
          </n-space>
        </n-form-item>
      </n-form>

      <n-divider style="margin: 4px 0 10px">官方数据源</n-divider>

      <n-space vertical :size="10">
        <n-space align="center" :size="8">
          <n-switch v-model:value="oEnabled" size="small" />
          <n-text style="font-size: 13px">定时抓取服务商控制台的已用流量（覆盖本地估算）</n-text>
        </n-space>

        <n-form label-placement="left" label-width="88" :show-feedback="false">
          <n-form-item label="账号">
            <n-input v-model:value="oUsername" placeholder="野草云登录邮箱" />
          </n-form-item>
          <n-form-item label="密码" style="margin-top: 10px">
            <n-input
              v-model:value="oPassword"
              type="password"
              show-password-on="click"
              :placeholder="official?.has_password ? '已保存，留空表示不修改' : '登录密码'"
            />
          </n-form-item>
          <n-form-item label="产品 ID" style="margin-top: 10px">
            <n-input v-model:value="oProductId" placeholder="如 92421" style="width: 140px" />
            <n-text depth="3" style="font-size: 12px; margin-left: 8px">控制台地址里的 id</n-text>
          </n-form-item>
          <n-form-item label="同步间隔" style="margin-top: 10px">
            <n-input-number v-model:value="oInterval" :min="0" :step="5" style="width: 110px" />
            <n-text depth="3" style="font-size: 12px; margin-left: 8px">分钟，0 = 只在手动触发时抓</n-text>
          </n-form-item>
        </n-form>

        <n-space align="center" :size="8">
          <n-button size="small" type="primary" ghost :loading="oTesting" @click="testOfficial">
            测试并保存
          </n-button>
          <n-button size="small" @click="saveOfficial()">仅保存配置</n-button>
        </n-space>

        <n-text v-if="official?.last_sync" depth="3" style="font-size: 12px">
          上次同步：{{ official.last_sync.replace('T', ' ').slice(0, 19) }}
          <template v-if="official.last_used">
            · 官网已用 {{ (Number(official.last_used) / 1024 ** 3).toFixed(2) }} GB
          </template>
        </n-text>
        <n-alert v-if="official?.last_error" type="warning" :bordered="false" style="font-size: 12px">
          {{ official.last_error }}
        </n-alert>
      </n-space>

      <n-text depth="3" style="font-size: 12px">
        修改重置周期会重新计算周期起点，可能触发一次计数清零。
      </n-text>
    </n-space>

    <template #footer>
      <n-space justify="end">
        <n-button @click="show = false">关闭</n-button>
        <n-button type="primary" :loading="saving" @click="saveSettings">保存设置</n-button>
      </n-space>
    </template>
  </n-modal>
</template>
