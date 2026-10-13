import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

// 极简深色主题：全局启用 Element Plus dark 变量
document.documentElement.classList.add('dark')

// ECharts
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkPointComponent, MarkLineComponent, DataZoomComponent } from 'echarts/components'
import VueECharts from 'vue-echarts'
use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, MarkPointComponent, MarkLineComponent, DataZoomComponent])

import './style.css'

import App from './App.vue'
import router from './router'
import { loadDemoFlag } from './api/demo'

const app = createApp(App)

app.use(ElementPlus)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 先取「演示模式」标志，再安装路由并挂载：
// 路由守卫在 install 时会立即做一次初始导航，必须确保此刻 isDemo 已就绪，
// 否则直接访问 /auto-factor-lab 不会被重定向。
loadDemoFlag().finally(() => {
  app.use(router)
  app.mount('#app')
})
