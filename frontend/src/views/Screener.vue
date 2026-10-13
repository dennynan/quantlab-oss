<template>
  <div class="screener-shell">
    <!-- ════════ 模式切换 ════════ -->
    <div class="mode-tabs">
      <button :class="{ active: mode === 'quick' }" @click="mode = 'quick'">快捷筛选</button>
      <button :class="{ active: mode === 'advanced' }" @click="mode = 'advanced'">高级筛选</button>
    </div>

    <!-- ════════ 快捷筛选 ════════ -->
    <section class="filter-bar" v-if="mode === 'quick'">
      <div class="filter-row">
        <div class="filter-group">
          <label>📈 5日动量</label>
          <div class="f-inputs">
            <span class="f-label">最低</span>
            <input v-model.number="filters.momentum_min" type="number" placeholder="5" class="f-input"
              @keyup.enter="doQuickScreen" />
            <span class="f-unit">%</span>
          </div>
          <div class="f-inputs">
            <span class="f-label">最高</span>
            <input v-model.number="filters.momentum_max" type="number" placeholder="30" class="f-input" />
            <span class="f-unit">%</span>
          </div>
        </div>
        <div class="filter-group">
          <label>📊 RSI(14)</label>
          <div class="f-inputs">
            <span class="f-label">最低</span>
            <input v-model.number="filters.rsi_min" type="number" placeholder="30" class="f-input" />
          </div>
          <div class="f-inputs">
            <span class="f-label">最高</span>
            <input v-model.number="filters.rsi_max" type="number" placeholder="70" class="f-input" />
          </div>
        </div>
        <div class="filter-group">
          <label>📐 MA20偏离</label>
          <div class="f-inputs">
            <span class="f-label">最低</span>
            <input v-model.number="filters.ma20_dev_min" type="number" placeholder="0" class="f-input" />
            <span class="f-unit">%</span>
          </div>
        </div>
        <div class="filter-group">
          <label>🌊 波动率</label>
          <div class="f-inputs">
            <span class="f-label">最高</span>
            <input v-model.number="filters.vol_max" type="number" placeholder="80" class="f-input" />
            <span class="f-unit">%</span>
          </div>
        </div>
        <div class="filter-group">
          <label>💰 成交额</label>
          <div class="f-inputs">
            <span class="f-label">最低</span>
            <input v-model.number="filters.amount_min" type="number" placeholder="5000" class="f-input" />
            <span class="f-unit">万</span>
          </div>
        </div>
        <div class="filter-actions">
          <button class="sr-btn primary" @click="doQuickScreen" :disabled="screening">
            <span v-if="screening" class="spinner-sm"></span>
            <span v-else>🔍 筛选</span>
          </button>
          <button class="sr-btn secondary" @click="resetFilters">↺ 重置</button>
        </div>
      </div>
    </section>

    <!-- ════════ 高级筛选 ════════ -->
    <section class="filter-bar" v-if="mode === 'advanced'">
      <div class="adv-tip">添加筛选条件，支持 gt(大于) / lt(小于) / gte(≥) / lte(≤) / between(区间)</div>
      <div class="adv-rows">
        <div v-for="(cond, i) in advConditions" :key="i" class="adv-row">
          <select v-model="cond.factor" class="adv-select">
            <option value="">-- 选因子 --</option>
            <option v-for="f in factorList" :key="f.key" :value="f.key">{{ f.label }} ({{ f.key }})</option>
          </select>
          <select v-model="cond.op" class="adv-op">
            <option value="gt">&gt; 大于</option>
            <option value="lt">&lt; 小于</option>
            <option value="gte">≥ 大于等于</option>
            <option value="lte">≤ 小于等于</option>
            <option value="between">↔ 区间</option>
          </select>
          <template v-if="cond.op === 'between'">
            <input v-model.number="cond.valueLow" type="number" class="adv-val" placeholder="下限" />
            <span class="adv-sep">~</span>
            <input v-model.number="cond.valueHigh" type="number" class="adv-val" placeholder="上限" />
          </template>
          <template v-else>
            <input v-model.number="cond.value" type="number" class="adv-val" placeholder="阈值" />
          </template>
          <button class="adv-del" @click="advConditions.splice(i, 1)" :disabled="advConditions.length <= 1">✕</button>
        </div>
      </div>
      <div class="adv-buttons">
        <button class="sr-btn secondary" @click="addAdvCondition">+ 添加条件</button>
        <button class="sr-btn primary" @click="doAdvScreen" :disabled="screening || !hasValidAdv">
          <span v-if="screening" class="spinner-sm"></span>
          <span v-else>🔍 高级筛选</span>
        </button>
      </div>
    </section>

    <!-- ════════ 预设 ════════ -->
    <section class="presets">
      <span class="presets-label">快捷方案:</span>
      <button v-for="p in presets" :key="p.name" class="preset-chip"
        @click="applyPreset(p)">
        {{ p.emoji }} {{ p.name }}
      </button>
    </section>

    <!-- ════════ 结果 ════════ -->
    <div v-if="screenResult" class="result-bar">
      <span class="result-count">共 <strong>{{ screenResult.total_matched }}</strong> 只匹配</span>
      <span class="result-date">数据日期: {{ screenResult.latest_date }}</span>
      <span v-if="screenResult.has_more" class="result-hint">（仅显示前 {{ screenResult.stocks.length }} 只）</span>
      <el-button size="small" type="warning" @click="sendToBacktest" style="margin-left:auto">
        📤 发送到回测
      </el-button>
    </div>

    <div v-if="screenResult && screenResult.stocks.length" class="result-table-wrap">
      <table class="result-table">
        <thead>
          <tr>
            <th class="th-code">代码</th>
            <th>名称</th>
            <th class="th-num">现价</th>
            <th class="th-num">5日动量</th>
            <th class="th-num">MA20偏离</th>
            <th class="th-num">RSI</th>
            <th class="th-num">20日动量</th>
            <th class="th-action">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in screenResult.stocks" :key="s.code"
            :class="{ 'row-selected': detailCode === s.code }"
            @click="selectStock(s.code)">
            <td class="td-code">{{ s.code }}</td>
            <td class="td-name">{{ s.name }}</td>
            <td class="td-price" :class="(s.momentum_5 ?? 0) >= 0 ? 'up' : 'down'">{{ s.close }}</td>
            <td class="td-momentum" :class="(s.momentum_5 ?? 0) >= 0 ? 'up' : 'down'">
              {{ s.momentum_5 != null ? (s.momentum_5 > 0 ? '+' : '') + s.momentum_5 + '%' : '—' }}
            </td>
            <td class="td-momentum" :class="(s.ma20_dev ?? 0) >= 0 ? 'up' : 'down'">
              {{ s.ma20_dev != null ? (s.ma20_dev > 0 ? '+' : '') + s.ma20_dev + '%' : '—' }}
            </td>
            <td class="td-rsi">
              <span class="rsi-badge" :class="rsiClass(s.rsi_14)">{{ s.rsi_14 ?? '—' }}</span>
            </td>
            <td class="td-momentum">
              {{ s.momentum_20 != null ? (s.momentum_20 > 0 ? '+' : '') + s.momentum_20 + '%' : '—' }}
            </td>
            <td class="td-action">
              <button class="action-link" @click.stop="showDetail(s.code)">📊</button>
              <button class="action-link" @click.stop="goAnalysis(s.code)">🧠</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="screenError" class="error-toast">{{ screenError }}</div>
    <div v-if="screenResult && !screenResult.stocks.length && !screenError" class="empty-state">
      📭 没有匹配的股票，试试放宽条件
    </div>

    <!-- ════════ 初始空状态 ════════ -->
    <div v-if="!screenResult && !screenError && !screening" class="welcome-state">
      <div class="wl-hero">🔬</div>
      <p class="wl-title">设置筛选条件，开始选股</p>
      <p class="wl-desc">基于 {{ poolSize || '本地' }} 只标的日线数据 + Qlib 因子计算引擎</p>
      <div class="wl-presets">
        <div v-for="p in presets" :key="p.name" class="wl-preset-card" @click="applyPreset(p)">
          <span class="wl-p-emoji">{{ p.emoji }}</span>
          <div>
            <strong>{{ p.name }}</strong>
            <p class="wl-p-desc">{{ p.desc }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- ════════ 详情弹窗 ════════ -->
    <el-dialog v-model="dialogVisible" :title="'📊 ' + detailCode + ' ' + (detailData?.name || '')" width="520px"
      :close-on-click-modal="true" destroy-on-close>
      <div v-if="detailLoading" class="detail-load">加载中…</div>
      <div v-else-if="detailData" class="detail-body">
        <div class="d-head">
          <span class="d-price">{{ detailData.latest_close }}</span>
          <span class="d-date">{{ detailData.latest_date }}</span>
        </div>
        <div class="divider"></div>
        <div class="d-grid">
          <div class="d-item" v-for="f in factorDisplay" :key="f.key">
            <span class="d-label">{{ f.label }}</span>
            <span class="d-value" :class="f.color?.(detailData[f.key])">{{ detailData[f.key] ?? '—' }}</span>
          </div>
        </div>
        <div v-if="detailData.ma_values" class="divider"></div>
        <div v-if="detailData.ma_values" class="d-ma">
          <span class="d-ma-label">均线</span>
          <span v-for="(v,k) in detailData.ma_values" :key="k" class="d-ma-v">
            {{ k }} <strong>{{ v }}</strong>
          </span>
        </div>
        <div v-if="detailData.ma_alignment" class="d-align"
          :class="detailData.ma_alignment === 'bullish' ? 'bull' : detailData.ma_alignment === 'bearish' ? 'bear' : ''">
          {{ detailData.ma_alignment === 'bullish' ? '🐂 多头排列' : detailData.ma_alignment === 'bearish' ? '🐻 空头排列' : '↔ 混合排列' }}
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, markRaw, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const mode = ref('quick')

// 因子列表（供高级筛选下拉使用）
const factorList = ref([])
// 当前行情库标的数（样例库与自建库不同，避免写死数字误导）
const poolSize = ref(0)

onMounted(async () => {
  // 预加载因子列表
  try {
    const res = await api.get('/qlib/factors')
    factorList.value = res.data.factors || []
  } catch {}
  // 预加载标的数
  try {
    const res = await api.get('/qlib/health')
    poolSize.value = res.data.total_stocks || 0
  } catch {}
})

// ── 快捷筛选 ──
const filters = reactive({
  momentum_min: null, momentum_max: null,
  rsi_min: null, rsi_max: null,
  ma20_dev_min: null,
  vol_max: null,
  amount_min: null,
})

const screening = ref(false)
const screenResult = ref(null)
const screenError = ref('')

// ── 高级筛选 ──
const advConditions = reactive([
  { factor: '', op: 'gt', value: null, valueLow: null, valueHigh: null }
])

function addAdvCondition() {
  advConditions.push({ factor: '', op: 'gt', value: null, valueLow: null, valueHigh: null })
}

const hasValidAdv = computed(() => {
  return advConditions.some(c => {
    if (!c.factor) return false
    if (c.op === 'between') return c.valueLow != null && c.valueHigh != null
    return c.value != null
  })
})

// ── 预设 ──
const presets = [
  { name: '强势突破', emoji: '🚀', desc: '5日动量>5%、MA20上方、RSI适中', filters: { momentum_min: 5, ma20_dev_min: 0, rsi_max: 70 } },
  { name: '超跌反弹', emoji: '🪝', desc: '5日跌超8%、RSI<30、成交活跃', filters: { momentum_max: -8, rsi_min: 0, rsi_max: 30, amount_min: 3000 } },
  { name: '温和慢牛', emoji: '🐂', desc: 'MA20上方、低波动、成交稳定', filters: { ma20_dev_min: 0, vol_max: 50, amount_min: 5000, rsi_min: 40, rsi_max: 60 } },
  { name: '放量启动', emoji: '📢', desc: '动量>3%、成交额>1亿、MA20上方', filters: { momentum_min: 3, ma20_dev_min: 0, amount_min: 10000 } },
]

function applyPreset(p) {
  mode.value = 'quick'
  Object.keys(filters).forEach(k => filters[k] = null)
  Object.assign(filters, p.filters)
  doQuickScreen()
}

function resetFilters() {
  Object.keys(filters).forEach(k => filters[k] = null)
  advConditions.splice(0, advConditions.length, { factor: '', op: 'gt', value: null, valueLow: null, valueHigh: null })
  screenResult.value = null
  screenError.value = ''
}

// ── 快捷筛选 API ──
function buildQueryParams() {
  const p = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => {
    if (v != null && v !== '') p.set(k, v)
  })
  p.set('limit', 30)
  return p.toString()
}

