<template>
  <div class="analysis-shell">
    <!-- ============ 搜索栏 ============ -->
    <div class="search-bar">
      <div class="search-box">
        <svg class="search-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <input v-model="stockCode" placeholder="输入股票代码" class="search-input"
          @keyup.enter="startAnalysis" @focus="searchFocused=true" @blur="searchFocused=false" />
        <button class="go-btn" :disabled="!stockCode.trim() || analyzing" @click="startAnalysis">
          <span v-if="analyzing" class="spinner" />
          <span v-else>分析</span>
        </button>
      </div>
      <div class="quick-bar">
        <span v-for="c in quickCodes" :key="c" class="quick-chip" @click="stockCode=c;startAnalysis()">
          {{ c.startsWith('6')?'SH':'SZ' }}{{ c }}
        </span>
      </div>
    </div>

    <!-- ============ 加载 ============ -->
    <div v-if="analyzing" class="loading-view">
      <div class="loader-dot"></div>
      <p>正在分析 <strong>{{ stockCode }}</strong> …</p>
    </div>

    <!-- ============ 错误 ============ -->
    <div v-if="error" class="error-toast">{{ error }}</div>

    <!-- ============ 分析报告 ============ -->
    <div v-if="result && !analyzing" class="report">

      <!-- ★ 概览仪表盘 ★ -->
      <section class="dashboard">
        <div class="dash-left">
          <div class="stock-identity">
            <div class="stock-name-row">
              <h1 class="stock-name">{{ result.name }}</h1>
              <span class="stock-code-badge">{{ result.code }}</span>
            </div>
            <div class="price-row">
              <span class="price-big" :class="trendClass">{{ result.price?.toFixed(2) }}</span>
              <span class="change-badge" :class="trendClass">
                {{ (result.change_pct||0)>=0?'+':'' }}{{ result.change_pct?.toFixed(2) }}%
              </span>
            </div>
            <div class="meta-row">
              <span v-if="result.factors?.ma5">MA5 {{ result.factors.ma5 }} / MA10 {{ result.factors.ma10 }} / MA20 {{ result.factors.ma20 }}</span>
              <span>{{ result.factors?.ma_alignment }}</span>
            </div>
          </div>

          <div class="total-ring-wrap">
            <svg class="total-ring" viewBox="0 0 140 140">
              <circle cx="70" cy="70" r="60" fill="none" stroke="#161C24" stroke-width="10"/>
              <circle cx="70" cy="70" r="60" fill="none" :stroke="result.total.color" stroke-width="10"
                stroke-linecap="round" :stroke-dasharray="2*Math.PI*60"
                :stroke-dashoffset="2*Math.PI*60*(1-result.total.total/100)"
                transform="rotate(-90 70 70)" class="ring-anim" />
            </svg>
            <div class="ring-center">
              <span class="ring-val" :style="{color:result.total.color}">{{ result.total.total }}</span>
              <span class="ring-unit">/100</span>
            </div>
          </div>
          <div class="total-verdict" :style="{color:result.total.color}">{{ result.total.grade }}</div>
        </div>

        <div class="dash-right">
          <div class="dimension-strip" v-for="(s,key) in result.scores" :key="key">
            <div class="dim-head">
              <span class="dim-icon">{{ scoreIcons[key] }}</span>
              <span class="dim-name">{{ scoreNames[key] }}</span>
            </div>
            <div class="dim-track">
              <div class="dim-fill" :style="{width:s.score+'%',background:s.color}"></div>
            </div>
            <div class="dim-tail">
              <span class="dim-score" :style="{color:s.color}">{{ s.score }}</span>
              <span class="dim-label" :style="{color:s.color}">{{ s.label }}</span>
            </div>
            <div class="dim-detail">{{ s.detail }}</div>
          </div>
        </div>
      </section>

      <!-- ★ 信号面板 ★ -->
      <section class="signal-panel">
        <div class="signal-card">
          <div class="sig-title">📐 多周期形态</div>
          <div class="sig-body">
            <div class="period-col" v-for="(pname, period) in periodNames" :key="period">
              <div class="period-tag">{{ pname }}</div>
              <template v-if="result.patterns[period]?.length">
                <div class="pattern-line" v-for="(p,i) in result.patterns[period]" :key="i"
                  :class="p.includes('⚠️')||p.includes('↓↓')||p.includes('死叉')||p.includes('空头')?'bearish':
                          p.includes('💡')||p.includes('↑↑')||p.includes('金叉')||p.includes('多头')?'bullish':''">
                  {{ p }}
                </div>
              </template>
              <div v-else class="pattern-line muted">无明显信号</div>
            </div>
          </div>
        </div>

        <div class="signal-card">
          <div class="sig-title">📊 关键数据</div>
          <div class="sig-body kv-list">
            <div class="kv"><span class="kv-k">日期</span><span class="kv-v">{{ result.date }}</span></div>
            <div class="kv"><span class="kv-k">今开</span><span class="kv-v">{{ result.open?.toFixed(2) }}</span></div>
            <div class="kv"><span class="kv-k">最高</span><span class="kv-v up">{{ result.high?.toFixed(2) }}</span></div>
            <div class="kv"><span class="kv-k">最低</span><span class="kv-v down">{{ result.low?.toFixed(2) }}</span></div>
            <div class="kv"><span class="kv-k">昨收</span><span class="kv-v">{{ ((result.price||0)-(result.change_pct||0)/100*(result.price||0)).toFixed(2) }}</span></div>
            <div class="kv"><span class="kv-k">MA5</span><span class="kv-v">{{ result.factors?.ma5 }}</span></div>
            <div class="kv"><span class="kv-k">MA20</span><span class="kv-v">{{ result.factors?.ma20 }}</span></div>
            <div class="kv"><span class="kv-k">MA60</span><span class="kv-v">{{ result.factors?.ma60 }}</span></div>
            <div class="kv"><span class="kv-k">RSI(14)</span><span class="kv-v">{{ result.factors?.rsi14 }}</span></div>
            <div class="kv"><span class="kv-k">波动率</span><span class="kv-v">{{ result.factors?.volatility_20 }}%</span></div>
          </div>
        </div>

        <div class="signal-card">
          <div class="sig-title">📈 因子指标</div>
          <div class="sig-body kv-list">
            <div class="kv"><span class="kv-k">5日动量</span><span class="kv-v" :class="(result.factors?.momentum_5||0)>=0?'up':'down'">{{ result.factors?.momentum_5 }}%</span></div>
            <div class="kv"><span class="kv-k">20日动量</span><span class="kv-v" :class="(result.factors?.momentum_20||0)>=0?'up':'down'">{{ result.factors?.momentum_20 }}%</span></div>
            <div class="kv"><span class="kv-k">MA20偏离</span><span class="kv-v">{{ result.factors?.ma20_dev || '—' }}</span></div>
            <div class="kv"><span class="kv-k">MA60偏离</span><span class="kv-v">{{ result.factors?.ma60_dev || '—' }}</span></div>
            <div class="kv"><span class="kv-k">均线排列</span><span class="kv-v">{{ result.factors?.ma_alignment }}</span></div>
            <div class="kv"><span class="kv-k">成交量</span><span class="kv-v">{{ fmtVol(result.volume) }}</span></div>
            <div class="kv"><span class="kv-k">成交额</span><span class="kv-v">{{ fmtAmt(result.amount) }}</span></div>
          </div>
        </div>
      </section>

      <!-- ★ 研判报告（本地规则生成，非 LLM） ★ -->
      <section class="ai-section">
        <div class="ai-header">
          <span class="ai-badge">量化研判</span>
          <span class="ai-model">Qlib 量化引擎 · 本地规则生成</span>
        </div>
        <div class="ai-body" v-html="renderedReport"></div>
      </section>
    </div>

    <!-- ============ 空状态 ============ -->
    <div v-if="!result && !analyzing && !error" class="empty-view">
      <div class="empty-hero">📊</div>
      <p class="empty-title">输入股票代码，即刻分析</p>
      <p class="empty-desc">Qlib 量化引擎 · 多周期形态 · 五维评分 · 本地规则研判</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { marked } from 'marked'
