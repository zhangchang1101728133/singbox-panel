<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import {
  useMessage,
  NModal, NForm, NFormItem, NInput, NInputNumber, NSelect, NButton, NSpace,
  NInputGroup, NSwitch, NText, NAlert,
} from 'naive-ui'
import { api, errMsg } from '../api/client'
import type { MessageResponse, Node, NodeConfig, ProtocolField, ProtocolsResponse, Protocol } from '../types/index'

const emit = defineEmits(['refresh'])
const message = useMessage()

const protocols = ref<Protocol[]>([])
const coreVersion = ref<string | null>(null)

const show = ref(false)
const editId = ref<number | null>(null)
const submitting = ref(false)
const title = computed(() => (editId.value ? '编辑节点' : '添加节点'))

const f = reactive<{
  name: string
  type: string
  server: string
  port: number | null
  cfg: NodeConfig   // 扁平化存储，key 为协议注册表里的点号路径
}>({
  name: '',
  type: 'vless',
  server: '',
  port: null,
  cfg: {},
})

const protocolOptions = computed(() =>
  protocols.value.map((p) => ({
    label: p.available ? p.label : `${p.label}（需 sing-box ${p.min_version}+）`,
    value: p.id,
    disabled: !p.available,
  }))
)

const currentFields = computed(() => {
  const p = protocols.value.find((x) => x.id === f.type)
  return p ? p.fields : []
})

// ── 点号路径读写 ────────────────────────────────────────────
function getPath(obj: NodeConfig, path: string): any {
  return path.split('.').reduce<any>((acc, k) => (acc == null ? acc : acc[k]), obj)
}

function setPath(obj: NodeConfig, path: string, value: unknown) {
  const keys = path.split('.')
  let cur: NodeConfig = obj
  keys.forEach((k, i) => {
    if (i === keys.length - 1) cur[k] = value
    else {
      if (typeof cur[k] !== 'object' || cur[k] === null) cur[k] = {}
      cur = cur[k]
    }
  })
}

// 随机值由后端生成：Shadowsocks 2022 的密钥格式取决于加密方式，规则不放在前端
async function generate(fld: ProtocolField) {
  try {
    const r = await api.post<{ value: string }>(`/api/protocols/${f.type}/random`, {
      field: fld.key,
      config: buildConfig(),
    })
    f.cfg[fld.key] = r.value
  } catch (e) {
    message.error(`生成失败：${errMsg(e)}`)
  }
}

function defaultPort(type: string) {
  const p = protocols.value.find((x) => x.id === type)
  return p ? p.default_port : 44300
}

function reset() {
  f.name = ''
  f.type = 'vless'
  f.server = ''
  f.port = null
  f.cfg = {}
}

function applyDefaults() {
  // 切换协议时，按注册表字段重置表单值
  const values: NodeConfig = {}
  currentFields.value.forEach((fld) => {
    if (fld.default !== undefined) values[fld.key] = fld.default
    else if (fld.type === 'bool') values[fld.key] = false
    else if (fld.type === 'number') values[fld.key] = null
    else values[fld.key] = ''
  })
  f.cfg = values
  f.port = defaultPort(f.type)
}

function openAdd() {
  reset()
  editId.value = null
  f.type = protocols.value.find((p) => p.available)?.id ?? 'vless'
  applyDefaults()
  show.value = true
}

function openEdit(node: Node) {
  reset()
  editId.value = node.id
  f.name = node.name
  f.type = node.type
  f.server = node.server
  f.port = node.server_port
  const c: NodeConfig = node.config || {}
  const values: NodeConfig = {}
  currentFields.value.forEach((fld) => {
    const v = getPath(c, fld.key)
    if (v === undefined || v === null) {
      if (fld.type === 'bool') values[fld.key] = false
      else if (fld.type === 'number') values[fld.key] = null
      else values[fld.key] = ''
    } else {
      values[fld.key] = v
    }
  })
  f.cfg = values
  show.value = true
}

