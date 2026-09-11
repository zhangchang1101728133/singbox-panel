/// <reference types="vite/client" />

// 让 TS 认识 .vue 单文件组件的导入。
// 具体类型由 vue-tsc 从各个 SFC 的 <script setup lang="ts"> 里推导，
// 这里只做模块声明兜底。
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}
