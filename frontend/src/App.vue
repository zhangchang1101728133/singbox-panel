<script setup lang="ts">
import { computed } from 'vue'
import { NConfigProvider, NMessageProvider, NDialogProvider, NGlobalStyle, darkTheme, lightTheme, zhCN, dateZhCN } from 'naive-ui'
import { RouterView } from 'vue-router'
import { useThemeStore } from './stores/theme'

const themeStore = useThemeStore()
const naiveTheme = computed(() => (themeStore.mode === 'dark' ? darkTheme : lightTheme))

// Teal 主色 + 更大圆角 + 卡片柔阴影
const themeOverrides = computed(() => {
  const dark = themeStore.mode === 'dark'
  return {
    common: {
      primaryColor: '#0ea5a4',
      primaryColorHover: '#14b8a6',
      primaryColorPressed: '#0c8e8d',
      primaryColorSuppl: '#14b8a6',
      borderRadius: '10px',
      borderRadiusSmall: '7px',
      fontWeightStrong: '600',
    },
    Card: {
      borderRadius: '16px',
      color: dark ? 'rgba(24, 26, 32, 0.72)' : 'rgba(255, 255, 255, 0.82)',
      colorModal: dark ? 'rgba(28, 30, 38, 0.92)' : 'rgba(255, 255, 255, 0.96)',
    },
    Button: { borderRadiusMedium: '10px', borderRadiusSmall: '8px' },
    Tag: { borderRadius: '6px' },
    Modal: { borderRadius: '16px' },
    Input: { borderRadius: '9px' },
  }
})
</script>

<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <n-global-style />
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<style>
* { box-sizing: border-box; }
html, body, #app { margin: 0; padding: 0; min-height: 100vh; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  transition: background 0.4s ease;
}
/* 暗色背景：青绿光晕 + 深底 */
html[data-theme='dark'] body {
  color-scheme: dark;
  background:
    radial-gradient(1100px 600px at 18% -8%, rgba(14, 165, 164, 0.16), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, rgba(20, 184, 166, 0.10), transparent 55%),
    radial-gradient(800px 800px at 50% 120%, rgba(99, 102, 241, 0.10), transparent 60%),
    #0b0d12;
  background-attachment: fixed;
  background-size: 200% 200%, 200% 200%, 200% 200%, 100% 100%;
  animation: bgflow 24s ease-in-out infinite;
}
/* 亮色背景：清爽浅青底 */
html[data-theme='light'] body {
  color-scheme: light;
  background:
    radial-gradient(1100px 600px at 18% -8%, rgba(14, 165, 164, 0.12), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, rgba(99, 102, 241, 0.08), transparent 55%),
    radial-gradient(800px 800px at 50% 120%, rgba(20, 184, 166, 0.08), transparent 60%),
    #f1f5f9;
  background-attachment: fixed;
  background-size: 200% 200%, 200% 200%, 200% 200%, 100% 100%;
  animation: bgflow 24s ease-in-out infinite;
}
@keyframes bgflow {
  0%   { background-position: 0% 0%, 100% 0%, 50% 100%, 0 0; }
  50%  { background-position: 30% 20%, 70% 10%, 40% 80%, 0 0; }
  100% { background-position: 0% 0%, 100% 0%, 50% 100%, 0 0; }
}
/* 滚动条 */
::-webkit-scrollbar { width: 8px; height: 8px; }
html[data-theme='dark'] ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 4px; }
html[data-theme='dark'] ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
html[data-theme='light'] ::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.15); border-radius: 4px; }
html[data-theme='light'] ::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.25); }

/* 全局按钮点击波纹 */
.global-ripple {
  position: absolute; border-radius: 50%; transform: scale(0);
  background: rgba(255, 255, 255, 0.45);
  pointer-events: none; z-index: 1;
  animation: ripple-anim 0.6s ease-out;
}
@keyframes ripple-anim {
  to { transform: scale(2.2); opacity: 0; }
}

/* 手机端：默认弹窗居中；仅当键盘弹出(body.kb-open)时上移，避免输入框被遮挡 */
@media (max-width: 600px) {
  body.kb-open .n-modal-scroll-content { align-items: flex-start !important; }
  body.kb-open .n-modal-scroll-content > .n-modal,
  body.kb-open .n-modal-scroll-content > .n-card {
    margin-top: 16px !important;
    align-self: flex-start !important;
    transition: margin-top 0.2s ease;
  }
}
</style>
