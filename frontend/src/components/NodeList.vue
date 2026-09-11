<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  useMessage, useDialog,
  NCard, NButton, NSpace, NTag, NSwitch, NEmpty, NList, NListItem, NText, NSpin,
} from 'naive-ui'
import type { PropType } from 'vue'
import { api, errMsg } from '../api/client'
import type { Node, ProtocolsResponse } from '../types/index'
import NodeFormModal from './NodeFormModal.vue'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  nodes: { type: Array as PropType<Node[]>, default: () => [] },
  loading: Boolean,
})
const emit = defineEmits(['refresh'])
const message = useMessage()
const dialog = useDialog()

const formRef = ref<InstanceType<typeof NodeFormModal> | null>(null)
const collapsed = ref(false)

// 各协议配色
const PROTO_COLORS: Record<string, string> = {
  vless: '#0ea5a4',
  vmess: '#6366f1',
  shadowsocks: '#f59e0b',
  hysteria2: '#ec4899',
  trojan: '#ef4444',
  tuic: '#8b5cf6',
  anytls: '#22c55e',
  snell: '#14b8a6',
}
function protoColor(type: string) { return PROTO_COLORS[type] || '#64748b' }

// 协议缩写（统一短码，等宽显示，让右侧按钮对齐）
// 从后端注册表读取，避免前端再维护一份和 protocols.py 重复的映射
const PROTO_ABBR = ref<Record<string, string>>({})
onMounted(async () => {
  try {
    const r = await api.get<ProtocolsResponse>('/api/protocols')
    PROTO_ABBR.value = Object.fromEntries((r.protocols || []).map((p) => [p.id, p.abbr]))
  } catch {
    // 拉不到就退化成 type 前 3 位，不影响列表渲染
  }
})
function protoAbbr(type: string) { return PROTO_ABBR.value[type] || (type || '').slice(0, 3).toUpperCase() }

function openAdd() { formRef.value?.openAdd() }
function openEdit(node: Node) { formRef.value?.openEdit(node) }

async function toggle(node: Node, val: boolean) {
  try {
    await api.put<{ message: string }>(`/nodes/api/${node.id}`, { enabled: val })
    message.success(val ? '已启用' : '已禁用')
    emit('refresh')
  } catch (e) {
    message.error(errMsg(e))
    emit('refresh')
  }
}

function confirmDelete(node: Node) {
  dialog.warning({
    title: '删除节点',
    content: `确定删除节点「${node.name}」？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.del<{ message: string }>(`/nodes/api/${node.id}`)
        message.success('节点已删除')
        emit('refresh')
      } catch (e) {
        message.error(errMsg(e))
      }
    },
  })
}
</script>

<template>
  <n-card size="small">
    <template #header>
      <div class="card-head" @click="collapsed = !collapsed">
        <span class="head-title">
          <app-icon name="chevron" :size="16" class="chev" :class="{ folded: collapsed }" />
          节点 ({{ nodes.length }})
        </span>
        <n-button size="small" type="primary" @click.stop="openAdd">添加节点</n-button>
      </div>
    </template>

    <n-spin v-show="!collapsed" :show="loading">
      <div v-if="!nodes.length" class="empty">
        <div class="empty-ico">🌐</div>
        <div class="empty-title">还没有节点</div>
        <div class="empty-desc">用「一键配置」快速生成，或手动添加一个节点</div>
        <n-button type="primary" size="small" @click="openAdd">添加第一个节点</n-button>
      </div>
      <n-list v-else hoverable>
        <n-list-item v-for="node in nodes" :key="node.id">
          <template #prefix>
            <n-switch :value="node.enabled" size="small"
                      @update:value="(v) => toggle(node, v)" />
          </template>
          <div class="node-info" :style="{ '--pc': protoColor(node.type) }"
               :class="{ neon: node.enabled }">
            <div class="line1">
              <span class="dot" :class="{ off: !node.enabled }"></span>
              <span class="nname">{{ node.name }}</span>
              <span class="proto" :title="node.type"
                    :style="{ color: protoColor(node.type), borderColor: protoColor(node.type) + '55', background: protoColor(node.type) + '1a' }">
                {{ protoAbbr(node.type) }}
              </span>
            </div>
            <div class="line2">{{ node.server }}:{{ node.server_port }}</div>
          </div>
          <template #suffix>
            <div class="row-actions">
              <n-button size="small" quaternary circle @click="openEdit(node)">
                <template #icon><app-icon name="edit" :size="16" /></template>
              </n-button>
              <n-button size="small" quaternary circle type="error" @click="confirmDelete(node)">
                <template #icon><app-icon name="trash" :size="16" /></template>
              </n-button>
            </div>
          </template>
        </n-list-item>
      </n-list>
    </n-spin>

    <node-form-modal ref="formRef" @refresh="emit('refresh')" />
  </n-card>
</template>

<style scoped>
/* 点击整条标题栏折叠 */
.card-head {
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; user-select: none;
}
.head-title { display: flex; align-items: center; gap: 6px; }
.chev { transition: transform 0.25s ease; opacity: 0.6; }
.chev.folded { transform: rotate(-90deg); }
/* 根因修复：naive 列表项内容区默认无 min-width:0，长文本会把右侧按钮挤出屏幕 */
:deep(.n-list-item) { align-items: center; }
:deep(.n-list-item__main) { min-width: 0; }
:deep(.n-list-item__suffix) { display: flex; align-items: center; flex-shrink: 0; }
.row-actions { flex-shrink: 0; display: flex; align-items: center; gap: 2px; }
.node-info {
  min-width: 0;
  display: flex; flex-direction: column; gap: 4px;
  padding-left: 10px; position: relative;
}
/* 启用节点：左侧霓虹竖条 */
.node-info::before {
  content: ''; position: absolute; left: 0; top: 2px; bottom: 2px; width: 3px;
  border-radius: 3px; background: #475569; transition: all 0.3s ease;
}
.node-info.neon::before {
  background: var(--pc);
  box-shadow: 0 0 8px var(--pc), 0 0 16px var(--pc);
  animation: neonpulse 2.2s ease-in-out infinite;
}
@keyframes neonpulse {
  0%, 100% { opacity: 0.7; box-shadow: 0 0 6px var(--pc), 0 0 12px var(--pc); }
  50% { opacity: 1; box-shadow: 0 0 10px var(--pc), 0 0 22px var(--pc); }
}
.line1 {
  display: flex; align-items: center; gap: 7px;
  min-width: 0; white-space: nowrap; overflow: hidden;
}
.nname {
  font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.line2 { font-size: 12px; opacity: 0.55; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #22c55e; box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.6);
  animation: pulse 2s infinite; flex-shrink: 0;
}
.dot.off { background: #64748b; animation: none; box-shadow: none; }
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.5); }
  70% { box-shadow: 0 0 0 6px rgba(34, 197, 94, 0); }
  100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
}
.proto {
  font-size: 11px; font-weight: 700; padding: 1px 0; flex-shrink: 0;
  border-radius: 6px; border: 1px solid; letter-spacing: 0.5px;
  width: 42px; text-align: center; box-sizing: border-box;
}
.empty { text-align: center; padding: 32px 16px; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.empty-ico { font-size: 40px; opacity: 0.85; }
.empty-title { font-size: 15px; font-weight: 600; }
.empty-desc { font-size: 12px; opacity: 0.6; margin-bottom: 6px; }
</style>

