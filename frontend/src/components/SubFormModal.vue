<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import type { PropType } from 'vue'
import {
  useMessage,
  NModal, NForm, NFormItem, NInput, NSelect, NButton, NSpace, NText,
} from 'naive-ui'
import { api, errMsg } from '../api/client'
import type { Node, Subscription } from '../types/index'

const props = defineProps({
  nodes: { type: Array as PropType<Node[]>, default: () => [] },
})
const emit = defineEmits(['refresh'])
const message = useMessage()

const show = ref(false)
const editId = ref<number | null>(null)
const submitting = ref(false)
const title = computed(() => (editId.value ? '编辑订阅' : '创建订阅'))

const f = reactive<{ name: string; slug: string; nodeIds: number[] }>({ name: '', slug: '', nodeIds: [] })

// 节点多选项：空数组表示包含全部节点
const nodeOptions = computed(() =>
  props.nodes.map((n) => ({ label: `${n.name} (${n.type})`, value: n.id }))
)

function reset() {
  f.name = ''
  f.slug = ''
  f.nodeIds = []
}

function openAdd() {
  reset()
  editId.value = null
  show.value = true
}

function openEdit(sub: Subscription) {
  reset()
  editId.value = sub.id
  f.name = sub.name
  f.slug = sub.slug || ''
  f.nodeIds = Array.isArray(sub.node_ids) ? [...sub.node_ids] : []
  show.value = true
}

defineExpose({ openAdd, openEdit })

async function submit() {
  if (!f.name.trim()) { message.warning('请输入订阅名称'); return }
  submitting.value = true
  const payload = {
    name: f.name.trim(),
    slug: f.slug.trim(),
    node_ids: f.nodeIds,
  }
  try {
    if (editId.value) {
      await api.put<{ message: string }>(`/sub/api/${editId.value}`, payload)
      message.success('订阅已更新')
    } else {
      await api.post<{ message: string }>('/sub/api/add', payload)
      message.success('订阅已创建')
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
      <n-form-item label="订阅名称">
        <n-input v-model:value="f.name" placeholder="订阅名称" />
      </n-form-item>
      <n-form-item label="链接别名 (可选)">
        <n-input v-model:value="f.slug" placeholder="留空则用默认 token" />
      </n-form-item>
      <n-form-item label="包含节点">
        <n-select v-model:value="f.nodeIds" multiple :options="nodeOptions"
                  placeholder="留空 = 包含全部节点" />
      </n-form-item>
      <n-text depth="3" style="font-size: 12px">不选则订阅包含所有节点</n-text>
    </n-form>

    <template #footer>
      <n-space justify="end">
        <n-button @click="show = false">取消</n-button>
        <n-button type="primary" :loading="submitting" @click="submit">
          {{ editId ? '保存' : '创建' }}
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

