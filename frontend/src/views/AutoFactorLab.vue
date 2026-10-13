<template>
  <div class="af-shell">
    <div class="af-header">
      <h1>🧬 自动因子挖掘 Lab</h1>
      <p class="af-sub">RD-Agent 全自动 R→D 迭代闭环 · 沙盒数据（沪深300 + 成分股）· 训练集 2008–2014 · 验证集 2015–2017 · 测试集 2018–2025 · 结果仅供人工筛选</p>
    </div>

    <!-- 演示站：只读模式提示 -->
    <el-alert
      v-if="isDemo"
      class="af-demo-alert"
      type="warning"
      :closable="false"
      show-icon
      title="演示站为只读模式"
      description="历史挖掘记录可正常查看；受限于演示环境，不支持发起新的挖掘或清理（会消耗付费 LLM 额度）。本地部署即为完整功能。"
    />

    <!-- 配置 + 启动 -->
    <el-card class="af-card" shadow="never">
      <div class="af-config">
        <div class="af-config-item">
          <span class="af-label">迭代圈数</span>
          <el-input-number v-model="loopN" :min="1" :max="10" :disabled="running" />
          <span v-if="resumeMode" class="af-hint">在历史成果上续跑 {{ loopN }} 圈</span>
        </div>
        <div class="af-config-item">
          <el-switch v-model="resumeMode" :disabled="running || !hasResumeTarget" />
          <span class="af-label">续跑上次会话</span>
          <el-tooltip v-if="resumeMode && resumeTarget" placement="top"
                      :content="`续跑自 ${resumeTarget.job_id}（会话已完成 ${resumeTarget.session_loops ?? resumeTarget.total_loops ?? resumeTarget.loop_n} 圈 · 目标总圈数 ${resumeTarget.total_loops ?? resumeTarget.loop_n} 圈）`">
            <span class="af-hint af-hint-fit">
              续跑自 {{ resumeTarget.job_id }} · 已完成 {{ resumeTarget.session_loops ?? resumeTarget.total_loops ?? resumeTarget.loop_n }}/{{ resumeTarget.total_loops ?? resumeTarget.loop_n }} 圈
            </span>
          </el-tooltip>
          <span v-else-if="!hasResumeTarget" class="af-hint">暂无历史成果可续跑</span>
        </div>
        <el-button type="primary" :loading="running" :disabled="isDemo || running || (resumeMode && !hasResumeTarget)" @click="doStart">
          {{ running ? '挖掘中…' : (resumeMode ? '续跑挖掘' : '启动挖掘') }}
        </el-button>
        <!-- P0-4（2026-09-24）：一键「续挖到当前生效 SOTA 最高」的可续跑会话 -->
        <el-button type="warning" plain :disabled="isDemo || running || !bestSession" @click="doResumeBest">
          续挖到最佳会话
        </el-button>
        <el-tooltip v-if="bestSession" placement="top"
                    :content="`目标：${bestSession.job_id}（当前生效 SOTA Calmar ${bestSession.calmar}）\n因子：${(bestSession.factors || []).join(', ') || '—'}`">
          <span class="af-hint af-hint-fit">
            最佳：{{ bestSession.job_id }} · Calmar {{ bestSession.calmar }} · {{ (bestSession.factors || []).length }} 个因子
          </span>
        </el-tooltip>
        <span v-else class="af-hint">暂无带会话检查点的历史 SOTA</span>
      </div>

      <!-- 阶段进度 -->
      <div v-if="running || status.step" class="af-progress">
        <el-steps :active="stepIndex" align-center finish-status="success">
          <el-step title="提假设" description="direct_exp_gen" />
          <el-step title="写代码" description="coding" />
          <el-step title="回测验证" description="running" />
          <el-step title="复盘" description="feedback" />
          <el-step title="记录" description="record" />
        </el-steps>
        <div class="af-progress-row">
          <el-progress :percentage="status.progress_pct || 0" :stroke-width="10" />
          <span class="af-status-msg">{{ status.message || '' }}</span>
        </div>
        <div v-if="status.error" class="af-error">❌ {{ status.error }}</div>
      </div>
    </el-card>

    <!-- 结果 -->
    <el-card v-if="result && (result.status === 'done' || result.result)" class="af-card" shadow="never">
      <template #header>
        <div class="af-card-head">
          <span>挖掘结果</span>
          <span class="af-job-tag">{{ result.job_id }}</span>
        </div>
      </template>

      <!-- 回测指标 -->
      <div v-if="result.result && result.result.backtest" class="af-section">
        <h3>回测指标
          <span v-if="gate" class="af-gate" :class="gate.pass ? 'ok' : 'no'">
            {{ gate.pass ? '✅ 过线' : '⚠️ 未过线' }}
          </span>
        </h3>
        <div v-if="gate" class="af-gate-reason" :class="gate.pass ? 'ok' : 'no'">
          {{ gate.reason }}<span class="af-gate-tip">（提示性质，不拦截导出/回测）</span>
        </div>
        <div class="af-metrics">
          <div class="af-metric" v-for="m in metricCards" :key="m.label">
            <div class="af-metric-label">{{ m.label }}</div>
            <div class="af-metric-value">{{ m.value }}</div>
          </div>
        </div>
      </div>

      <!-- SOTA 对比 -->
      <div v-if="result.result && result.result.sota_comparison && hasSota" class="af-section">
        <h3>与 SOTA 对比</h3>
        <div class="af-metrics af-metrics-sota">
          <div class="af-metric" v-for="(v, k) in result.result.sota_comparison" :key="k">
            <div class="af-metric-label">{{ sotaLabel(k) }}</div>
            <div class="af-metric-value">当前 {{ fmt(v.current) }} / SOTA {{ fmt(v.sota) }}</div>
          </div>
        </div>
      </div>

      <!-- 因子列表 -->
      <div v-if="result.result && result.result.factors && result.result.factors.length" class="af-section">
        <h3>本轮挖出的因子（{{ result.result.factors.length }} 个）</h3>
        <el-collapse>
          <el-collapse-item v-for="f in result.result.factors" :key="f.factor_name" :name="f.factor_name">
            <template #title>
              <span class="af-factor-name">{{ f.factor_name_cn || f.factor_name }}</span>
              <span v-if="f.factor_name_cn" class="af-factor-en">{{ f.factor_name }}</span>
            </template>
            <pre class="af-code">{{ f.code }}</pre>
          </el-collapse-item>
        </el-collapse>
      </div>

      <!-- 最新生效因子组合 -->
      <div v-if="activeFactors.length" class="af-section">
        <h3>最新生效因子组合（SOTA · {{ activeFactors.length }} 个）</h3>
        <div class="af-active-factors">
          <el-tag v-for="f in activeFactors" :key="f" size="small" type="success" style="margin: 2px 6px 2px 0">{{ f }}</el-tag>
        </div>
      </div>

      <!-- 复盘结论 -->
      <div v-if="feedback" class="af-section">
        <h3>AI 复盘结论</h3>
        <div class="af-feedback">
          <div v-if="feedback.Observations" class="af-feedback-item"><b>观察</b><p>{{ feedback.Observations }}</p></div>
          <div v-if="feedback['Feedback for Hypothesis']" class="af-feedback-item"><b>假设反馈</b><p>{{ feedback['Feedback for Hypothesis'] }}</p></div>
          <div v-if="feedback['New Hypothesis']" class="af-feedback-item"><b>新假设</b><p>{{ feedback['New Hypothesis'] }}</p></div>
          <div v-if="feedback.Reasoning" class="af-feedback-item"><b>推理过程</b><p>{{ feedback.Reasoning }}</p></div>
          <div v-if="feedback['Replace Best Result']" class="af-feedback-item"><b>是否替换最优</b><p>{{ feedback['Replace Best Result'] === 'yes' ? '是' : feedback['Replace Best Result'] === 'no' ? '否' : feedback['Replace Best Result'] }}</p></div>
        </div>
      </div>
    </el-card>

    <!-- 历史：按会话分组（父=本轮挖掘，子=续跑），默认收起只显示父节点 -->
    <el-card class="af-card" shadow="never">
      <template #header>
        <div class="af-card-head af-hist-head" @click="histCollapsed = !histCollapsed">
          <span>
            历史记录
            <el-tag v-if="history.length" size="small" type="info" effect="plain" style="margin-left:6px">
              {{ history.length }} 条 / {{ historyTree.length }} 轮
            </el-tag>
          </span>
          <span class="af-hist-toggle" :title="histCollapsed ? '展开历史记录' : '收起历史记录'">
            <el-icon><ArrowUp v-if="!histCollapsed" /><ArrowDown v-else /></el-icon>
          </span>
        </div>
      </template>
      <el-table v-show="!histCollapsed" :data="historyTree" size="small" empty-text="暂无记录"
                row-key="job_id" :tree-props="{ children: 'children' }">
        <el-table-column prop="job_id" label="任务" width="215" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.job_id }}
            <el-tag v-if="row.__synthetic" size="small" type="warning" effect="plain" style="margin-left:4px">本轮根</el-tag>
            <el-tag v-if="row.__isParent && row.__childCount" size="small" type="info" style="margin-left:4px">
              续跑×{{ row.__childCount }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="圈数" width="50" align="center">
          <template #default="{ row }">{{ row.__latest?.total_loops ?? row.total_loops ?? row.loop_n }}</template>
        </el-table-column>
        <el-table-column label="状态" width="68" align="center">
          <template #default="{ row }">
            <el-tag :type="stType(row.__st)" size="small">{{ statusLabel(row.__st) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="当前最佳因子组合" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.__isParent && row.__best && row.__best.job_id !== row.job_id" class="af-hint">来自 {{ shortId(row.__best.job_id) }}：</span>
            {{ row.__bestFactors || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="IC" width="66" align="center">
          <template #default="{ row }">{{ row.__bestIC != null ? row.__bestIC.toFixed(4) : '—' }}</template>
        </el-table-column>
        <el-table-column label="ICIR" width="66" align="center">
          <template #default="{ row }">{{ row.__bestICIR != null ? row.__bestICIR.toFixed(4) : '—' }}</template>
        </el-table-column>
        <el-table-column label="门禁" width="74" align="center">
          <template #default="{ row }">
            <span v-if="row.__gate === true" class="af-gate-mini ok">✅ 过线</span>
            <span v-else-if="row.__gate === false" class="af-gate-mini no">⚠️ 未过</span>
            <span v-else class="af-gate-mini">—</span>
          </template>
        </el-table-column>
        <el-table-column label="开始" width="105" align="center">
          <template #default="{ row }">{{ (row.started || '').replace('T', ' ').slice(5, 16) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="56" align="center">
          <template #default="{ row }">
            <el-button size="small" text type="primary"
                       @click="loadResult(row.__isParent && row.__best ? row.__best.job_id : row.job_id)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 磁盘清理（历史缓存） -->
    <el-card class="af-card" shadow="never">
      <template #header>
        <div class="af-card-head">
          <span>磁盘清理（历史缓存）</span>
          <span v-if="disk" class="af-job-tag">
            RD-Agent 产物 {{ (disk.rdagent_mb / 1024).toFixed(2) }} GB · 可用 {{ (disk.free_mb / 1024).toFixed(1) }} GB
          </span>
        </div>
      </template>
      <div class="af-clean-row">
        <el-button size="small" :loading="cleaning" :disabled="isDemo || running || cleaning" @click="doCleanup(true)">预览可清理项</el-button>
        <el-button size="small" type="danger" plain :loading="cleaning" :disabled="isDemo || running || cleaning" @click="doCleanup(false)">清理历史缓存</el-button>
        <span class="af-hint">保留：当前生效因子目录 + 会话检查点 + 最新任务；删掉的进废纸篓可恢复；挖掘中不可清理</span>
      </div>
      <div v-if="cleanResult" class="af-clean-result">
        <p class="af-clean-sum">
          <b>{{ cleanResult.message }}</b>
          <span v-if="cleanResult.dry_run && cleanResult.estimate_mb">　预计可释放 {{ (cleanResult.estimate_mb / 1024).toFixed(2) }} GB</span>
          <span v-else-if="!cleanResult.dry_run">　RD-Agent 体积 {{ (cleanResult.before_mb / 1024).toFixed(2) }} GB → {{ (cleanResult.after_mb / 1024).toFixed(2) }} GB（减少 {{ (cleanResult.freed_mb / 1024).toFixed(2) }} GB；清空废纸篓后彻底释放）</span>
        </p>
        <pre class="af-clean-lines">{{ (cleanResult.lines || []).join('\n') }}</pre>
      </div>
    </el-card>
  </div>
</template>

<script setup>
// 演示站（isDemo）：RD-Agent 为只读模式（后端拦截写操作），页面禁用发起/清理按钮
import { isDemo } from '../api/demo'
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const loopN = ref(1)
const running = ref(false)
const status = ref({})
const result = ref(null)
const history = ref([])
const resumeMode = ref(false)
const resumeTarget = ref(null)
const hasResumeTarget = computed(() => !!resumeTarget.value)
// P0-4（2026-09-24）：当前生效 SOTA 最高、且可续跑的会话（供「续挖到最佳会话」按钮展示）
const bestSession = ref(null)
let timer = null
const cleaning = ref(false)
const cleanResult = ref(null)
const disk = ref(null)

const stepIndex = computed(() => {
  const s = status.value.step
  if (!s) return 0
  const map = { direct_exp_gen: 0, coding: 1, running: 2, feedback: 3, record: 4 }
  return map[s] ?? 0
})

const feedback = computed(() => result.value?.result?.feedback || null)

const activeFactors = computed(() => result.value?.result?.active_factors || [])

const hasSota = computed(() => {
  const c = result.value?.result?.sota_comparison
  return c && Object.keys(c).length > 0
})

const gate = computed(() => result.value?.result?.gate || null)

const metricCards = computed(() => {
  const bt = result.value?.result?.backtest
  if (!bt) return []
  const defs = [
    ['IC', bt.IC], ['ICIR', bt.ICIR], ['Rank IC', bt['Rank IC']], ['Rank ICIR', bt['Rank ICIR']],
    ['年化收益(含成本)', bt.annualized_return_with_cost],
    ['最大回撤(含成本)', bt.max_drawdown_with_cost],
    ['信息比率 IR(含成本)', bt.information_ratio_with_cost],
    ['Calmar(含成本)', bt.calmar_with_cost],
  ]
  return defs
    .filter(([, v]) => v != null)
    .map(([label, v]) => ({ label, value: fmt(v) }))
})

function fmt(v) {
  if (v == null) return '—'
  if (typeof v === 'number') {
    if (Math.abs(v) < 1) return v.toFixed(4)
    return v.toFixed(3)
  }
  return v
}

const SOTA_LABELS = {
  IC: 'IC',
  annualized_return_with_cost: '年化收益（含成本）',
  max_drawdown_with_cost: '最大回撤（含成本）',
  calmar_with_cost: 'Calmar（含成本）',
}
function sotaLabel(k) {
  return SOTA_LABELS[k] || k
}

const STATUS_LABELS = { done: '完成', failed: '失败', running: '运行中' }
function statusLabel(s) {
  return STATUS_LABELS[s] || s
}

function stType(s) {
  return s === 'done' ? 'success' : s === 'failed' ? 'danger' : 'warning'
}

function shortId(id) {
  return (id || '').slice(-6)
}

const histCollapsed = ref(false)

function enrichNode(j) {
  return {
    ...j,
    __bestFactors: (j.factor_names_cn || j.factor_names || []).join('、'),
    __bestIC: j.IC,
    __bestICIR: j.ICIR,
    __gate: j.gate_pass,
    __st: j.status,
  }
}

// 历史按「同一轮挖掘」分组：一轮 = 同一会话；父 = 会话根任务，子 = 该会话的历次续跑（默认收起只看父）
const historyTree = computed(() => {
  const items = history.value || []
  const byId = new Map(items.map(j => [j.job_id, j]))
  // 沿 resume_from 回溯到本轮根任务；根任务不在记录里时用该 id 作合成根节点
  const rootOf = (id) => {
    const seen = new Set()
    let cur = id
    while (cur && byId.has(cur) && !seen.has(cur)) {
      seen.add(cur)
      const n = byId.get(cur)
      if (!n.resume_from) return cur
      cur = n.resume_from
    }
    return cur || id
  }
  const groups = new Map()
  for (const j of items) {
    const key = rootOf(j.resume_from || j.job_id)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(j)
  }
  const desc = (a, b) => (b.started || '').localeCompare(a.started || '')
  const nodes = []
  for (const [key, members] of groups) {
    const root = byId.get(key)
    const sorted = members.slice().sort(desc)          // 新 → 旧
    const latest = sorted[0]                           // 该轮最新一次（决定状态/圈数）
    const kids = sorted.filter(m => m !== root)        // 续跑子节点
    const best = kids.concat(root ? [root] : []).find(n => n.IC != null) || latest // 当前最佳（最新有结果者）
    const base = root ? enrichNode(root) : { job_id: key, __synthetic: true, started: latest.started }
    nodes.push({
      ...base,
      __isParent: true,
      __childCount: kids.length,
      __latest: latest,
      __st: latest.status,
      __gate: latest.gate_pass,
      __best: best,
      __bestFactors: (best.factor_names_cn || best.factor_names || []).join('、') || '—',
      __bestIC: best.IC,
      __bestICIR: best.ICIR,
      __sortKey: latest.started || base.started || '',
      children: kids.map(k => ({ ...enrichNode(k), __isParent: false, __best: k })),
    })
  }
  nodes.sort((a, b) => (b.__sortKey || '').localeCompare(a.__sortKey || ''))
  return nodes
})

async function doStart() {
  running.value = true
  status.value = {}
  result.value = null
  try {
    const res = await api.post('/rdagent/start', { loop_n: loopN.value, resume: resumeMode.value })
    if (!res.data?.ok) {
      running.value = false
      return
    }
    startPolling()
  } catch (e) {
    running.value = false
  }
}

function startPolling() {
  stopPolling()
  timer = setInterval(async () => {
    try {
      const res = await api.get('/rdagent/status')
      status.value = res.data || {}
      if (res.data?.running === false) {
        stopPolling()
        running.value = false
        await loadResult()
        loadHistory()
      }
    } catch (e) {
      /* ignore */
    }
  }, 2500)
}

function stopPolling() {
  if (timer) { clearInterval(timer); timer = null }
}

async function loadResult(jobId) {
  try {
    const res = await api.get('/rdagent/result', { params: jobId ? { job_id: jobId } : {} })
    result.value = res.data || null
    // 若指定历史任务已结束，同步状态
    if (res.data && jobId && res.data.status !== 'running') {
      status.value = status.value || {}
    }
  } catch (e) {
    /* ignore */
  }
}

async function loadDisk() {
  try {
    const res = await api.get('/rdagent/disk')
    disk.value = res.data || null
  } catch (e) {
    /* ignore */
  }
}

async function doCleanup(dryRun) {
  if (!dryRun) {
    try {
      await ElMessageBox.confirm(
        '将把历史因子/回测产物、pickle_cache、旧 job 日志移到废纸篓（保留当前生效因子目录、会话检查点、最新任务）。删除项可从废纸篓恢复，继续？',
        '清理历史缓存',
        { type: 'warning', confirmButtonText: '清理', cancelButtonText: '取消' }
      )
    } catch (e) {
      return
    }
  }
  cleaning.value = true
  cleanResult.value = null
  try {
    const res = await api.post('/rdagent/cleanup', { dry_run: !!dryRun })
    cleanResult.value = res.data || null
    if (!res.data?.ok) {
      ElMessage.error(res.data?.message || '清理失败')
    } else if (!dryRun) {
      ElMessage.success('清理完成')
      await loadDisk()
      loadHistory()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '清理失败')
  } finally {
    cleaning.value = false
  }
}

// P0-4（2026-09-24）：拉取「当前生效 SOTA 最高、且会话检查点仍在」的会话
async function loadBestSession() {
  try {
    const res = await api.get('/rdagent/best-session')
    bestSession.value = res.data?.ok ? res.data : null
  } catch (e) {
    bestSession.value = null
  }
}

async function doResumeBest() {
  if (!bestSession.value) return
  running.value = true
  status.value = {}
  result.value = null
  try {
    const res = await api.post('/rdagent/start', { loop_n: loopN.value, resume_best: true })
    if (!res.data?.ok) {
      ElMessage.warning(res.data?.message || '启动失败')
      running.value = false
      return
    }
    startPolling()
  } catch (e) {
    running.value = false
  }
}

async function loadHistory() {
  try {
    const res = await api.get('/rdagent/history')
    history.value = res.data?.jobs || []
    resumeTarget.value = history.value.find(j => j.status === 'done') || null
    if (!resumeTarget.value) resumeMode.value = false
    loadBestSession()
  } catch (e) {
    /* ignore */
  }
}

onMounted(async () => {
  loadHistory()
  loadDisk()
  // 恢复进行中的任务轮询
  try {
    const res = await api.get('/rdagent/status')
    status.value = res.data || {}
    if (res.data?.running) {
      running.value = true
      startPolling()
    } else if (res.data?.job_id) {
      await loadResult()
    }
  } catch (e) {
    /* ignore */
  }
})

onUnmounted(stopPolling)
</script>

<style scoped>
.af-demo-alert {
  margin-bottom: 12px;
}
.af-gate { margin-left:10px; padding:2px 10px; border-radius: 8px; font-size:12px; font-weight:600; vertical-align:middle; }
.af-gate.ok { background:rgba(34,197,94,0.16); color:#4ADE80; }
.af-gate.no { background:rgba(245,158,11,0.14); color:#F59E0B; }
.af-gate-reason { margin:6px 0 10px; font-size:12px; line-height:1.7; }
.af-gate-reason.ok { color:#4ADE80; }
.af-gate-reason.no { color:#F59E0B; }
.af-gate-tip { color:#7A8494; margin-left:6px; }
.af-gate-mini { font-size:11px; }
.af-gate-mini.ok { color:#4ADE80; }
.af-gate-mini.no { color:#F59E0B; }
.af-shell { max-width: 980px; margin: 0 auto; }
.af-header h1 { font-size: 24px; font-weight: 700; margin: 0 0 6px; }
.af-sub { color: var(--text-muted, #7A8494); font-size: 13px; margin: 0 0 20px; }
.af-card { margin-bottom: 16px; background: var(--card-bg, #fff); }
.af-card-head { display: flex; justify-content: space-between; align-items: center; }
.af-hist-head { cursor: pointer; user-select: none; }
.af-hist-toggle { display: flex; align-items: center; color: var(--text-muted, #7A8494); font-size: 16px; }
.af-hist-toggle:hover { color: var(--el-color-primary, #60A5FA); }
.af-job-tag { font-size: 12px; color: var(--text-muted, #7A8494); }
.af-config { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.af-config-item { display: flex; align-items: center; gap: 10px; min-width: 0; }
.af-config > .el-button { flex: 0 0 auto; }
.af-label { font-size: 14px; font-weight: 500; }
.af-hint { font-size: 12px; color: var(--text-muted, #7A8494); }
/* 续跑提示：单行不换行，过长省略号（完整内容见 tooltip），避免把「续跑挖掘」按钮挤到第二行 */
.af-hint-fit { display: inline-block; max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; }
.af-progress { margin-top: 20px; }
.af-progress-row { display: flex; align-items: center; gap: 16px; margin-top: 14px; }
.af-progress-row .el-progress { flex: 1; }
.af-status-msg { font-size: 13px; color: var(--text-muted, #7A8494); white-space: nowrap; }
.af-error { margin-top: 12px; color: #F87171; font-size: 13px; }
.af-section { margin-bottom: 20px; }
.af-section h3 { font-size: 15px; font-weight: 600; margin: 0 0 12px; }
.af-metrics { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.af-metrics-sota { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
.af-metrics-sota .af-metric-value { font-size: 14px; white-space: nowrap; }
.af-metric { background: var(--content-bg, #161C24); border-radius: 8px; padding: 12px 14px; }
.af-metric-label { font-size: 12px; color: var(--text-muted, #7A8494); margin-bottom: 4px; }
.af-metric-value { font-size: 16px; font-weight: 600; }
.af-factor-name { font-family: monospace; font-weight: 600; }
.af-factor-en { font-family: monospace; font-size: 12px; color: var(--text-muted, #7A8494); margin-left: 8px; }
.af-code { background: #0B0E13; color: var(--text-primary); padding: 14px; border-radius: 8px; overflow-x: auto; font-size: 12px; line-height: 1.5; max-height: 360px; }
.af-feedback { display: flex; flex-direction: column; gap: 10px; }
.af-feedback-item { background: var(--content-bg, #161C24); border-radius: 8px; padding: 12px 14px; }
.af-feedback-item b { display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.af-feedback-item p { margin: 0; font-size: 13px; line-height: 1.7; color: var(--text-color, #C9D1DB); white-space: pre-wrap; }
.af-clean-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.af-clean-result { margin-top: 12px; }
.af-clean-sum { font-size: 13px; margin: 0 0 8px; }
.af-clean-lines { background: var(--content-bg, #161C24); border-radius: 8px; padding: 12px; font-size: 12px; line-height: 1.6; max-height: 220px; overflow: auto; margin: 0; white-space: pre-wrap; }
</style>