async function doQuickScreen() {
  const qs = buildQueryParams()
  if (!qs.includes('=')) { screenError.value = '请至少设置一个筛选条件'; return }
  screening.value = true; screenError.value = ''; screenResult.value = null
  try {
    const res = await api.get(`/qlib/screen/quick?${qs}`)
    screenResult.value = res.data
  } catch (e) {
    screenError.value = e.response?.data?.detail || e.message || '筛选失败'
  } finally { screening.value = false }
}

// ── 高级筛选 API ──
async function doAdvScreen() {
  const conditions = advConditions
    .filter(c => c.factor)
    .map(c => {
      const v = c.op === 'between' ? [c.valueLow || 0, c.valueHigh || 0] : (c.value || 0)
      return { factor: c.factor, op: c.op, value: v }
    })
  if (!conditions.length) { screenError.value = '请添加至少一个有效条件'; return }

  screening.value = true; screenError.value = ''; screenResult.value = null
  try {
    const res = await api.post('/qlib/screen', { conditions, limit: 30 })
    screenResult.value = res.data
  } catch (e) {
    screenError.value = e.response?.data?.detail || e.message || '筛选失败'
  } finally { screening.value = false }
}

// ── 工具 ──
function rsiClass(v) {
  if (v == null) return ''
  if (v >= 70) return 'overbought'
  if (v <= 30) return 'oversold'
  return ''
}

