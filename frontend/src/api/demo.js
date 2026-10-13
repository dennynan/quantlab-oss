import { ref } from 'vue'
import api from './index'

// 演示模式标志：由后端 /api/health 的 demo 字段决定。
// 演示站会禁用 RD-Agent（付费 LLM），前端据此隐藏「自动因子挖掘」入口。
export const isDemo = ref(false)

export async function loadDemoFlag() {
  try {
    const res = await api.get('/health')
    isDemo.value = !!(res.data && res.data.demo)
  } catch (e) {
    isDemo.value = false
  }
  return isDemo.value
}
