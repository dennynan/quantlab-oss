import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    children: [
      // 合并后的两大工作区
      { path: '', redirect: { name: 'Research' } },
      { path: 'research', name: 'Research', component: () => import('../views/Research.vue'), meta: { title: '分析 · 选股' } },
      { path: 'lab', name: 'Lab', component: () => import('../views/Lab.vue'), meta: { title: '模型实验室' } },
      { path: 'auto-factor-lab', name: 'AutoFactorLab', component: () => import('../views/AutoFactorLab.vue'), meta: { title: '自动因子挖掘' } },

      // 旧路径兼容：重定向到合并后的页面并定位到对应 tab
      { path: 'analysis', redirect: to => ({ name: 'Research', query: { ...to.query, tab: 'analysis' } }) },
      { path: 'screener', redirect: to => ({ name: 'Research', query: { ...to.query, tab: 'screener' } }) },
      { path: 'backtest', redirect: to => ({ name: 'Lab', query: { ...to.query, tab: 'backtest' } }) },
      { path: 'model-lab', redirect: to => ({ name: 'Lab', query: { ...to.query, tab: 'train' } }) }
    ]
  },
  // 其余未知路径回落到首页
  { path: '/:pathMatch(.*)*', redirect: '/research' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 开源版：不拦截页面浏览，所有页面可看
// （演示站的 RD-Agent 只读限制由后端拦截 + 页面内提示，不做路由重定向）
export default router