// ── 详情弹窗 ──
const dialogVisible = ref(false)
const detailCode = ref('')
const detailLoading = ref(false)
const detailData = ref(null)

const factorDisplay = markRaw([
  { key: 'momentum_5', label: '5日动量', color: v => parseFloat(v) >= 0 ? 'up' : 'down' },
  { key: 'momentum_20', label: '20日动量', color: v => parseFloat(v) >= 0 ? 'up' : 'down' },
  { key: 'ma20_dev', label: 'MA20偏离', color: v => parseFloat(v) >= 0 ? 'up' : 'down' },
  { key: 'ma60_dev', label: 'MA60偏离', color: v => parseFloat(v) >= 0 ? 'up' : 'down' },
  { key: 'rsi_14', label: 'RSI(14)', color: v => { const n = parseFloat(v); return n >= 70 ? 'overbought' : n <= 30 ? 'oversold' : '' } },
  { key: 'volatility_20', label: '20日波动率', color: () => '' },
  { key: 'avg_amount_20', label: '日均成交额(万)', color: () => '' },
  { key: 'turnover_20', label: '日均换手率(%)', color: () => '' },
])

function selectStock(code) { detailCode.value = code }
async function showDetail(code) {
  detailCode.value = code; dialogVisible.value = true
  detailLoading.value = true; detailData.value = null
  try {
    const res = await api.get(`/qlib/factors/${code}`)
    detailData.value = res.data
  } catch { detailData.value = { error: '加载失败' } }
  finally { detailLoading.value = false }
}
function goAnalysis(code) {
  router.push({ path: '/analysis', query: { code } })
}
function sendToBacktest() {
  if (!screenResult.value?.stocks?.length) return
  const codes = screenResult.value.stocks.map(s => s.code)
  localStorage.setItem('backtest_candidate_pool', JSON.stringify({
    codes,
    source: 'screener',
    timestamp: Date.now(),
  }))
  router.push('/backtest?from=screener')
}
</script>

