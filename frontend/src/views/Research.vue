<template>
  <div class="merged-page">
    <div class="seg-tabs">
      <button :class="{ active: tab === 'analysis' }" @click="setTab('analysis')">AI 个股分析</button>
      <button :class="{ active: tab === 'screener' }" @click="setTab('screener')">AI 选股</button>
    </div>
    <component :is="comps[tab]" v-bind="tab === 'analysis' ? { initialCode: route.query.code || '' } : {}" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Analysis from './Analysis.vue'
import Screener from './Screener.vue'

const TABS = ['analysis', 'screener']
const comps = { analysis: Analysis, screener: Screener }

const route = useRoute()
const router = useRouter()

const tab = computed(() => (TABS.includes(route.query.tab) ? route.query.tab : 'analysis'))

function setTab(t) {
  if (t === tab.value) return
  const q = { ...route.query, tab: t }
  if (t === 'analysis' && !q.code) delete q.code
  router.replace({ query: q })
}
</script>

<style scoped>
.merged-page { max-width: 1280px; }
</style>
