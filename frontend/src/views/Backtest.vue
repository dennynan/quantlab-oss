<template>
  <div class="bt-page">
    <!-- ═══ TopK 多因子轮动 ═══ -->
      <!-- 推荐策略预设卡片 -->
      <div class="card">
        <div class="card-title">📋 推荐策略配置</div>
        <p class="preset-note">以下为作者实盘在用的因子组合，可一键加载；开源样例库为合成数据，回测结果仅供演示，不代表实盘收益。</p>
        <div class="preset-grid">
          <div class="preset-card preset-featured" @click="loadPreset('momentum')">
            <div class="preset-badge">🔥 推荐</div>
            <div class="preset-header">
              <span class="preset-icon">🚀</span>
              <div>
                <h3>动量轮动精选</h3>
                <span class="preset-tag">动量轮动 · 进攻型</span>
              </div>
            </div>
            <div class="preset-body">
              <div class="preset-factors">
                <span class="factor-chip">REVS20 40% <em>20日高点动量</em></span>
                <span class="factor-chip">Rtn20 30% <em>20日收益率</em></span>
                <span class="factor-chip">CORD20 30% <em>收益量价相关</em></span>
              </div>
              <div class="preset-params">
                <span>🔝 Top 10</span><span>🔄 月度调仓</span><span>❌ 淘汰3只</span><span>💰 100只股票池</span>
              </div>
            </div>
            <el-button type="primary" size="small" round>一键加载 →</el-button>
          </div>

          <div class="preset-card" @click="loadPreset('lowvol')">
            <div class="preset-header">
              <span class="preset-icon">🛡️</span>
              <div>
                <h3>动量+低波动</h3>
                <span class="preset-tag">低波动叠加 · 防御型</span>
              </div>
            </div>
            <div class="preset-body">
              <div class="preset-factors">
                <span class="factor-chip">REVS20 50%</span>
                <span class="factor-chip">Rtn20 20%</span>
                <span class="factor-chip down">STD20 -30%</span>
              </div>
              <div class="preset-params">
                <span>🔝 Top 10</span><span>🔄 月度调仓</span><span>❌ 淘汰3只</span>
              </div>
            </div>
            <el-button size="small" round>一键加载 →</el-button>
          </div>

          <div class="preset-card" @click="loadPreset('balanced')">
            <div class="preset-header">
              <span class="preset-icon">⚖️</span>
              <div>
                <h3>均衡四因子</h3>
                <span class="preset-tag">均衡配置 · 稳健型</span>
              </div>
            </div>
            <div class="preset-body">
              <div class="preset-factors">
                <span class="factor-chip">REVS20 25%</span>
                <span class="factor-chip">Rtn20 25%</span>
                <span class="factor-chip">CORD20 25%</span>
                <span class="factor-chip down">STD20 -25%</span>
              </div>
              <div class="preset-params">
                <span>🔝 Top 10</span><span>🔄 月度调仓</span><span>❌ 淘汰5只</span>
              </div>
            </div>
            <el-button size="small" round>一键加载 →</el-button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">🎯 多因子轮动配置</div>
        <div v-if="candidatePool.length" class="candidate-bar">
          🎯 候选池: <strong>{{ candidatePool.length }}</strong> 只 (来自AI选股)
          <el-switch v-model="topkForm.use_candidate" size="small" style="margin-left:8px" active-text="使用" />
          <span v-if="topkForm.use_candidate" style="font-size:11px;color:#7A8494;margin-left:4px">股票池将限定为候选池内股票</span>
        </div>
        <div class="topk-layout">
          <!-- 左：因子选择 -->
          <div class="topk-factors">
            <div class="topk-label">选择 Alpha158 因子（多选，最多10个）</div>
            <div v-if="topkFactorsLoading" style="color:#7A8494;padding:20px">加载因子列表...</div>
            <div v-else-if="topkFactorsError" style="color:#f87171;padding:20px">
              ⚠️ 因子加载失败
              <button class="btn-link" @click="loadTopkFactors()" style="margin-left:8px;color:#60A5FA;border:none;background:none;cursor:pointer">重试</button>
            </div>
            <div v-else-if="!Object.keys(topkFactorCats).length" style="color:#7A8494;padding:20px">暂无因子数据，请检查后端服务</div>
            <div v-else class="factor-cats">
              <div v-for="(keys, cat) in topkFactorCats" :key="cat" class="factor-cat">
                <div class="cat-name">{{ cat }}</div>
                <el-checkbox-group v-model="topkForm.factors" class="factor-grid" :max="10">
                  <el-checkbox v-for="k in keys" :key="k" :value="k" :label="topkFactorMap[k]?.label || k" />
                </el-checkbox-group>
              </div>
            </div>
            <div v-if="topkForm.factors.length" class="topk-weights">
              <div class="topk-label">因子权重（等权 / 自定义）</div>
              <div class="weight-rows">
                <div v-for="f in topkForm.factors" :key="'w'+f" class="weight-row">
                  <span class="w-name">{{ topkFactorMap[f]?.label || f }}</span>
                  <el-slider v-model="topkWeights[f]" :min="-100" :max="100" size="small" class="w-slider" />
                  <el-input-number v-model="topkWeights[f]" :min="-100" :max="100" size="small" controls-position="right" class="w-input" />
                </div>
              </div>
              <div class="w-total" :class="{ ok: topkWeightSum === 100, bad: topkWeightSum !== 100 }">
                权重合计(绝对值): {{ topkWeightSum }}%
              </div>
            </div>
          </div>
          <!-- 右：回测参数 -->
          <div class="topk-params">
            <div class="topk-label">回测参数</div>
            <el-form label-width="100px" size="small">
              <el-form-item label="持仓数 TopK">
                <el-slider v-model="topkForm.top_k" :min="2" :max="30" show-input />
              </el-form-item>
              <el-form-item label="淘汰数">
                <el-slider v-model="topkForm.n_drop" :min="1" :max="topkForm.top_k" show-input />
              </el-form-item>
              <el-form-item label="调仓频率">
                <el-select v-model="topkForm.rebalance_freq" style="width:120px">
                  <el-option label="每月" value="month" />
                  <el-option label="每周" value="week" />
                  <el-option label="每5日" value="day" />
                </el-select>
              </el-form-item>
              <el-form-item label="回测天数">
                <el-input-number v-model="topkForm.days" :min="100" :max="1500" :step="100" />
              </el-form-item>
              <el-form-item label="初始资金(万)">
                <el-input-number v-model="topkForm.initial_cash" :min="10" :max="5000" :step="10" />
              </el-form-item>
              <el-form-item label="最小持有(天)">
                <el-input-number v-model="topkForm.hold_thresh" :min="1" :max="60" :step="1" />
              </el-form-item>
            </el-form>
            <el-button type="primary" size="large" @click="runTopkBacktest"
              :loading="topkRunning" :disabled="topkForm.factors.length === 0 || topkWeightSum !== 100"
              style="width:100%">
              🚀 运行多因子轮动回测
            </el-button>
            <!-- 进度条 -->
            <div v-if="topkRunning" style="margin-top:10px">
              <div style="font-size:12px;color:#98A2B3;margin-bottom:4px">{{ topkProgressMsg || '准备中...' }}</div>
              <el-progress :percentage="topkProgress" :show-text="false" :stroke-width="8" :color="topkProgress === 100 ? '#4ADE80' : '#60A5FA'" />
              <div style="text-align:right;font-size:11px;color:#7A8494;margin-top:2px">{{ topkProgress }}%</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 🕘 历史回测（本地落盘，重启不丢；只显示本访客自己的） -->
      <div class="card">
        <div class="card-title" style="display:flex;align-items:center;justify-content:space-between">
          <span>🕘 历史回测</span>
          <div style="display:flex;align-items:center;gap:4px">
            <el-button size="small" text @click="loadHistory" :loading="histLoading">刷新</el-button>
            <el-button size="small" text :disabled="!histItems.length" @click="clearHistory">🗑 清空</el-button>
          </div>
        </div>
        <div v-if="histLoading" class="hist-empty">加载中...</div>
        <div v-else-if="!histItems.length" class="hist-empty">
          暂无历史记录 —— 每次运行回测后自动保存，最多保留最近 50 条
        </div>
        <div v-else class="hist-list">
          <div v-for="it in histItems" :key="it.task_id" class="hist-row"
               :class="{ disabled: !it.has_result }" @click="loadHistoryItem(it)">
            <div class="hist-top">
              <span class="hist-time">{{ fmtTime(it.finished_at || it.created_at) }}</span>
              <el-tag :type="it.status === 'done' ? 'success' : it.status === 'error' ? 'danger' : 'info'"
                      size="small" effect="plain">{{ statusText(it.status) }}</el-tag>
              <span class="hist-id">{{ it.task_id }}</span>
            </div>
            <div class="hist-body">
              <span class="hist-factors">{{ (it.params?.factors || []).map(f => topkFactorMap[f]?.label || f).join(' · ') || '—' }}</span>
              <span class="hist-params">Top{{ it.params?.top_k }} · {{ freqText(it.params?.rebalance_freq) }}调仓 · {{ it.params?.days }}日</span>
              <span class="hist-load">{{ it.has_result ? '载入 →' : '无结果' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- TopK 回测结果 -->
      <div class="card" id="topk-result" v-if="topkResult">
        <div class="card-title">📊 轮动回测结果</div>
        <!-- 核心指标 -->
        <div class="topk-overview">
          <div class="metric-item" :class="topkResult.overview.total_return_pct >= 0 ? 'metric-up' : 'metric-down'">
            <div class="mi-icon">{{ topkResult.overview.total_return_pct >= 0 ? '📈' : '📉' }}</div>
            <div class="mi-body">
              <div class="mi-val">{{ (topkResult.overview.total_return_pct >= 0 ? '+' : '') + topkResult.overview.total_return_pct.toFixed(2) }}%</div>
              <div class="mi-label">总收益率</div>
            </div>
          </div>
          <div class="metric-item metric-up">
            <div class="mi-icon">📊</div>
            <div class="mi-body">
              <div class="mi-val">{{ topkResult.overview.annual_return_pct.toFixed(2) }}%</div>
              <div class="mi-label">年化收益</div>
            </div>
          </div>
          <div class="metric-item" :class="topkResult.overview.sharpe_ratio >= 1 ? 'metric-up' : topkResult.overview.sharpe_ratio >= 0.5 ? 'metric-neutral' : 'metric-down'">
            <div class="mi-icon">⚖️</div>
            <div class="mi-body">
              <div class="mi-val">{{ topkResult.overview.sharpe_ratio.toFixed(2) }}</div>
              <div class="mi-label">夏普比率</div>
            </div>
          </div>
          <div class="metric-item metric-down">
            <div class="mi-icon">🔻</div>
            <div class="mi-body">
              <div class="mi-val">-{{ topkResult.overview.max_drawdown_pct.toFixed(2) }}%</div>
              <div class="mi-label">最大回撤</div>
            </div>
          </div>
          <div class="metric-item" :class="topkResult.overview.win_rate_pct >= 50 ? 'metric-up' : 'metric-down'">
            <div class="mi-icon">🎯</div>
            <div class="mi-body">
              <div class="mi-val">{{ topkResult.overview.win_rate_pct.toFixed(1) }}%</div>
              <div class="mi-label">胜率</div>
            </div>
          </div>
          <div class="metric-item metric-neutral">
            <div class="mi-icon">🔄</div>
            <div class="mi-body">
              <div class="mi-val">{{ topkResult.overview.total_trades }}</div>
              <div class="mi-label">总交易</div>
            </div>
          </div>
        </div>
        <div class="topk-config-info">
          <el-tag size="small">Top{{ topkResult.strategy_config.top_k }}</el-tag>
          <el-tag size="small" type="info">{{ topkResult.strategy_config.rebalance_freq === 'month' ? '月度' : topkResult.strategy_config.rebalance_freq === 'week' ? '周度' : '5日' }}调仓</el-tag>
          <el-tag size="small" type="warning">全市场 {{ topkResult.strategy_config.universe_size }} 只</el-tag>
          <el-tag size="small">{{ topkResult.strategy_config.backtest_days }}个交易日</el-tag>
          <el-tag size="small" type="success">{{ topkResult.strategy_config.rebalance_count }}次调仓</el-tag>
        </div>

        <!-- 策略因子明细（strategy_config.factors 是因子 key 数组，weights 按位对应） -->
        <div class="factor-detail-row" style="margin-top:12px">
          <span style="font-size:13px;color:#98A2B3">因子构成：</span>
          <el-tag v-for="(f, i) in topkResult.strategy_config.factors" :key="f" size="small" effect="plain">
            {{ topkFactorMap[f]?.label || f }} ({{ Math.round((topkResult.strategy_config.weights?.[i] ?? 0) * 100) }}%)
          </el-tag>
        </div>

        <!-- 权益曲线图 -->
        <div style="margin-top: 20px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
            <span style="font-weight:600;font-size:14px;color:#C9D1DB">📈 权益曲线</span>
            <div style="display:flex;gap:16px;font-size:12px">
              <span><span style="display:inline-block;width:12px;height:12px;border-radius:2px;background:#60A5FA;margin-right:4px"></span>策略</span>
              <span v-if="topkResult.benchmark"><span style="display:inline-block;width:12px;height:12px;border-radius:2px;background:#7A8494;margin-right:4px"></span>{{ topkResult.benchmark.label }}</span>
            </div>
          </div>
          <v-chart :option="topkEquityChartOption" style="height:280px" autoresize />
        </div>

        <!-- 基准对比 -->
        <div v-if="topkResult.benchmark" class="bench-compare">
          <div class="bc-item">
            <div class="bc-label">{{ topkResult.benchmark.label }}同期收益</div>
            <div class="bc-val" :class="topkResult.benchmark.total_return_pct >= 0 ? 'up' : 'down'">
              {{ (topkResult.benchmark.total_return_pct >= 0 ? '+' : '') + topkResult.benchmark.total_return_pct.toFixed(2) }}%
            </div>
          </div>
          <div class="bc-item">
            <div class="bc-label">超额收益 α</div>
            <div class="bc-val" :class="(topkResult.overview.total_return_pct - topkResult.benchmark.total_return_pct) >= 0 ? 'up' : 'down'">
              {{ `${(topkResult.overview.total_return_pct - topkResult.benchmark.total_return_pct) >= 0 ? '+' : ''}${(topkResult.overview.total_return_pct - topkResult.benchmark.total_return_pct).toFixed(2)}%` }}
            </div>
          </div>
          <div class="bc-item">
            <div class="bc-label">跟踪误差</div>
            <div class="bc-val neutral">{{ topkResult.overview.tracking_error != null ? topkResult.overview.tracking_error + '%' : '-' }}</div>
          </div>
        </div>

        <!-- 策略审计 -->
        <div v-if="topkResult.audit" style="margin-top:16px;background:rgba(245,158,11,0.14);border:1px solid #F59E0B;border-radius:8px;padding:14px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <span style="font-size:16px">🔍</span>
            <strong style="font-size:14px;color:#FBBF24">策略审计报告</strong>
            <el-tag :type="topkResult.audit.overall_risk === '低' ? 'success' : topkResult.audit.overall_risk === '中' ? 'warning' : 'danger'" size="small">
              风险: {{ topkResult.audit.overall_risk }}
            </el-tag>
          </div>
          <!-- 跳过的因子 -->
          <div v-if="topkResult.strategy_config.skipped_factors?.length" style="background:rgba(245,158,11,0.14);border-radius:6px;padding:8px 12px;margin-bottom:10px;font-size:13px;color:#FBBF24">
            ⚠️ {{ topkResult.strategy_config.skipped_factors.join(', ') }} 不在因子库中，已自动跳过
          </div>
          <div v-for="issue in topkResult.audit.issues" :key="issue.check" style="display:flex;align-items:flex-start;gap:6px;margin-bottom:4px;font-size:13px">
            <span style="flex-shrink:0;margin-top:1px">{{ issue.status === 'pass' ? '✅' : '⚠️' }}</span>
            <div>
              <span style="font-weight:600;color:#C9D1DB">{{ issue.check }}</span>
              <span style="color:#98A2B3"> — {{ issue.detail }}</span>
            </div>
          </div>
          <div v-if="topkResult.audit.warnings?.length" style="margin-top:8px;font-size:12px;color:#F59E0B">
            <div v-for="w in topkResult.audit.warnings" :key="w">💡 {{ w }}</div>
          </div>
        </div>

        <!-- 操作统计 -->
        <div style="margin-top:16px;display:grid;grid-template-columns:repeat(4,1fr);gap:12px">
          <div style="background:#12161D;border-radius:8px;padding:12px;text-align:center">
            <div style="font-size:20px;font-weight:700;color:#4ADE80">{{ topkResult.overview.buy_count }}</div>
            <div style="font-size:12px;color:#7A8494">买入次数</div>
          </div>
          <div style="background:#12161D;border-radius:8px;padding:12px;text-align:center">
            <div style="font-size:20px;font-weight:700;color:#F87171">{{ topkResult.overview.sell_count }}</div>
            <div style="font-size:12px;color:#7A8494">卖出次数</div>
          </div>
          <div style="background:#12161D;border-radius:8px;padding:12px;text-align:center">
            <div style="font-size:20px;font-weight:700;color:#60A5FA">{{ topkResult.overview.rebalance_operations }}</div>
            <div style="font-size:12px;color:#7A8494">调仓操作</div>
          </div>
          <div style="background:#12161D;border-radius:8px;padding:12px;text-align:center">
            <div style="font-size:20px;font-weight:700;color:#F59E0B">{{ (topkResult.overview.rebalance_operations / Math.max(topkResult.strategy_config.rebalance_count, 1)).toFixed(1) }}</div>
            <div style="font-size:12px;color:#7A8494">均调仓交易</div>
          </div>
        </div>

        <!-- 最近交易记录（折叠） -->
        <el-collapse v-if="topkResult.trades?.length" style="margin-top:16px;border:none">
          <el-collapse-item :title="'📋 交易记录 (' + topkResult.trades.length + '笔) | 范围: ' + (topkResult.trades[0]?.date || '') + ' ~ ' + (topkResult.trades[topkResult.trades.length-1]?.date || '')">
            <el-table :data="topkResult.trades" size="small" max-height="360" stripe
              :default-sort="{prop:'date',order:'descending'}">
              <el-table-column prop="date" label="日期" width="110" sortable />
              <el-table-column prop="action" label="操作" width="70">
                <template #default="{ row }">
                  <el-tag :type="row.action === '买入' ? 'success' : 'danger'" size="small">{{ row.action }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="stock" label="股票" width="100" />
              <el-table-column prop="price" label="价格" width="80" />
              <el-table-column prop="shares" label="股数" width="80" />
              <el-table-column prop="amount" label="成交金额" width="110">
                <template #default="{ row }">¥{{ row.amount?.toLocaleString() }}</template>
              </el-table-column>
              <el-table-column label="账户总金额" width="120">
                <template #default="{ row }">
                  ¥{{ row.account_total?.toLocaleString() }}
                </template>
              </el-table-column>
              <el-table-column prop="reason" label="原因" min-width="160" show-overflow-tooltip />
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </div>

      <!-- TopK 报错 -->
      <div class="card err-card" v-if="topkError">
        <el-alert :title="topkError" type="error" show-icon :closable="false" />
      </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import VChart from 'vue-echarts'
import api from '../api'

// ═══ TopK 多因子轮动 ═══
const topkFactorCats = ref({})      // { 分类: [因子key, ...] }
const topkFactorMap = ref({})       // { 因子key: {key,label,desc} }
const topkFactorsLoading = ref(false)
const topkFactorsError = ref(false)
const topkRunning = ref(false)
const topkProgress = ref(0)
const topkProgressMsg = ref('')
const topkTaskId = ref(null)
const topkResult = ref(null)
const topkError = ref('')
const skipWeightReset = ref(false)
const candidatePool = ref([])

// 历史回测（后端落盘，按匿名访客隔离）
const histLoading = ref(false)
const histItems = ref([])

function fmtTime(s) {
  if (!s) return '—'
  const d = new Date(s)
  if (isNaN(d.getTime())) return String(s).slice(0, 16).replace('T', ' ')
  const p = n => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function statusText(s) {
  return s === 'done' ? '完成' : s === 'error' ? '失败' : s === 'running' ? '运行中' : '排队中'
}

function freqText(f) {
  return f === 'month' ? '月度' : f === 'week' ? '周度' : '5日'
}

async function loadHistory() {
  histLoading.value = true
  try {
    const r = await api.get('/backtest/topk/history', { params: { limit: 20 } })
    histItems.value = r.data.items || []
  } catch (e) {
    histItems.value = []
  } finally {
    histLoading.value = false
  }
}

// 清空本访客的全部回测历史（仅限自己的）
async function clearHistory() {
  const n = histItems.value.length
  try {
    await ElMessageBox.confirm(
      `将删除你在本机的全部回测历史（当前 ${n} 条），只影响你自己的记录，删除后不可恢复。继续？`,
      '清空回测历史',
      { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' }
    )
  } catch (e) {
    return   // 取消
  }
  try {
    const r = await api.delete('/backtest/topk/history')
    const d = r.data || {}
    await loadHistory()
    let msg = `已清空 ${d.deleted ?? 0} 条历史记录`
    if (d.skipped_running) msg += `（${d.skipped_running} 条运行中，保留）`
    ElMessage.success(msg)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '清空失败')
  }
}

// 点击历史记录：载入结果 + 回填参数，方便微调后重跑
async function loadHistoryItem(it) {
  if (!it.has_result) return
  topkError.value = ''
  try {
    const r = await api.get(`/backtest/topk/status/${it.task_id}`)
    const res = r.data.result
    if (!res) { topkError.value = '该任务没有可用的结果'; return }
    topkResult.value = res

    // 回填表单（策略配置里 factors 是因子 key 数组，weights 与之按位对应）
    const cfg = res.strategy_config || {}
    const fs = cfg.factors || []
    const ws = cfg.weights || []
    skipWeightReset.value = true
    topkForm.factors = fs.map(f => (typeof f === 'string' ? f : f.key))
    Object.keys(topkWeights).forEach(k => delete topkWeights[k])
    topkForm.factors.forEach((f, i) => {
      topkWeights[f] = Math.round((ws[i] ?? 0) * 100)
    })
    if (cfg.top_k) topkForm.top_k = cfg.top_k
    if (cfg.n_drop) topkForm.n_drop = Math.min(cfg.n_drop, cfg.top_k || 30)
    if (cfg.rebalance_freq) topkForm.rebalance_freq = cfg.rebalance_freq
    if (cfg.backtest_days) topkForm.days = cfg.backtest_days
    nextTick(() => {
      skipWeightReset.value = false
      document.getElementById('topk-result')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  } catch (e) {
    topkError.value = e?.response?.data?.detail || e?.message || '载入失败'
  }
}

const topkForm = reactive({
  factors: [],
  top_k: 10,
  n_drop: 3,
  rebalance_freq: 'month',
  days: 500,
  initial_cash: 100,   // 单位：万
  hold_thresh: 1,
  use_candidate: true,
})
const topkWeights = reactive({})

const topkWeightSum = computed(() =>
  topkForm.factors.map(f => Math.abs(topkWeights[f] || 0)).reduce((a, b) => a + b, 0))

const topkEquityChartOption = computed(() => {
  const r = topkResult.value
  if (!r || !r.equity_curve || !r.equity_curve.length) return {}
  const dates = r.equity_curve.map(x => x.date)
  const series = [{
    name: '策略净值', type: 'line', data: r.equity_curve.map(x => x.equity),
    smooth: true, showSymbol: false, lineStyle: { color: '#60A5FA', width: 2 },
    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
      { offset: 0, color: 'rgba(99,102,241,0.25)' },
      { offset: 1, color: 'rgba(99,102,241,0.02)' }] } },
  }]
  const bm = r.benchmark
  if (bm && bm.equity_curve && bm.equity_curve.length) {
    series.push({
      name: bm.label || '基准', type: 'line',
      data: bm.equity_curve.map(x => x.equity), smooth: true, showSymbol: false,
      lineStyle: { color: '#7A8494', width: 1.5, type: 'dashed' },
    })
  }
  return {
    textStyle: { color: '#98A2B3' },
    tooltip: { trigger: 'axis', backgroundColor: '#1C222C', borderColor: '#333C49', textStyle: { color: '#E6E9EE' } },
    legend: { data: series.map(x => x.name), right: 0, top: 0, textStyle: { fontSize: 12, color: '#98A2B3' } },
    grid: { left: 8, right: 16, top: 34, bottom: 8, containLabel: true },
    xAxis: { type: 'category', data: dates, boundaryGap: false, axisLabel: { fontSize: 11, color: '#7A8494' }, axisLine: { lineStyle: { color: '#262D38' } } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 11, color: '#7A8494' }, splitLine: { lineStyle: { color: '#1C222C' } } },
    series,
  }
})

async function loadTopkFactors() {
  if (topkFactorsLoading.value) return
  topkFactorsLoading.value = true
  topkFactorsError.value = false
  try {
    const r = await api.get('/backtest/topk/factors')
    const cats = {}, map = {}
    const src = (r.data && r.data.categories) || {}
    for (const [cat, items] of Object.entries(src)) {
      cats[cat] = items.map(it => it.key)
      items.forEach(it => { map[it.key] = it })
    }
    topkFactorCats.value = cats
    topkFactorMap.value = map
  } catch (e) {
    topkFactorsError.value = true
  } finally {
    topkFactorsLoading.value = false
  }
}

const presets = {
  momentum: { factors: ['REVS20', 'Rtn20', 'CORD20'], weights: { REVS20: 40, Rtn20: 30, CORD20: 30 }, top_k: 10, n_drop: 3, rebalance_freq: 'month', days: 500, initial_cash: 100, hold_thresh: 1 },
  lowvol:   { factors: ['REVS20', 'Rtn20', 'STD20'], weights: { REVS20: 50, Rtn20: 20, STD20: -30 }, top_k: 10, n_drop: 3, rebalance_freq: 'month', days: 500, initial_cash: 100, hold_thresh: 1 },
  balanced: { factors: ['REVS20', 'Rtn20', 'CORD20', 'STD20'], weights: { REVS20: 25, Rtn20: 25, CORD20: 25, STD20: -25 }, top_k: 10, n_drop: 5, rebalance_freq: 'month', days: 500, initial_cash: 100, hold_thresh: 1 },
}

function loadPresetData(p) {
  skipWeightReset.value = true
  topkForm.factors = [...(p.factors || [])]
  Object.keys(topkWeights).forEach(k => delete topkWeights[k])
  Object.entries(p.weights || {}).forEach(([k, v]) => { topkWeights[k] = v })
  ;['top_k', 'n_drop', 'rebalance_freq', 'days', 'initial_cash', 'hold_thresh'].forEach(k => {
    if (p[k] !== undefined) topkForm[k] = p[k]
  })
  nextTick(() => { skipWeightReset.value = false })
}

function loadPreset(key) {
  if (presets[key]) loadPresetData(presets[key])
}

async function runTopkBacktest() {
  if (!topkForm.factors.length || topkWeightSum.value !== 100) return
  topkRunning.value = true
  topkProgress.value = 0
  topkProgressMsg.value = ''
  topkError.value = ''
  topkResult.value = null
  try {
    const payload = {
      factors: topkForm.factors,
      weights: topkForm.factors.map(f => (topkWeights[f] || 0) / 100),
      top_k: topkForm.top_k,
      n_drop: topkForm.n_drop,
      rebalance_freq: topkForm.rebalance_freq,
      days: topkForm.days,
      initial_cash: topkForm.initial_cash * 10000,
      hold_thresh: topkForm.hold_thresh,
    }
    if (topkForm.use_candidate && candidatePool.value.length) {
      payload.custom_pool = candidatePool.value
    }
    const r = await api.post('/backtest/topk', payload)
    const taskId = r.data.task_id
    topkTaskId.value = taskId

    // 轮询进度
    for (;;) {
      await new Promise(res => setTimeout(res, 1200))
      const sr = await api.get(`/backtest/topk/status/${taskId}`)
      topkProgress.value = sr.data.progress || 0
      topkProgressMsg.value = sr.data.message || ''
      if (sr.data.status === 'done') {
        topkResult.value = sr.data.result
        break
      } else if (sr.data.status === 'error') {
        topkError.value = sr.data.error || '回测失败'
        break
      }
    }
  } catch (e) {
    topkError.value = e?.response?.data?.detail || e?.message || '请求失败'
  } finally {
    topkRunning.value = false
  }
}

// 勾选因子变化 → 自动等权
watch(() => topkForm.factors.join(','), () => {
  if (skipWeightReset.value) return
  const n = topkForm.factors.length
  if (!n) return
  const v = Math.round(100 / n)
  topkForm.factors.forEach(f => { topkWeights[f] = v })
})

onMounted(async () => {
  // 候选池（来自 AI 选股页）
  try {
    const raw = localStorage.getItem('backtest_candidate_pool')
    if (raw) {
      const data = JSON.parse(raw)
      candidatePool.value = data.codes || data || []
      localStorage.removeItem('backtest_candidate_pool')
    }
  } catch (e) { /* ignore */ }

  await loadTopkFactors()
  loadHistory()

  // 预设（来自其他页面跳转）
  try {
    const raw = localStorage.getItem('topk_preset')
    if (raw) {
      loadPresetData(JSON.parse(raw))
      localStorage.removeItem('topk_preset')
    }
  } catch (e) { /* ignore */ }
})
</script>

<style scoped>
.bt-page { max-width: 900px; margin: 0 auto; padding-bottom: 40px; }.ph { margin: 0 0 4px; font-size: 20px; }
.ph-sub { margin: 0 0 20px; color: #7A8494; font-size: 13px; }

.card {
  background: var(--card-bg); border-radius: 8px; padding: 20px; margin-bottom: 14px;
}
.card-head {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
  flex-wrap: wrap; gap: 8px;
}
.card-title { font-size: 15px; font-weight: 700; }
.card-tip { font-size: 11px; color: #7A8494; margin-left: 10px; }
.head-actions { display: flex; gap: 6px; }
.collapse-arrow { font-size: 14px; color: #7A8494; transition: transform .2s; }
.collapse-arrow.open { transform: rotate(180deg); }

/* Modes */
.mode-tabs { display: flex; gap: 8px; margin-bottom: 14px; }
.mode-tab {
  flex: 1; display: flex; align-items: center; gap: 10px;
  padding: 12px; border: 2px solid #262D38; border-radius: 8px; cursor: pointer;
  transition: all .2s; font-size: 13px;
}
.mode-tab:hover { border-color: #7A8494; }
.mode-tab.active { border-color: #60A5FA; background: rgba(59,130,246,0.12); }
.m-icon { font-size: 22px; }
.m-name { font-weight: 700; }
.m-desc { font-size: 11px; color: #7A8494; margin-top: 1px; }

.stock-row { display: flex; flex-direction: column; gap: 8px; }
.picked-tags { display: flex; gap: 6px; flex-wrap: wrap; }

/* Editor */
.editor-wrap { position: relative; }
.editor-wrap.empty::after {
  content: ''; position: absolute; inset: 0; pointer-events: none;
}
.code-editor {
  width: 100%; min-height: 220px; max-height: 500px;
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  font-size: 13px; line-height: 1.6; padding: 16px;
  border: 1px solid #262D38; border-radius: 8px; resize: vertical;
  background: var(--surface-2); color: var(--text-primary); outline: none; tab-size: 4;
}
.code-editor:focus { border-color: #60A5FA; }
.code-editor::placeholder { color: #98A2B3; }
.editor-status { padding: 6px 12px 0; font-size: 11px; color: #7A8494; }
.es-empty { color: #333B47; }

/* Config */
.config-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.ci { display: flex; flex-direction: column; gap: 4px; }
.ci label { font-size: 13px; font-weight: 600; }
.ci-hint { font-size: 11px; color: #7A8494; }

.run-btn { width: 100%; height: 48px; font-size: 16px; font-weight: 700; border-radius: 8px; }
.hint { text-align: center; color: #333B47; font-size: 13px; margin: 10px 0 0; }

.err-card { background: rgba(239,68,68,0.12); border-color: rgba(239,68,68,0.35); }
.err-detail { margin-top: 12px; }
.err-detail pre {
  background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.35); border-radius: 6px;
  padding: 12px; font-size: 12px; line-height: 1.5; font-family: monospace;
  color: #FCA5A5; overflow-x: auto; white-space: pre-wrap; margin: 0;
}

/* Results */
.res-stock-line { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.res-stock { font-size: 18px; font-weight: 800; }

.metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 18px; }
.metric { text-align: center; padding: 14px 8px; background: #12161D; border-radius: 8px; }
.mlabel { font-size: 11px; color: #7A8494; margin-bottom: 4px; }
.mnum { font-size: 20px; font-weight: 800; }
.mnum.sm { font-size: 16px; }
.mnum.warn { color: #F59E0B; }

.section-title { font-size: 14px; font-weight: 700; margin: 16px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #161C24; }
.chart-section { margin-bottom: 10px; }
.chart-badge { font-size: 10px; background: #60A5FA; color: #fff; padding: 1px 8px; border-radius: 8px; margin-left: 8px; font-weight: 600; }
.chart-row { display: flex; flex-direction: column; gap: 16px; }
.chart-box { background: #12161D; border-radius: 8px; padding: 12px; border: 1px solid #161C24; }
.chart-box.full { width: 100%; }
.chart-empty { text-align: center; padding: 40px; color: #7A8494; font-size: 13px; background: #12161D; border-radius: 8px; border: 1px dashed #262D38; }

.tstats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.ts-item { display: flex; justify-content: space-between; padding: 8px 12px; background: #12161D; border-radius: 6px; font-size: 13px; }
.ts-item span { color: #7A8494; }
.ts-item strong { color: #C9D1DB; }

/* 风险指标 */
.risk-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; padding-top: 12px; border-top: 1px solid #262D38; justify-content: center; }
.rk-item { flex: 0 0 auto; min-width: 90px; padding: 6px 10px; background: #12161D; border-radius: 6px; text-align: center; }
.rk-item span { display: block; font-size: 11px; color: #7A8494; margin-bottom: 2px; }
.rk-item strong { font-size: 14px; }

/* Stock list for comprehensive */
.stock-list { display: flex; flex-direction: column; gap: 8px; }
.stock-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: #12161D; border-radius: 8px; }
.si-name { font-weight: 600; font-size: 14px; }
.si-code { font-size: 11px; color: #7A8494; margin-left: 8px; }
.si-metrics { display: flex; gap: 16px; align-items: center; font-size: 14px; font-weight: 700; }
.si-trades { font-size: 12px; color: #7A8494; font-weight: 400; }

.no-trades { text-align: center; padding: 20px; color: #7A8494; }
.no-trades p { margin: 0 0 4px; font-size: 14px; }
.nt-tip { font-size: 12px; color: #333B47; }

/* 诊断面板 */
.nt-diag { margin-top: 14px; padding: 14px; background: rgba(59,130,246,0.10); border: 1px solid rgba(56,189,248,0.35); border-radius: 8px; text-align: left; }
.diag-title { font-size: 13px; font-weight: 700; color: #38BDF8; margin-bottom: 8px; }
.diag-meta { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 11px; color: #98A2B3; margin-bottom: 10px; }
.diag-table { font-size: 12px; margin-bottom: 10px; }
.diag-row { display: flex; padding: 3px 0; border-bottom: 1px solid #262D38; }
.diag-row-hd { color: #7A8494; font-weight: 600; font-size: 11px; }
.diag-row span:first-child { flex: 1; color: #C9D1DB; }
.diag-row span:nth-child(2) { width: 56px; text-align: right; }
.diag-row span:nth-child(3) { width: 48px; text-align: right; color: #7A8494; }
.diag-count { color: #38BDF8; font-weight: 600; }
.diag-suggest { font-size: 12px; color: #A4AEBB; }
.diag-stitle { font-weight: 600; margin-bottom: 4px; color: #F59E0B; }
.diag-suggest ul { margin: 0; padding-left: 16px; }
.diag-suggest li { margin-bottom: 3px; line-height: 1.5; }

.c-g { color: #4ADE80 !important; }
.c-r { color: #F87171 !important; }

/* ─── Qlib 引擎 ─── */
.qlib-opt-result { margin-top: 12px; padding: 12px; background: rgba(34,197,94,0.12); border-radius: 8px; border: 1px solid rgba(34,197,94,0.35); }
.qlib-opt-title { font-size: 13px; font-weight: 700; color: #4ADE80; margin-bottom: 8px; }
.qlib-opt-params { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }

/* ─── 引擎切换标签 ─── */
.page-top { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.engine-tabs { display: flex; gap: 0; background: #161C24; border-radius: 8px; padding: 3px; flex-shrink: 0; }
.engine-tab { padding: 8px 18px; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .2s; background: transparent; color: #98A2B3; white-space: nowrap; }
.engine-tab:hover { color: #C9D1DB; }
.engine-tab.active { background: var(--card-bg); color: #60A5FA; }

/* ─── Qlib 策略卡片 ─── */
.qlib-strategy-picker { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; margin-bottom: 16px; }
.qlib-strat-card { padding: 14px; border: 2px solid #262D38; border-radius: 8px; cursor: pointer; transition: all .15s; background: var(--card-bg); }
.qlib-strat-card:hover { border-color: rgba(96,165,250,0.5); background: #12161D; }
.qlib-strat-card.active { border-color: #60A5FA; background: rgba(59,130,246,0.12); }
.qs-icon { font-size: 22px; margin-bottom: 6px; }
.qs-name { font-size: 13px; font-weight: 700; color: #C9D1DB; }
.qs-desc { font-size: 11px; color: #7A8494; margin-top: 3px; line-height: 1.4; }

/* ─── Qlib 配置 ─── */
.qlib-config { margin-top: 4px; }
.qlib-config-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-size: 13px; font-weight: 600; color: #A4AEBB; }
.qlib-config-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.qlib-param-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.qlib-actions { display: flex; gap: 10px; margin-top: 14px; }

/* ─── Qlib 模式切换 ─── */
.qlib-mode-row { display: flex; align-items: center; gap: 10px; margin-top: 16px; padding-top: 14px; border-top: 1px solid #161C24; }
.qlib-mode-label { font-size: 12px; color: #7A8494; font-weight: 500; }
.qlib-mode-tabs { display: flex; gap: 0; background: #161C24; border-radius: 8px; padding: 2px; }
.qlib-mode-tab { padding: 6px 16px; border: none; border-radius: 7px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all .15s; background: transparent; color: #98A2B3; }
.qlib-mode-tab:hover { color: #C9D1DB; }
.qlib-mode-tab.active { background: #60A5FA; color: #fff; }
.qlib-mode-help { font-size: 14px; cursor: help; opacity: 0.5; }

/* ─── Qlib 官方指标条 ─── */
.qlib-metrics-bar { background: #12161D; border-radius: 8px; margin-bottom: 14px; border: 1px solid #262D38; overflow: hidden; }
.qm-head { font-size: 11px; font-weight: 700; color: #60A5FA; text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 14px; background: #12161D; border-bottom: 1px solid #262D38; }
.qm-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: #262D38; }
.qm-cell { padding: 10px 14px; background: var(--card-bg); display: flex; flex-direction: column; gap: 3px; }
.qm-cell.wide { grid-column: span 2; }
.qm-label { font-size: 10px; color: #7A8494; font-weight: 500; text-transform: uppercase; }
.qm-val { font-size: 13px; font-weight: 700; color: #C9D1DB; }
.qm-val.big { font-size: 18px; }

.cash-after { font-weight: 700; font-variant-numeric: tabular-nums; }

/* ─── TopK 多因子轮动 ─── */
.candidate-bar { background: rgba(245,158,11,0.14); border: 1px solid #F59E0B; border-radius: 6px; padding: 8px 12px; margin-bottom: 12px; font-size: 13px; color: #FBBF24; display: flex; align-items: center; }
.topk-layout { display: flex; gap: 24px; }
.topk-factors { flex: 3; min-width: 0; }
.topk-params { flex: 2; min-width: 300px; }
.topk-label { font-size: 14px; font-weight: 600; color: #C9D1DB; margin-bottom: 10px; }
.factor-cats { max-height: 350px; overflow-y: auto; }
.factor-cat { margin-bottom: 14px; }
.cat-name { font-size: 12px; color: #7A8494; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; font-weight: 600; }
.factor-grid { display: flex; flex-wrap: wrap; gap: 4px; }
.factor-grid .el-checkbox { margin-right: 8px; font-size: 12px; }
.topk-weights { margin-top: 16px; padding-top: 16px; border-top: 1px solid #262D38; }
.weight-rows { max-height: 250px; overflow-y: auto; }
.weight-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.w-name { flex: 0 0 100px; font-size: 12px; color: #A4AEBB; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.w-slider { flex: 1; }
.w-input { width: 80px; flex-shrink: 0; }
.w-total { text-align: right; margin-top: 8px; font-size: 13px; font-weight: 600; }
.w-total.ok { color: #4ADE80; }
.w-total.bad { color: #F87171; }
.topk-overview { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.topk-config-info { margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }

.metric-item {
  display: flex; align-items: center; gap: 10px;
  background: #12161D; border-radius: 8px; padding: 14px 16px;
  border-left: 4px solid transparent; transition: border-color .2s;
}
.metric-item.metric-up { border-left-color: #4ADE80; }
.metric-item.metric-down { border-left-color: #F87171; }
.metric-item.metric-neutral { border-left-color: #7A8494; }
.mi-icon { font-size: 22px; flex-shrink: 0; width: 32px; text-align: center; }
.mi-body { flex: 1; }
.mi-val { font-size: 20px; font-weight: 700; color: #C9D1DB; line-height: 1.2; }
.mi-label { font-size: 11px; color: #7A8494; margin-top: 2px; }

.bench-compare {
  margin-top: 16px;
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
  padding: 14px; background: #12161D; border-radius: 8px;
}
.bc-item { text-align: center; }
.bc-label { font-size: 12px; color: #7A8494; margin-bottom: 4px; }
.bc-val { font-size: 18px; font-weight: 700; }
.bc-val.up { color: #4ADE80; }
.bc-val.down { color: #F87171; }
.bc-val.neutral { color: #C9D1DB; }
.card-title { font-size: 16px; font-weight: 700; color: #C9D1DB; margin-bottom: 16px; }

/* ─── 推荐策略预设卡片 ─── */
.preset-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 0; }
.preset-card {
  background: var(--card-bg, #fff); border-radius: 8px;
  padding: 18px; cursor: pointer; transition: all 0.2s; border: 1px solid #262D38;
  display: flex; flex-direction: column; position: relative;
}
.preset-card:hover { transform: translateY(-2px); }
.preset-featured { border-color: #60A5FA; background: #12161D; }
.preset-badge {
  position: absolute; top: -1px; right: 16px;
  background: #60A5FA; color: white;
  padding: 2px 10px; border-radius: 0 0 6px 6px; font-size: 11px; font-weight: 600;
}
.preset-header { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 12px; }
.preset-icon { font-size: 26px; flex-shrink: 0; }
.preset-header h3 { margin: 0; font-size: 14px; font-weight: 600; color: #C9D1DB; }
.preset-tag { font-size: 11px; color: #7A8494; display: block; margin-top: 2px; }
.preset-note { font-size: 11px; color: #7A8494; margin: 0 0 12px; line-height: 1.5; }
.preset-body { flex: 1; }
.preset-factors { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
.factor-chip {
  display: inline-flex; align-items: center;
  padding: 2px 8px; border-radius: 8px;
  background: rgba(99,102,241,0.07); color: #60A5FA; font-size: 11px; font-weight: 500;
}
.factor-chip.down { background: rgba(239,68,68,0.07); color: #F87171; }
.factor-chip em { font-size: 10px; opacity: 0.65; font-style: normal; margin-left: 2px; }
.preset-params { display: flex; flex-wrap: wrap; gap: 6px; }
.preset-params span {
  font-size: 11px; color: #98A2B3;
  padding: 1px 7px; background: #12161D; border-radius: 4px;
}

@media (max-width: 900px) {
  .preset-grid { grid-template-columns: 1fr; }
}

/* 🕘 历史回测 */
.hist-empty { color: #7A8494; font-size: 13px; padding: 10px 0; }
.hist-list { display: flex; flex-direction: column; gap: 6px; }
.hist-row {
  display: flex; flex-direction: column; gap: 4px;
  padding: 9px 12px; border: 1px solid #262D38; border-radius: 8px;
  background: #12161D; cursor: pointer; transition: border-color .15s, background .15s;
}
.hist-row:hover { border-color: #3B82F6; background: #151A22; }
.hist-row.disabled { cursor: default; opacity: .55; }
.hist-row.disabled:hover { border-color: #262D38; background: #12161D; }
.hist-top { display: flex; align-items: center; gap: 8px; }
.hist-time { font-size: 12px; color: #E6E9EE; font-variant-numeric: tabular-nums; }
.hist-id { font-size: 11px; color: #5A6371; margin-left: auto; font-family: ui-monospace, monospace; }
.hist-body { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hist-factors { font-size: 12px; color: #98A2B3; }
.hist-params { font-size: 11px; color: #7A8494; }
.hist-load { margin-left: auto; font-size: 11px; color: #60A5FA; }
.hist-row.disabled .hist-load { color: #5A6371; }

.btn-link:hover { text-decoration: underline; }
</style>