import api from '../api'

const props = defineProps({ initialCode: { type: String, default: '' } })

const stockCode = ref('')
const analyzing = ref(false)
const result = ref(null)
const error = ref('')
const searchFocused = ref(false)

const quickCodes = ['600519', '000001', '300750']
const scoreIcons = { technical: '📈', value: '💰', money_flow: '💵', heat: '🔥', trend: '🧭' }
const scoreNames = { technical: '技术面', value: '价值面', money_flow: '资金面', heat: '热度', trend: '趋势' }
const periodNames = { day: '日线', week: '周线', month: '月线' }

const trendClass = computed(() => result.value && (result.value.change_pct||0) >= 0 ? 'up' : 'down')

const renderedReport = computed(() => {
  if (!result.value?.report) return ''
  let html = marked(result.value.report, { breaks: true })
  html = html.replace(/<p>【(.+?)】/g, '<h4 class="r-section"><span class="r-sect-dot"></span>$1</h4>')
  html = html.replace(/<strong>(仅供参考.*?)<\/strong>/g, '<em class="r-disclaimer">$1</em>')
  return html
})

function fmtVol(v) {
  if (!v) return '—'
  if (v >= 1e8) return (v/1e8).toFixed(1)+'亿手'
  if (v >= 1e4) return (v/1e4).toFixed(1)+'万手'
  return v+'手'
}
function fmtAmt(v) {
  if (!v) return '—'
  if (v >= 1e8) return (v/1e8).toFixed(1)+'亿'
  if (v >= 1e4) return (v/1e4).toFixed(0)+'万'
  return v
}

