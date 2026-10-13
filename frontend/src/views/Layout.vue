<template>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="sidebar-brand" @click="$router.push('/research')">
        <span class="brand-text">策略实验室</span>
        <span class="brand-tag">OSS</span>
      </div>

      <nav class="sidebar-nav">
        <router-link to="/research" class="nav-item" active-class="active">
          <span>分析 · 选股</span>
        </router-link>
        <router-link to="/lab" class="nav-item" active-class="active">
          <span>模型实验室</span>
        </router-link>
        <router-link to="/auto-factor-lab" class="nav-item" active-class="active">
          <span>自动因子挖掘</span>
        </router-link>
      </nav>

      <div class="sidebar-foot">
        <span>{{ isDemo ? '在线演示 · 免登录' : '开源版 · 免登录' }}</span>
      </div>
    </aside>

    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
// 开源版：无用户认证，侧边栏不含用户/配额信息
// 演示站（isDemo）：仅用于底部标识；RD-Agent 入口保留，进去后由页面禁写
import { isDemo } from '../api/demo'
</script>

<style scoped>
.app-layout { display: flex; min-height: 100vh; }
.sidebar {
  width: 200px; min-width: 200px;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  position: fixed; top: 0; left: 0; bottom: 0;
  z-index: 100;
}
.sidebar-brand {
  display: flex; align-items: baseline; gap: 6px;
  padding: 20px 20px 16px; cursor: pointer;
  user-select: none;
}
.brand-text { font-size: 15px; font-weight: 600; color: var(--text-primary); letter-spacing: -0.2px; }
.brand-tag {
  font-size: 10px; line-height: 14px; color: var(--text-muted);
  border: 1px solid var(--border); border-radius: 4px; padding: 0 4px;
}

.sidebar-nav {
  flex: 1; padding: 4px 10px;
  display: flex; flex-direction: column; gap: 1px;
}
.nav-item {
  display: flex; align-items: center;
  padding: 8px 12px; border-radius: var(--radius-sm);
  color: var(--text-secondary); font-size: 13px;
  transition: background 0.12s, color 0.12s;
  text-decoration: none;
}
.nav-item:hover { background: var(--sidebar-hover); color: var(--text-primary); text-decoration: none; }
.nav-item.active { background: var(--sidebar-active); color: var(--text-primary); font-weight: 500; }

.sidebar-foot {
  padding: 14px 20px; border-top: 1px solid var(--border);
  font-size: 11px; color: var(--text-muted);
}

.main-content {
  flex: 1; margin-left: 200px;
  padding: 28px 32px; min-height: 100vh;
  background: var(--content-bg);
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