function buildConfig(): NodeConfig {
  const out: NodeConfig = {}
  currentFields.value.forEach((fld) => {
    let v = f.cfg[fld.key]
    if (v === '' || v === null || v === undefined) return
    if (fld.type === 'number') v = Number(v)
    setPath(out, fld.key, v)
  })
  return out
}

defineExpose({ openAdd, openEdit })

async function loadProtocols() {
  try {
    const r = await api.get<ProtocolsResponse>('/api/protocols')
    protocols.value = r.protocols
    coreVersion.value = r.core_version
  } catch (e) {
    message.error(`协议列表加载失败：${errMsg(e)}`)
  }
}

onMounted(loadProtocols)

async function submit() {
  if (!f.name.trim() || !f.server.trim() || !f.port) {
    message.warning('请填写名称、地址和端口')
    return
  }
  if (f.port < 1 || f.port > 65535) { message.warning('端口范围 1-65535'); return }
  submitting.value = true
  const payload = {
    name: f.name.trim(), type: f.type, server: f.server.trim(),
    server_port: f.port, enabled: true, config: buildConfig(),
  }
  try {
    if (editId.value) {
      await api.put<MessageResponse>(`/nodes/api/${editId.value}`, payload)
      message.success('节点已更新')
    } else {
      await api.post<MessageResponse>('/nodes/api/add', payload)
      message.success('节点已添加')
    }
    show.value = false
    emit('refresh')
  } catch (e) {
    message.error(errMsg(e))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <n-modal v-model:show="show" preset="card" :title="title" style="max-width: 460px" :bordered="false" :auto-focus="false" class="form-modal">
    <n-form>
      <n-form-item label="节点名称">
        <n-input v-model:value="f.name" placeholder="节点名称" />
      </n-form-item>
      <n-form-item label="协议类型">
        <n-select
          v-model:value="f.type"
          :options="protocolOptions"
          :disabled="!!editId"
          @update:value="applyDefaults"
        />
      </n-form-item>
      <n-form-item label="服务器地址">
        <n-input v-model:value="f.server" placeholder="IP 或域名" />
      </n-form-item>
      <n-form-item label="端口">
        <n-input-number v-model:value="f.port" :min="1" :max="65535" style="width: 100%" />
      </n-form-item>

      <n-alert v-if="coreVersion === null" type="warning" :bordered="false" style="margin-bottom: 12px">
        无法读取 sing-box 版本，协议可用性按最新版判断
      </n-alert>

      <template v-for="fld in currentFields" :key="fld.key">
        <n-form-item v-if="fld.type === 'bool'" :label="fld.label">
          <n-switch v-model:value="f.cfg[fld.key]" />
        </n-form-item>

        <n-form-item v-else-if="fld.type === 'select'" :label="fld.label">
          <n-select
            v-model:value="f.cfg[fld.key]"
            :options="(fld.options || []).map((o) => ({ label: o || '（无）', value: o }))"
          />
        </n-form-item>

        <n-form-item v-else-if="fld.type === 'number'" :label="fld.label">
          <n-input-number v-model:value="f.cfg[fld.key]" style="width: 100%" />
        </n-form-item>

        <n-form-item v-else :label="fld.label">
          <n-input-group>
            <n-input v-model:value="f.cfg[fld.key]" :placeholder="fld.label" />
            <n-button v-if="fld.gen" @click="generate(fld)">生成</n-button>
          </n-input-group>
        </n-form-item>
      </template>

      <n-text v-if="!currentFields.length" depth="3" style="font-size: 12px">
        该协议无需额外参数
      </n-text>
    </n-form>

    <template #footer>
      <n-space justify="end">
        <n-button @click="show = false">取消</n-button>
        <n-button type="primary" :loading="submitting" @click="submit">
          {{ editId ? '保存' : '添加' }}
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>
