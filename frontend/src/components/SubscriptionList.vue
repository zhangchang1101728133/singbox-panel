<script setup>
import { ref, computed } from 'vue'
import {
  useMessage, useDialog,
  NCard, NButton, NSpace, NEmpty, NList, NListItem, NText, NModal,
} from 'naive-ui'
import QrcodeVue from 'qrcode.vue'
import { api } from '../api/client'
import SubFormModal from './SubFormModal.vue'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  subs: { type: Array, default: () => [] },
  nodes: { type: Array, default: () => [] },
  serverIp: String,
})
const emit = defineEmits(['refresh'])
const message = useMessage()
const dialog = useDialog()
const collapsed = ref(false)

const formRef = ref(null)
const origin = computed(() => window.location.origin)

function subUrl(sub) {
  const name = sub.slug || sub.token
  return `${origin.value}/sub/download/${name}`
}

// 二维码弹窗
const qrShow = ref(false)
const qrUrl = ref('')
const qrName = ref('')
function openQr(sub) {
  qrUrl.value = subUrl(sub)
  qrName.value = sub.name
  qrShow.value = true
}

function openAdd() { formRef.value.openAdd() }
function openEdit(sub) { formRef.value.openEdit(sub) }

async function copyUrl(sub) {
  const url = subUrl(sub)
  try {
    await navigator.clipboard.writeText(url)
    message.success('订阅链接已复制')
  } catch {
    // 降级：clipboard 不可用（http 非安全上下文）时用临时输入框
    const ta = document.createElement('textarea')
    ta.value = url; document.body.appendChild(ta); ta.select()
    document.execCommand('copy'); ta.remove()
    message.success('订阅链接已复制')
  }
}

function fixModalFocus() {
  // naive modal 内部有一个 aria-hidden="true" 的隐藏 div 会抢焦点
  // 导致浏览器报 "Blocked aria-hidden on an element because its descendant retained focus"
  // 弹窗打开后把焦点移到弹窗标题上，绕开这个问题
  const el = document.querySelector('.n-card')
  if (el) el.focus({ preventScroll: true })
}

function confirmDelete(sub) {
  dialog.warning({
    title: '删除订阅',
    content: `确定删除订阅「${sub.name}」？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.del(`/sub/api/${sub.id}`)
        message.success('订阅已删除')
        emit('refresh')
      } catch (e) {
        message.error(e.message)
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
          订阅 ({{ subs.length }})
        </span>
        <n-button size="small" type="primary" @click.stop="openAdd">创建订阅</n-button>
      </div>
    </template>

    <div v-show="!collapsed">
    <div v-if="!subs.length" class="empty">
      <div class="empty-ico">🔗</div>
      <div class="empty-title">还没有订阅</div>
      <div class="empty-desc">创建订阅后，用链接或扫码导入客户端</div>
      <n-button type="primary" size="small" @click="openAdd">创建第一个订阅</n-button>
    </div>

    <n-list v-else hoverable>
      <n-list-item v-for="sub in subs" :key="sub.id">
        <div class="sub-info">
          <span class="sub-accent"></span>
          <div class="sub-text">
            <div class="sname">{{ sub.name }}</div>
            <div class="surl">{{ subUrl(sub) }}</div>
          </div>
        </div>
        <template #suffix>
          <div class="row-actions">
            <n-button size="small" quaternary circle type="primary" @click="copyUrl(sub)">
              <template #icon><app-icon name="copy" :size="16" /></template>
            </n-button>
            <n-button size="small" quaternary circle @click="openQr(sub)">
              <template #icon><app-icon name="qr" :size="16" /></template>
            </n-button>
            <n-button size="small" quaternary circle @click="openEdit(sub)">
              <template #icon><app-icon name="edit" :size="16" /></template>
            </n-button>
            <n-button size="small" quaternary circle type="error" @click="confirmDelete(sub)">
              <template #icon><app-icon name="trash" :size="16" /></template>
            </n-button>
          </div>
        </template>
      </n-list-item>
    </n-list>
    </div>

    <sub-form-modal ref="formRef" :nodes="nodes" @refresh="emit('refresh')" />

    <!-- 二维码弹窗 -->
    <n-modal v-model:show="qrShow" preset="card" title="扫码导入订阅" style="max-width: 320px">
      <div class="qr-wrap">
        <div class="qr-box">
          <qrcode-vue :value="qrUrl" :size="220" level="M" render-as="svg" />
        </div>
        <n-text depth="3" style="font-size: 12px; text-align: center; word-break: break-all">{{ qrName }}</n-text>
      </div>
    </n-modal>
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
/* 根因修复：内容区加 min-width:0，长 URL 才会截断而非把按钮挤出屏幕 */
:deep(.n-list-item) { align-items: center; }
:deep(.n-list-item__main) { min-width: 0; }
:deep(.n-list-item__suffix) { display: flex; align-items: center; flex-shrink: 0; }
.sub-info { display: flex; align-items: center; gap: 10px; min-width: 0; }
.sub-accent {
  width: 3px; align-self: stretch; min-height: 34px; border-radius: 3px; flex-shrink: 0;
  background: linear-gradient(180deg, #2dd4bf, #6366f1);
  box-shadow: 0 0 10px rgba(45, 212, 191, 0.5);
}
.sub-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.sname { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.surl { font-size: 12px; opacity: 0.55; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row-actions { flex-shrink: 0; display: flex; align-items: center; gap: 2px; }
.empty { text-align: center; padding: 32px 16px; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.empty-ico { font-size: 40px; opacity: 0.85; }
.empty-title { font-size: 15px; font-weight: 600; }
.empty-desc { font-size: 12px; opacity: 0.6; margin-bottom: 6px; }
.qr-wrap { display: flex; flex-direction: column; align-items: center; gap: 14px; }
.qr-box { background: #fff; padding: 14px; border-radius: 12px; box-shadow: 0 4px 18px rgba(0,0,0,0.3); }
</style>