<style scoped>
.screener-shell {
  max-width: 1000px; margin: 0 auto; padding: 4px;
  color: #E6E9EE;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
.sr-header { margin-bottom: 20px; }
.sr-title { font-size: 24px; font-weight: 800; margin: 0 0 4px; letter-spacing: -.5px; }
.sr-desc { font-size: 13px; color: #7A8494; margin: 0; }

/* Mode tabs */
.mode-tabs { display: flex; gap: 6px; margin-bottom: 16px; }
.mode-tabs button {
  padding: 7px 18px; border-radius: 8px; border: 1.5px solid #262D38;
  background: var(--card-bg); font-size: 13px; font-weight: 600; color: #98A2B3;
  cursor: pointer; transition: all .15s;
}
.mode-tabs button:hover { background: #12161D; }
.mode-tabs button.active {
  background: var(--primary); color: #fff; border-color: #E6E9EE;
}

/* Filter Bar */
.filter-bar {
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 18px 20px; margin-bottom: 12px;
}
.filter-row { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end; }
.filter-group { display: flex; flex-direction: column; gap: 6px; }
.filter-group label { font-size: 11px; font-weight: 700; color: #98A2B3; text-transform: uppercase; letter-spacing: .5px; }
.f-inputs { display: flex; align-items: center; gap: 6px; }
.f-label { font-size: 10px; color: #7A8494; min-width: 24px; text-align: right; }
.f-input { width: 72px; padding: 6px 8px; border: 1.5px solid #262D38; border-radius: 6px; font-size: 13px; font-family: 'SF Mono',monospace; text-align: right; outline: none; transition: border-color .15s; background: transparent; color: #E6E9EE; }
.f-input:focus { border-color: #60A5FA; }
.f-unit { font-size: 11px; color: #7A8494; }
.filter-actions { display: flex; gap: 8px; align-items: flex-end; padding-bottom: 2px; }
.sr-btn { padding: 8px 18px; border-radius: 8px; border: none; font-size: 13px; font-weight: 700; cursor: pointer; transition: all .15s; white-space: nowrap; }
.sr-btn.primary { background: var(--primary); color: #fff; }
.sr-btn.primary:hover:not(:disabled) { background: var(--primary-hover); }
.sr-btn.primary:disabled { opacity: .4; }
.sr-btn.secondary { background: transparent; color: #98A2B3; border: 1.5px solid #262D38; }
.sr-btn.secondary:hover { background: #12161D; }
.spinner-sm { display: inline-block; width: 14px; height: 14px; border: 2px solid #fff; border-top-color: transparent; border-radius: 50%; animation: spin-sm .6s linear infinite; vertical-align: middle; }
@keyframes spin-sm { to { transform: rotate(360deg) } }

/* Advanced */
.adv-tip { font-size: 11px; color: #7A8494; margin-bottom: 10px; }
.adv-rows { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.adv-row { display: flex; align-items: center; gap: 8px; }
.adv-select { padding: 6px 8px; border: 1.5px solid #262D38; border-radius: 6px; font-size: 12px; background: var(--card-bg); color: #E6E9EE; min-width: 160px; }
.adv-op { padding: 6px 8px; border: 1.5px solid #262D38; border-radius: 6px; font-size: 12px; background: var(--card-bg); color: #E6E9EE; min-width: 110px; }
.adv-val { width: 80px; padding: 6px 8px; border: 1.5px solid #262D38; border-radius: 6px; font-size: 13px; font-family: 'SF Mono',monospace; text-align: right; background: transparent; }
.adv-sep { color: #7A8494; font-size: 12px; }
.adv-del { background: none; border: none; color: #F87171; cursor: pointer; font-size: 16px; padding: 4px 6px; }
.adv-buttons { display: flex; gap: 10px; }

/* Presets */
.presets { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.presets-label { font-size: 12px; color: #7A8494; font-weight: 600; }
.preset-chip { font-size: 12px; padding: 5px 14px; border-radius: 20px; border: 1.5px solid #262D38; background: var(--card-bg); color: #A4AEBB; cursor: pointer; transition: all .15s; font-weight: 500; }
.preset-chip:hover { background: var(--primary); color: #fff; border-color: #E6E9EE; }

/* Result */
.result-bar { display: flex; align-items: center; gap: 16px; padding: 10px 16px; margin-bottom: 10px; background: #12161D; border-radius: 8px; font-size: 13px; }
.result-count strong { color: #60A5FA; font-size: 16px; }
.result-date { color: #7A8494; font-size: 12px; }
.result-hint { color: #333B47; font-size: 11px; margin-left: auto; }

.result-table-wrap { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.result-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.result-table th { background: #12161D; padding: 10px 12px; text-align: left; font-size: 10px; font-weight: 700; text-transform: uppercase; color: #7A8494; letter-spacing: .5px; border-bottom: 1px solid #161C24; }
.th-num, .th-action { text-align: right; }
.result-table td { padding: 10px 12px; border-bottom: 1px solid #12161D; cursor: pointer; transition: background .1s; }
.result-table tr:hover td { background: #12161D; }
.result-table tr.row-selected td { background: rgba(59,130,246,0.12); }
.td-code { font-family: 'SF Mono',monospace; font-size: 12px; color: #98A2B3; font-weight: 600; }
.td-name { font-weight: 600; color: #E6E9EE; }
.td-price { font-family: 'SF Mono',monospace; font-weight: 700; text-align: right; }
.td-momentum { text-align: right; font-weight: 600; font-family: 'SF Mono',monospace; }
.td-rsi { text-align: right; }
.td-action { text-align: right; }
.up { color: #F87171; }
.down { color: #4ADE80; }
.rsi-badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; font-family: 'SF Mono',monospace; }
.rsi-badge.overbought { background: rgba(239,68,68,0.12); color: #F87171; }
.rsi-badge.oversold { background: rgba(34,197,94,0.12); color: #4ADE80; }
.action-link { background: none; border: none; font-size: 16px; cursor: pointer; padding: 2px 6px; border-radius: 4px; }
.action-link:hover { background: #161C24; }

.error-toast { padding: 14px 20px; border-radius: 8px; background: rgba(239,68,68,0.12); color: #F87171; font-size: 14px; margin: 16px 0; border: 1px solid rgba(239,68,68,0.35); }
.empty-state { text-align: center; padding: 60px 20px; font-size: 15px; color: #7A8494; }

.welcome-state { text-align: center; padding: 60px 20px 40px; }
.wl-hero { font-size: 56px; margin-bottom: 12px; opacity: .6; }
.wl-title { font-size: 16px; font-weight: 700; color: #A4AEBB; margin: 0 0 6px; }
.wl-desc { font-size: 13px; color: #7A8494; margin: 0 0 32px; }
.wl-presets { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; max-width: 500px; margin: 0 auto; }
.wl-preset-card { display: flex; align-items: flex-start; gap: 12px; background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 16px; cursor: pointer; transition: all .15s; text-align: left; }
.wl-preset-card:hover { border-color: #60A5FA; }
.wl-p-emoji { font-size: 28px; flex-shrink: 0; }
.wl-preset-card strong { display: block; font-size: 14px; color: #E6E9EE; margin-bottom: 4px; }
.wl-p-desc { font-size: 11px; color: #7A8494; margin: 0; }

/* Detail Dialog */
.detail-load { text-align: center; padding: 40px 0; color: #7A8494; }
.detail-body { padding: 4px 0; }
.d-head { display: flex; justify-content: space-between; align-items: baseline; }
.d-price { font-size: 32px; font-weight: 900; letter-spacing: -1px; }
.d-date { font-size: 12px; color: #7A8494; }
.divider { height: 1px; background: #161C24; margin: 14px 0; }
.d-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.d-item { display: flex; flex-direction: column; gap: 2px; }
.d-label { font-size: 10px; color: #7A8494; text-transform: uppercase; font-weight: 600; letter-spacing: .3px; }
.d-value { font-size: 15px; font-weight: 700; font-family: 'SF Mono',monospace; }
.d-value.up { color: #F87171; } .d-value.down { color: #4ADE80; }
.d-value.overbought { color: #F87171; } .d-value.oversold { color: #4ADE80; }
.d-ma { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; font-size: 12px; }
.d-ma-label { color: #7A8494; font-weight: 600; font-size: 10px; text-transform: uppercase; margin-right: 4px; }
.d-ma-v { font-family: 'SF Mono',monospace; color: #98A2B3; }
.d-ma-v strong { color: #E6E9EE; }
.d-align { margin-top: 12px; padding: 8px 14px; border-radius: 8px; font-size: 14px; font-weight: 700; text-align: center; }
.d-align.bull { background: rgba(239,68,68,0.12); color: #F87171; }
.d-align.bear { background: rgba(34,197,94,0.12); color: #4ADE80; }
.d-align:not(.bull):not(.bear) { background: #12161D; color: #98A2B3; }
</style>
