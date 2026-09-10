<script setup>
// 统一描线图标（stroke 跟随 currentColor，跨平台一致，无外部依赖）
const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 18 },
})

// 24x24 viewBox，1.8 描边
const PATHS = {
  copy: 'M9 9h10v10H9zM5 15H4V4h11v1',
  qr: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 14h2M20 16v4M14 18h2v2h-2z',
  edit: 'M4 20h4L18.5 9.5a2.1 2.1 0 0 0-3-3L5 17v3z M13.5 6.5l3 3',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  bolt: 'M13 3 4 14h7l-1 7 9-11h-7z',
  download: 'M12 4v10m0 0 4-4m-4 4-4-4M5 20h14',
  refresh: 'M4 12a8 8 0 0 1 14-5l2 2M20 12a8 8 0 0 1-14 5l-2-2M18 4v5h-5M6 20v-5h5',
  power: 'M12 4v8M8 6a7 7 0 1 0 8 0',
  chevron: 'M6 9l6 6 6-6',
}
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
       stroke-linejoin="round" class="app-icon" aria-hidden="true">
    <path :d="PATHS[name]" />
  </svg>
</template>

<style scoped>
.app-icon { display: block; flex-shrink: 0; }
</style>