async function startAnalysis() {
  const code = stockCode.value.trim()
  if (!code) return
  analyzing.value = true; error.value = ''; result.value = null
  try {
    const res = await api.get(`/qlib/factors/${code}/full`)
    if (res.data.error) throw new Error(res.data.error)
    result.value = res.data
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '分析失败'
  } finally { analyzing.value = false }
}

// 从「AI选股」点击跳转过来时，自动带上股票代码并分析
watch(() => props.initialCode, (code) => {
  if (!code) return
  stockCode.value = code
  startAnalysis()
}, { immediate: true })
</script>

<style scoped>
.analysis-shell {
  max-width: 880px;
  margin: 0 auto;
  padding: 8px 4px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
.search-bar { margin-bottom: 24px; }
.search-box {
  display: flex; align-items: center; gap: 12px;
  background: var(--card-bg);
  border: 1.5px solid var(--border);
  border-radius: 8px; padding: 4px 4px 4px 20px;
  transition: all .2s;
}
.search-box:focus-within {
  border-color: #60A5FA;
}
.search-svg { width: 20px; height: 20px; color: #7A8494; flex-shrink: 0; }
.search-input {
  flex: 1; border: none; outline: none; background: transparent;
  font-size: 17px; padding: 14px 0; color: #E6E9EE;
  font-family: 'SF Mono','JetBrains Mono','Menlo',monospace; letter-spacing: 1px;
}
.search-input::placeholder { color: #333B47; letter-spacing: 0; font-family: inherit; }
.go-btn {
  padding: 12px 28px; border: none; border-radius: 8px;
  background: var(--primary); color: #fff; font-size: 14px; font-weight: 700;
  cursor: pointer; transition: all .2s; letter-spacing: .5px;
}
.go-btn:hover:not(:disabled) { background: var(--primary-hover); }
.go-btn:disabled { opacity: .35; cursor: not-allowed; }
.spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #fff; border-top-color: transparent; border-radius: 50%; animation: s .6s linear infinite; }
@keyframes s { to{transform:rotate(360deg)} }
.quick-bar { display: flex; gap: 8px; margin-top: 10px; }
.quick-chip {
  font-size: 12px; color: #98A2B3; cursor: pointer;
  padding: 5px 14px; border-radius: 20px; background: #12161D;
  border: 1px solid #262D38; transition: all .15s; font-weight: 500;
}
.quick-chip:hover { background: var(--primary); color: #fff; border-color: #E6E9EE; }
.loading-view {
  display: flex; flex-direction: column; align-items: center;
  padding: 100px 20px; gap: 16px; color: #7A8494;
}
.loader-dot {
  width: 10px; height: 10px; border-radius: 50%; background: #60A5FA;
  animation: ld 1.2s infinite;
}
@keyframes ld { 0%,100%{transform:scale(1);opacity:.3} 50%{transform:scale(2.5);opacity:.8} }
.error-toast {
  padding: 14px 20px; border-radius: 8px; background: rgba(239,68,68,0.12);
  color: #F87171; font-size: 14px; margin-bottom: 16px; border: 1px solid rgba(239,68,68,0.35);
}

/* 仪表盘 */
.dashboard {
  display: grid; grid-template-columns: 260px 1fr;
  gap: 0; background: var(--card-bg);
  border-radius: 20px; border: 1px solid var(--border);
  overflow: hidden; margin-bottom: 14px;
}
.dash-left {
  padding: 28px 24px 24px;
  background: #12161D;
  display: flex; flex-direction: column; align-items: center;
  text-align: center; gap: 16px;
  border-right: 1px solid var(--border);
}
.stock-name-row { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.stock-name { font-size: 20px; font-weight: 800; color: #E6E9EE; margin: 0; letter-spacing: -.2px; }
.stock-code-badge {
  font-size: 12px; color: #7A8494; font-family: 'SF Mono',monospace;
  background: #161C24; padding: 2px 10px; border-radius: 4px;
}
.price-row { display: flex; align-items: baseline; gap: 8px; }
.price-big { font-size: 34px; font-weight: 900; letter-spacing: -1.5px; }
.price-big.up { color: #F87171; } .price-big.down { color: #4ADE80; }
.change-badge {
  font-size: 14px; font-weight: 700; padding: 2px 10px; border-radius: 6px;
}
.change-badge.up { background: rgba(239,68,68,0.12); color: #F87171; }
.change-badge.down { background: rgba(34,197,94,0.12); color: #4ADE80; }
.meta-row {
  font-size: 11px; color: #7A8494; display: flex; flex-direction: column; gap: 2px;
  font-family: 'SF Mono',monospace;
}
.total-ring-wrap { position: relative; width: 130px; height: 130px; }
.total-ring { width: 130px; height: 130px; }
.ring-anim { transition: stroke-dashoffset 1.2s cubic-bezier(.4,0,.2,1); }
.ring-center {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  flex-direction: column;
}
.ring-val { font-size: 36px; font-weight: 900; line-height: 1; }
.ring-unit { font-size: 12px; color: #7A8494; }
.total-verdict { font-size: 15px; font-weight: 700; }
.dash-right {
  padding: 20px 24px 16px;
  display: flex; flex-direction: column; gap: 10px; justify-content: center;
}
.dimension-strip { }
.dim-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.dim-icon { font-size: 15px; }
.dim-name { font-size: 13px; font-weight: 700; color: #C9D1DB; flex: 1; }
.dim-weight { font-size: 10px; color: #7A8494; background: #12161D; padding: 1px 7px; border-radius: 4px; }
.dim-track { height: 6px; background: #161C24; border-radius: 3px; overflow: hidden; margin-bottom: 2px; }
.dim-fill { height: 100%; border-radius: 3px; transition: width 1s cubic-bezier(.4,0,.2,1); }
.dim-tail { display: flex; align-items: baseline; gap: 8px; }
.dim-score { font-size: 18px; font-weight: 800; }
.dim-label { font-size: 12px; font-weight: 600; }
.dim-detail { font-size: 10px; color: #7A8494; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
@media (max-width: 680px) {
  .dashboard { grid-template-columns: 1fr; }
  .dash-left { border-right: none; border-bottom: 1px solid var(--border); }
}

/* 信号面板 */
.signal-panel {
  display: grid; grid-template-columns: 1fr 1fr 1fr;
  gap: 12px; margin-bottom: 14px;
}
@media (max-width: 780px) { .signal-panel { grid-template-columns: 1fr 1fr; } }
@media (max-width: 520px) { .signal-panel { grid-template-columns: 1fr; } }
.signal-card {
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden;
}
.sig-title {
  font-size: 12px; font-weight: 700; color: #98A2B3;
  padding: 12px 16px; border-bottom: 1px solid #161C24;
  text-transform: uppercase; letter-spacing: .5px;
}
.sig-body { padding: 12px 16px; }
.period-col { margin-bottom: 10px; }
.period-col:last-child { margin-bottom: 0; }
.period-tag {
  font-size: 10px; font-weight: 700; color: #7A8494;
  margin-bottom: 4px; letter-spacing: .5px;
}
.pattern-line {
  font-size: 12px; color: #A4AEBB; padding: 2px 0; line-height: 1.5;
  font-family: 'SF Mono','JetBrains Mono',monospace; font-size: 11px;
}
.pattern-line.bullish { color: #F87171; }
.pattern-line.bearish { color: #4ADE80; }
.pattern-line.muted { color: #333B47; font-family: inherit; }
.kv-list { display: flex; flex-direction: column; gap: 6px; }
.kv { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
.kv-k { color: #7A8494; }
.kv-v { font-weight: 600; color: #E6E9EE; font-family: 'SF Mono',monospace; font-size: 12px; }
.kv-v.up { color: #F87171; }
.kv-v.down { color: #4ADE80; }

/* AI 报告 */
.ai-section {
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden;
}
.ai-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 24px; border-bottom: 1px solid #161C24;
}
.ai-badge {
  font-size: 14px; font-weight: 800; color: #E6E9EE;
  display: flex; align-items: center; gap: 6px;
}
.ai-badge::before { content: '🧠'; }
.ai-model { font-size: 11px; color: #7A8494; font-family: 'SF Mono',monospace; }
.ai-body {
  padding: 28px 32px; font-size: 14.5px; line-height: 2;
  color: #C9D1DB;
}
.ai-body :deep(h4.r-section) {
  font-size: 16px; font-weight: 800; color: #E6E9EE;
  margin: 28px 0 10px; padding-top: 24px;
  border-top: 1px solid #161C24;
  display: flex; align-items: center; gap: 8px;
}
.ai-body :deep(.r-sect-dot) {
  width: 6px; height: 6px; border-radius: 50%; background: #60A5FA;
  flex-shrink: 0;
}
.ai-body :deep(p) { margin: 8px 0; }
.ai-body :deep(strong) { font-weight: 700; color: #E6E9EE; }
.ai-body :deep(em.r-disclaimer) {
  display: block; font-style: normal; color: #7A8494;
  font-size: 12px; margin-top: 16px; padding-top: 12px;
  border-top: 1px dashed #262D38;
}
.empty-view { text-align: center; padding: 100px 20px; }
.empty-hero { font-size: 64px; margin-bottom: 16px; opacity: .6; }
.empty-title { font-size: 16px; font-weight: 700; color: #A4AEBB; margin: 0 0 6px; }
.empty-desc { font-size: 13px; color: #7A8494; margin: 0; }
</style>
