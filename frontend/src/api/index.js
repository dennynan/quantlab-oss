import axios from 'axios'

// 开源版：无登录，无需注入 token
const api = axios.create({
  baseURL: '/api',
  timeout: 60000  // 回测可能耗时较长
})

// ── 匿名访客标识 ──
// 演示站没有登录，但「回测任务」这类用户产生的数据需要区分归属，
// 否则多人访问同一个站点时会互相看到对方的结果。这里在浏览器本地生成一个
// 随机 id 并持久化，随每个请求以 X-Anon-Id 头发出（后端也支持 Cookie 兜底）。
// 注意：这不是安全边界，只是避免多访客在演示站上互相干扰。
const ANON_KEY = 'ql_anon_id'

function getAnonId() {
  let id = ''
  try {
    id = localStorage.getItem(ANON_KEY) || ''
  } catch (e) {
    id = ''
  }
  if (!id) {
    id = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID().replace(/-/g, '')
      : Math.random().toString(36).slice(2) + Date.now().toString(36)
    try {
      localStorage.setItem(ANON_KEY, id)
    } catch (e) {
      /* 隐私模式下 localStorage 可能不可用，忽略 */
    }
  }
  return id
}

api.interceptors.request.use((config) => {
  config.headers = config.headers || {}
  config.headers['X-Anon-Id'] = getAnonId()
  return config
})

export default api
export { getAnonId }
