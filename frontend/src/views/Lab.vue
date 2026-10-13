<template>
  <div class="merged-page">
    <div class="seg-tabs">
      <button :class="{ active: tab === 'backtest' }" @click="setTab('backtest')">策略回测</button>
      <button :class="{ active: tab === 'train' }" @click="setTab('train')">模型训练</button>
    </div>
    <component :is="comps[tab]" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Backtest from './Backtest.vue'
import ModelLab from './ModelLab.vue'

const TABS = ['backtest', 'train']
const comps = { backtest: Backtest, train: ModelLab }

const route = useRoute()
const router = useRouter()

const tab = computed(() => (TABS.includes(route.query.tab) ? route.query.tab : 'backtest'))

function setTab(t) {
  if (t === tab.value) return
  router.replace({ query: { ...route.query, tab: t } })
}
</script>

<style scoped>
.merged-page { max-width: 1280px; }
</style>
