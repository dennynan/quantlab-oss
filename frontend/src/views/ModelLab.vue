<template>
  <div class="ml-shell">
    <!-- ====== 实验配置 ====== -->
    <section class="ml-card">
      <div class="ml-card-head">
        <h2>⚙️ 实验配置</h2>
        <div style="display:flex;align-items:center;gap:8px">
          <!-- 模式切换 -->
          <div class="mode-toggle">
            <button :class="{on: trainMode==='manual'}" @click="trainMode='manual'">手动模式</button>
            <button :class="{on: trainMode==='smart'}" @click="trainMode='smart'">🧠 智能选因子</button>
          </div>
          <span v-if="running" class="badge badge-train">训练中...</span>
          <span v-else-if="fsRunning" class="badge badge-train">选因子中...</span>
          <span v-else-if="trainHistory.length" class="badge badge-ok">{{ trainHistory.length }} 次实验</span>
          <span v-else class="badge badge-idle">未训练</span>
        </div>
      </div>

      <div class="config-grid">
        <!-- 目标收益窗口 -->
        <div class="cfg-item">
          <label>🎯 预测目标</label>
          <div class="cfg-chips">
            <button v-for="d in [3,5,10,20]" :key="d" class="chip" :class="{on: cfg.targetHorizon===d}" @click="cfg.targetHorizon=d">{{ d }}日收益</button>
          </div>
        </div>

        <!-- 训练窗口 -->
        <div class="cfg-item">
          <label>📅 训练窗口</label>
          <div class="cfg-chips">
            <button v-for="d in [365,730,1095]" :key="d" class="chip" :class="{on: cfg.trainDays===d}" @click="cfg.trainDays=d">{{ d===365?'1年':d===730?'2年':'3年' }}</button>
          </div>
        </div>

        <!-- 验证比例 -->
        <div class="cfg-item">
          <label>✂️ 验证集比例</label>
          <div class="cfg-chips">
            <button v-for="p in [10,15,20,25]" :key="p" class="chip" :class="{on: cfg.validPct===p}" @click="cfg.validPct=p">{{ p }}%</button>
          </div>
        </div>

        <!-- 模型参数 -->
        <div class="cfg-item">
          <label>🧠 模型参数</label>
          <div class="cfg-row">
            <div class="cfg-kv">
              <span>学习率</span>
              <select v-model.number="cfg.lr" class="kv-select">
                <option :value="0.01">0.01</option>
                <option :value="0.03">0.03</option>
                <option :value="0.05">0.05</option>
                <option :value="0.1">0.10</option>
              </select>
            </div>
            <div class="cfg-kv">
              <span>叶子数</span>
              <select v-model.number="cfg.leaves" class="kv-select">
                <option :value="31">31</option>
                <option :value="63">63</option>
                <option :value="127">127</option>
              </select>
            </div>
            <div class="cfg-kv">
              <span>树数</span>
              <select v-model.number="cfg.estimators" class="kv-select">
                <option :value="100">100</option>
                <option :value="200">200</option>
                <option :value="300">300</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- 特征选择（按分类展示，可折叠+搜索） -->
      <div class="feature-select">
        <div class="f-header-row">
          <label style="cursor:pointer" @click="factorOpen = !factorOpen">
            <span class="collapse-arrow sm" :class="{open: factorOpen}">▼</span>
            📊 特征因子 <span class="f-count">已选 {{ selectedFeatures.length }}/{{ allFeatureKeys.length }}</span>
          </label>
          <input v-model="factorSearch" class="f-search" placeholder="🔍 搜索（中/英文）..." />
        </div>
        <div v-if="factorOpen">
          <div v-for="cat in filteredCategories" :key="cat.name" class="f-cat-group">
            <div class="f-cat-label" style="cursor:default">
              {{ cat.name }} <span class="f-cat-n">({{ cat.factors.length }})</span>
              <span class="f-cat-sel" v-if="categorySelectedCount(cat) > 0">已选{{ categorySelectedCount(cat) }}</span>
            </div>
            <div class="f-chips">
              <button v-for="f in cat.factors" :key="f.key" class="chip f-chip" :class="{on: cfg.features.has(f.key)}" @click="toggleFeature(f.key)">
                {{ f.label }}
              </button>
            </div>
          </div>
          <div class="f-actions">
            <button class="f-action-link" @click="selectAllFactors()">全选</button>
            <button class="f-action-link" @click="cfg.features.clear()">清空</button>
            <button class="f-action-link" @click="selectTopIR(5)">IR Top5</button>
          </div>
        </div>
      </div>

      <!-- 智能选因子配置 -->
      <div v-if="trainMode==='smart'" class="smart-cfg">
        <div class="smart-cfg-row">
          <div class="smart-cfg-item">
            <span>阶段</span>
            <label v-for="s in ['screen_only','full']" :key="s" class="smart-radio">
              <input type="radio" v-model="fsCfg.mode" :value="s" />
              {{ s==='screen_only'?'仅IC预筛':'全流程(预筛+窗口+前向)' }}
            </label>
          </div>
          <div class="smart-cfg-item">
            <span>目标周期</span>
            <select v-model.number="fsCfg.targetHorizon" class="kv-select">
              <option :value="5">5日</option>
              <option :value="10">10日</option>
              <option :value="20">20日</option>
            </select>
          </div>
          <div class="smart-cfg-item">
            <span>滚动窗口数</span>
            <select v-model.number="fsCfg.nWindows" class="kv-select">
              <option :value="2">2</option>
              <option :value="3">3</option>
            </select>
          </div>
          <div class="smart-cfg-item">
            <span>目标因子数</span>
            <select v-model.number="fsCfg.topN" class="kv-select">
              <option :value="5">5</option>
              <option :value="10">10</option>
              <option :value="15">15</option>
            </select>
          </div>
        </div>
      </div>

      <div style="display:flex;align-items:center;gap:12px;margin-top:14px">
        <button class="train-btn" :disabled="trainDisabled" @click="trainMode==='smart' ? doSmartSelect() : doTrain()" style="flex-shrink:0">
          <span v-if="running || fsRunning" class="spinner-sm"></span>
          <span v-else>{{ trainMode==='smart' ? '🧠 开始智能选因子' : '🚀 开始实验' }}</span>
        </button>
        <div v-if="running" style="flex:1;min-width:200px">
          <el-progress :percentage="trainingProgress" :stroke-width="8" :show-text="true" />
          <span class="train-note">{{ statusMsg }}</span>
        </div>
        <div v-if="fsRunning" style="flex:1;min-width:200px">
          <el-progress :percentage="fsProgress" :stroke-width="8" :show-text="true" :color="'#A78BFA'" />
          <span class="train-note">{{ fsStatusMsg }}</span>
        </div>
        <span class="train-note" v-else-if="statusMsg">{{ statusMsg }}</span>
      </div>
    </section>

    <!-- 智能选因子结果 -->
    <section class="ml-card" v-if="trainMode==='smart' && fsResult?.status==='done'">
      <div class="ml-card-head"><h2>🧬 因子筛选报告</h2><span class="meta-date">{{ fsResult.job_id }}</span></div>
      <!-- 阶段1: IC预筛 -->
      <div v-if="fsResult.stages?.screen" style="margin-bottom:16px">
        <h3 style="font-size:14px;margin:0 0 8px">📋 IC预筛 — {{ fsResult.stages.screen.n_total }} → {{ fsResult.stages.screen.n_passed }} 因子</h3>
        <div v-if="fsResult.stages.screen.n_dropped" style="margin-bottom:8px">
          <span style="font-size:12px;color:#7A8494;cursor:pointer" @click="showDropped=!showDropped">
            {{ showDropped?'收起':'展开' }}淘汰明细 ({{ fsResult.stages.screen.n_dropped }}个) ▼
          </span>
          <div v-if="showDropped" style="max-height:200px;overflow-y:auto;font-size:12px;margin-top:4px">
            <span v-for="d in fsResult.stages.screen.dropped" :key="d.factor" class="drop-tag">{{ d.factor }}:{{ d.reason }}</span>
          </div>
        </div>
        <div class="f-chips">
          <button v-for="f in fsResult.stages.screen.passed" :key="f.factor" class="chip f-chip" :class="{on: selectedFsFactors.includes(f.factor)}" @click="toggleFsFactor(f.factor)">{{ f.label }}</button>
        </div>
      </div>
      <!-- 阶段2: 多窗口稳定性 -->
      <div v-if="fsResult.stages?.stability" style="margin-bottom:16px">
        <h3 style="font-size:14px;margin:0 0 8px">📊 多窗口稳定性 — Top 15</h3>
        <div style="display:flex;flex-wrap:wrap;gap:6px">
          <span v-for="k in (fsResult.stages.stability.top15||[])" :key="k" class="stab-chip" :class="{top: selectedFsFactors.includes(k)}" @click="toggleFsFactor(k)" :title="'入选率:'+(fsResult.stages.stability.stability[k]?.hit_rate||0)+' | 得分:'+(fsResult.stages.stability.stability[k]?.score||0)">
            {{ k }} <small>{{ fsResult.stages.stability.stability[k]?.score }}</small>
          </span>
        </div>
      </div>
      <!-- 阶段3: 多样性前向选择 -->
      <div v-if="fsResult.stages?.forward?.path">
        <h3 style="font-size:14px;margin:0 0 8px">🎯 多样性前向选择 (种子={{ fsResult.stages.forward.seed?.join(',') }})</h3>
        <table class="ic-table" style="font-size:12px">
          <thead><tr><th>阶段</th><th>因子组合</th><th>val_IC</th><th>增益/测试</th></tr></thead>
          <tbody>
            <tr v-for="p in fsResult.stages.forward.path" :key="p.step">
              <td>{{ p.step }}</td>
              <td style="font-weight:600;color:#60A5FA">{{ p.factors ? p.factors.join('+') : (p.added || '—') }}</td>
              <td :class="(p.val_IC||0)>0?'up':'down'">{{ p.val_IC }}</td>
              <td>{{ p.gain!=null ? ((p.gain>0?'+':'')+p.gain) : (p.n_tested!=null ? '测试'+p.n_tested+'组' : (p.tested!=null ? '测试'+p.tested+'个' : '—')) }}</td>
            </tr>
          </tbody>
        </table>
        <div style="margin-top:12px;padding:12px;background:rgba(34,197,94,0.12);border-radius:8px;font-size:14px">
          ✅ <b>最终推荐 {{ fsResult.stages.forward.n_final }} 因子 (测试{{ fsResult.stages.forward.n_combos_tested || 0 }}组合):</b>
          <span v-for="f in fsResult.stages.forward.final_factors" :key="f" class="chip on" style="margin:2px">{{ f }}</span>
          <br><span style="font-size:12px;color:#98A2B3">val_IC={{ fsResult.stages.forward.final_val_IC }} | 种子IC={{ fsResult.stages.forward.baseline_val_IC }}</span>
        </div>
        <button class="train-btn" style="margin-top:8px;font-size:13px;padding:8px 20px" @click="applySelectedFsFactors" :disabled="!fsResult.stages.forward.final_factors?.length">
          📋 应用这 {{ fsResult.stages.forward.n_final }} 个因子到实验
        </button>
      </div>
    </section>

    <!-- ====== 手动模式: 实验结果 + Tab (因子IC / AI预测) ====== -->
    <section class="ml-card" v-if="trainMode==='manual' && currentMeta">
      <div class="ml-card-head">
        <h2>📈 实验结果 — {{ currentMeta.job_id }}</h2>
        <span class="meta-date">{{ formatDate(currentMeta.trained_at) }}</span>
      </div>
      <div class="result-meta">
        <div class="rm-item"><span>验证IC</span><strong :class="currentMeta.val_IC>0.02?'good':currentMeta.val_IC>0?'warn':'bad'">{{ currentMeta.val_IC?.toFixed(4) }}</strong></div>
        <div class="rm-item"><span>MSE{{ currentMeta.target_mode==='rank_z_daily' ? '(rank-z量纲)' : '' }}</span><strong>{{ currentMeta.val_MSE?.toFixed(4) }}</strong></div>
        <div class="rm-item"><span>训练样本</span><strong>{{ currentMeta.train_samples?.toLocaleString() }}</strong></div>
        <div class="rm-item"><span>验证样本</span><strong>{{ currentMeta.valid_samples?.toLocaleString() }}</strong></div>
        <div class="rm-item"><span>股票数</span><strong>{{ currentMeta.n_stocks }}</strong></div>
        <div class="rm-item"><span>最佳轮次</span><strong>{{ currentMeta.best_iteration }}</strong></div>
      </div>
      <div class="rm-importance" v-if="currentMeta.importance_top5?.length">
        <span class="rm-imp-label">TOP5 重要因子:</span>
        <span v-for="(imp,i) in currentMeta.importance_top5" :key="i" class="rm-imp-chip">{{ factorMeta[imp[0]]?.label || imp[0] }} <em>{{ imp[1] }}%</em></span>
      </div>
      <div style="margin-top:12px" v-if="currentMeta.features?.length">
        <el-button size="small" type="warning" @click="exportToTopk">📤 导出因子权重到轮动引擎</el-button>
      </div>
      <!-- Tab切换 -->
      <div style="margin-top:16px">
        <div class="tab-nav">
          <button :class="{on: resultTab==='ic'}" @click="resultTab='ic'">📊 因子有效性评估 (IC/IR)</button>
          <button :class="{on: resultTab==='pred'}" @click="resultTab='pred'">🎯 AI 预测 Top30</button>
        </div>
        <div v-show="resultTab==='ic'" class="ic-hint">
          多空价差 = 因子当日前20%与后20%的目标收益差（看<b>经济意义</b>，高 IR 不等于能赚钱）
          　｜　分段 = 按时间三等分的 IC 是否同号
          　｜　有效天数 &lt; 30 视为样本不足
        </div>
        <div v-show="resultTab==='ic'" class="ic-table-wrap">
          <table class="ic-table" v-if="icResults.length">
            <thead><tr><th>因子</th><th class="th-num">IC Mean</th><th class="th-num">IC Std</th><th class="th-num">|IR|</th><th class="th-num">IC>0%</th><th class="th-num">有效天数</th><th class="th-num">多空价差</th><th class="th-num">分段</th><th>评级</th></tr></thead>
            <tbody>
              <tr v-for="f in icResults" :key="f.factor" @click="toggleFeatureSelect(f.factor)" class="ic-row" :class="{sel: cfg.features.has(f.factor)}">
                <td class="td-factor"><span class="ic-check">{{ cfg.features.has(f.factor)?'☑':'☐' }}</span>{{ f.label || factorMeta[f.factor]?.label || f.factor }}</td>
                <td class="td-num" :class="f.IC_mean>0?'up':'down'">{{ f.IC_mean.toFixed(4) }}</td>
                <td class="td-num">{{ f.IC_std.toFixed(4) }}</td>
                <td class="td-num strong">{{ Math.abs(f.IR).toFixed(3) }}</td>
                <td class="td-num">{{ (f.IC_pos_ratio*100).toFixed(0) }}%</td>
                <td class="td-num" :class="{dim: f.days < 30}">{{ f.days }}</td>
                <td class="td-num" :class="f.ls_spread!=null ? (f.ls_spread>0?'up':'down') : 'dim'">
                  {{ f.ls_spread!=null ? (f.ls_spread>0?'+':'')+(f.ls_spread*100).toFixed(2)+'%' : '—' }}
                </td>
                <td class="td-num" :class="{dim: f.seg_same_sign==null}">
                  {{ f.seg_same_sign==null ? '—' : (f.seg_same_sign?'✅ 同号':'⚠️ 异号') }}
                </td>
                <td><span class="ic-badge" :class="irGrade(f.IR)">{{ irGradeText(f.IR) }}</span></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-hint">尚未评估，请先训练模型</div>
        </div>
        <div v-show="resultTab==='pred'" class="pred-table-wrap">
          <table class="pred-table" v-if="predictions.length">
            <thead><tr><th>#</th><th>代码</th><th>名称</th><th class="th-num">现价</th><th class="th-num">预测{{ cfg.targetHorizon }}日收益</th><th class="th-num">20日收益</th><th class="th-num">MA20偏离</th></tr></thead>
            <tbody>
              <tr v-for="(p,i) in predictions" :key="p.code" @click="goAnalysis(p.code)" class="pred-row">
                <td class="td-rank">{{ i+1 }}</td><td class="td-code">{{ p.code }}</td><td class="td-name">{{ p.name }}</td>
                <td class="td-num">{{ p.close }}</td>
                <td class="td-num strong" :class="p.pred_return_5d>0?'up':'down'">{{ p.pred_return_5d>0?'+':'' }}{{ p.pred_return_5d.toFixed(2) }}%</td>
                <td class="td-num"><span :class="(p.rtn20??0)>0?'up':'down'">{{ p.rtn20!=null?(p.rtn20>0?'+':'')+(p.rtn20*100).toFixed(1)+'%':'—' }}</span></td>
                <td class="td-num" :class="(p.ma20_dev??0)>0?'up':'down'">{{ p.ma20_dev!=null?(p.ma20_dev>0?'+':'')+(p.ma20_dev*100).toFixed(1)+'%':'—' }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-hint">尚未预测，请先训练模型</div>
        </div>
      </div>
    </section>

    <!-- ====== 手动模式: 实验记录 ====== -->
    <section class="ml-card" v-if="trainMode==='manual' && trainHistory.length > 1">
      <div class="ml-card-head"><h2>📜 实验记录 (训练)</h2></div>
      <table class="hist-table">
        <thead>
          <tr><th>时间</th><th>特征数</th><th>验证IC</th><th>MSE<sup style="color:#7A8494">*</sup></th><th>目标</th><th>学习率</th></tr>
        </thead>
        <tbody>
          <tr v-for="h in trainHistory" :key="h.job_id" @click="loadHistoryMeta(h)" class="hist-row">
            <td>{{ h.job_id }}</td>
            <td class="td-num">{{ h.n_features }}</td>
            <td class="td-num strong" :class="h.val_IC>0?'up':'down'">{{ h.val_IC?.toFixed(4) }}</td>
            <td class="td-num">{{ h.val_MSE?.toFixed(4) }}</td>
            <td class="td-num">{{ h.target_horizon }}d</td>
            <td class="td-num">{{ h.learning_rate }}</td>
          </tr>
        </tbody>
      </table>
      <div style="font-size:12px;color:#7A8494;margin-top:6px;line-height:1.6">
        <sup>*</sup> MSE 口径：<b>2026-09-18 起</b>训练目标改为「每日截面 rank-z 标准化」，MSE 约 1.0 属正常量纲（此前为原始收益率口径，约 0.007），两者不可直接跨期比较；验证IC 始终为原始收益率口径，可比。
      </div>
    </section>

    <!-- ====== 智能模式: 实验记录 ====== -->
    <section class="ml-card" v-if="trainMode==='smart' && fsHistory.length">
      <div class="ml-card-head"><h2>📜 实验记录 (因子筛选)</h2></div>
      <table class="hist-table">
        <thead>
          <tr><th>时间</th><th>结果</th><th>因子数</th><th>val_IC</th><th>最终因子</th></tr>
        </thead>
        <tbody>
          <tr v-for="h in fsHistory" :key="h.job_id" @click="loadFsHistory(h)" class="hist-row">
            <td>{{ h.job_id }}</td>
            <td><span :class="h.status==='done'?'up':'down'">{{ h.status==='done'?'✅完成':h.status }}</span></td>
            <td class="td-num">{{ h.n_final }}</td>
            <td class="td-num strong">{{ h.val_IC?.toFixed(4) }}</td>
            <td>{{ (h.final_factors||[]).join(', ') }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()

const allFeatureKeys = ref([])  // 从 API 动态加载

// 因子中文名+分类（从API动态加载）
const factorMeta = ref({})
// 按分类分组的因子列表
const factorCategories = computed(() => {
  const cats = {}
  for (const [key, meta] of Object.entries(factorMeta.value)) {
    const cat = meta.cat || '其他'
    cats[cat] = cats[cat] || []
    cats[cat].push({ key, label: meta.label })
  }
  return Object.entries(cats).map(([name, factors]) => ({ name, factors }))
})

// 搜索 & 整体折叠
const factorSearch = ref('')
const factorOpen = ref(false) // 默认收起

const filteredCategories = computed(() => {
  const q = factorSearch.value.trim().toLowerCase()
  if (!q) return factorCategories.value
  return factorCategories.value.map(cat => ({
    name: cat.name,
    factors: cat.factors.filter(f =>
      f.label.toLowerCase().includes(q) || f.key.toLowerCase().includes(q)
    ),
  })).filter(cat => cat.factors.length > 0)
})

function categorySelectedCount(cat) {
  return cat.factors.filter(f => cfg.features.has(f.key)).length
}

async function loadFactorMeta() {
  try {
    const r = await api.get('/ml/factor_meta')
    factorMeta.value = r.data.factors || {}
    allFeatureKeys.value = Object.keys(r.data.factors || {})
    // 默认全选
    selectAllFactors()
  } catch (e) { /* ignore */ }
}

function selectAllFactors() {
  allFeatureKeys.value.forEach(k => cfg.features.add(k))
}

const cfg = reactive({
  targetHorizon: 5,
  trainDays: 730,
  validPct: 20,
  lr: 0.05,
  leaves: 63,
  estimators: 200,
  features: new Set(),  // 由 loadFactorMeta 填充
})

const icOpen = ref(false)   // IC表格默认收起 (legacy, now uses resultTab)
const predOpen = ref(false) // 预测表格默认收起 (legacy, now uses resultTab)
const resultTab = ref('ic') // 手动模式 Tab: 'ic' | 'pred'
const selectedFeatures = computed(() => [...cfg.features])

// 模式切换
const trainMode = ref('manual')  // 'manual' | 'smart'

const running = ref(false)
const statusMsg = ref('')
const trainingProgress = ref(0)

// 智能选因子状态
const fsRunning = ref(false)
const fsProgress = ref(0)
const fsStatusMsg = ref('')
const fsResult = ref(null)
const showDropped = ref(false)
const selectedFsFactors = ref([])
const fsPollTimer = ref(null)

const fsCfg = reactive({
  mode: 'full',
  targetHorizon: 10,
  nWindows: 3,
  topN: 10,
})

const trainDisabled = computed(() => {
  if (running.value || fsRunning.value) return true
  if (trainMode.value === 'smart') return false  // smart mode uses its own data
  return !selectedFeatures.value.length
})
const currentMeta = ref(null)
const icResults = ref([])
const icUpdated = ref('')
const predictions = ref([])
const predDate = ref('')
const trainHistory = ref([])
const fsHistory = ref([])     // 智能模式实验历史

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso.slice(0, 16).replace('T', ' ')
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function toggleFeature(k) {
  if (cfg.features.has(k)) cfg.features.delete(k); else cfg.features.add(k)
}
function toggleFeatureSelect(k) {
  if (cfg.features.has(k)) cfg.features.delete(k); else cfg.features.add(k)
}
function selectTopIR(n) {
  cfg.features.clear()
  icResults.value.slice(0, n).forEach(r => cfg.features.add(r.factor))
}

// ── 工具 ──
function rsiClass(v) { if(v==null)return''; if(v>=70)return'overbought'; if(v<=30)return'oversold'; return'' }
function irGrade(ir) { const a=Math.abs(ir); return a>=0.5?'excellent':a>=0.3?'good':a>=0.1?'moderate':'weak' }
function irGradeText(ir) { const a=Math.abs(ir); return a>=0.5?'⭐优异':a>=0.3?'✅有效':a>=0.1?'🔶一般':'❌弱' }
function goAnalysis(code) { router.push({path:'/analysis',query:{code}}) }

function exportToTopk() {
  if (!currentMeta.value?.features?.length) return
  const features = currentMeta.value.features
  
  // 从 importance_top5 提取权重映射
  const importanceMap = {}
  let maxImp = 1
  if (currentMeta.value.importance_top5) {
    currentMeta.value.importance_top5.forEach(([name, val]) => {
      importanceMap[name] = Math.max(0, val)
      maxImp = Math.max(maxImp, val)
    })
  }
  
  // IC方向映射: 负IC的因子权重应取反（因子值高→收益低）
  const icSign = {}
  icResults.value.forEach(r => {
    icSign[r.factor] = r.IC_mean
  })
  
  // 构建因子列表和权重
  const factors = []
  const weights = []
  features.forEach(f => {
    factors.push(f)  // Alpha158 因子名直接使用
    const imp = importanceMap[f]
    let w = 0
    if (imp !== undefined && imp > 0) {
      w = imp / 100  // 转换百分比为比例
    } else {
      w = 0.01  // 未出现在 importance_top5 中的因子，给最低权重
    }
    // IC Mean 为负 → 取反权重
    if (icSign[f] !== undefined && icSign[f] < 0) {
      w = -w
    }
    weights.push(w)
  })
  
  // 归一化: 按绝对值之和归一，保留符号（负IC因子保持负权重）
  const absTotal = weights.reduce((s, w) => s + Math.abs(w), 0)
  const normalized = absTotal > 0 ? weights.map(w => w / absTotal) : weights.map(() => 1 / weights.length)
  
  localStorage.setItem('topk_preset', JSON.stringify({
    factors: factors.slice(0, 10),
    weights: normalized.slice(0, 10),
    top_k: 10,
    n_drop: 3,
    rebalance_freq: 'month',
    source: 'model_lab',
  }))
  router.push('/backtest?from=model')
}

async function doTrain() {
  running.value = true; statusMsg.value = '启动...'; trainingProgress.value = 0
  const payload = {
    days: cfg.trainDays,
    target_horizon: cfg.targetHorizon,
    valid_pct: cfg.validPct,
    lr: cfg.lr,
    leaves: cfg.leaves,
    estimators: cfg.estimators,
    features: selectedFeatures.value,
  }
  try {
    const res = await api.post('/ml/train', payload)
    statusMsg.value = `job: ${res.data.job_id} — 训练中（约2-5分钟）`
    pollUntilDone(res.data.job_id)
  } catch(e) {
    statusMsg.value = '启动失败: '+(e.response?.data?.detail||e.message)
    running.value = false
  }
}

function pollUntilDone(jobId) {
  const iv = setInterval(async () => {
    try {
      const s = await api.get('/ml/train/status')
      statusMsg.value = s.data.message || ''
      trainingProgress.value = s.data.progress_pct || 0
      if (!s.data.running) {
        clearInterval(iv); running.value = false
        trainingProgress.value = 100
        statusMsg.value = s.data.message || '完成!'
        await loadCurrentMeta()
        await loadFactorEval()
        await loadPredictions()
        await loadHistory()
      }
    } catch { clearInterval(iv); running.value = false }
  }, 3000)
}

async function loadCurrentMeta() {
  try { const r = await api.get('/ml/train/meta'); if(r.data.val_IC!=null) currentMeta.value=r.data } catch {}
}
async function loadFactorEval() {
  try { const r = await api.get('/ml/factor_eval'); icResults.value=r.data.results||[]; icUpdated.value=r.data.updated } catch {}
}
async function loadPredictions() {
  try { const r = await api.get(`/ml/predictions?n=30`); predictions.value=r.data.predictions||[]; predDate.value=r.data.date } catch {}
}
async function loadHistory() {
  try { const r = await api.get('/ml/train/history'); trainHistory.value=r.data.experiments||[] } catch {}
}
loadFsHistoryList()
function loadHistoryMeta(h) {
  currentMeta.value = h
  // 加载该实验对应的 IC 评估和预测
  api.get('/ml/factor_eval', { params: { job_id: h.job_id } }).then(r => {
    icResults.value = r.data.results || []
    icUpdated.value = r.data.updated
  }).catch(() => {})
  api.get('/ml/predictions', { params: { n: 30, job_id: h.job_id } }).then(r => {
    predictions.value = r.data.predictions || []
    predDate.value = r.data.date
  }).catch(() => {})
  resultTab.value = 'ic'  // 默认显示IC标签
}

// ── 智能模式历史 ──
async function loadFsHistory(h) {
  try {
    const r = await api.get('/ml/factor-select/result', { params: { job_id: h.job_id } })
    if (r.data.status === 'not_found') return
    fsResult.value = r.data
    if (r.data.stages?.screen?.passed_names) {
      selectedFsFactors.value = r.data.stages.screen.passed_names
    }
  } catch(e) {
    console.error('loadFsHistory failed', e)
  }
}

async function loadFsHistoryList() {
  try {
    const r = await api.get('/ml/factor-select/history')
    fsHistory.value = r.data.experiments || []
  } catch {}
}

// ── 智能选因子 ──
async function doSmartSelect() {
  fsRunning.value = true; fsProgress.value = 0; fsStatusMsg.value = '启动...'
  try {
    const res = await api.post('/ml/factor-select', {
      mode: fsCfg.mode,
      target_horizon: fsCfg.targetHorizon,
      lr: cfg.lr, leaves: cfg.leaves, estimators: cfg.estimators,
      screener: { min_ir_abs: 0.15, max_per_category: 5 },
      stability: { n_windows: fsCfg.nWindows },
      forward_select: { top_n: fsCfg.topN, min_ic_gain: 0.001 },
    })
    fsStatusMsg.value = res.data.message || '运行中...'
    fsPollTimer.value = setInterval(pollFsStatus, 3000)
  } catch(e) {
    fsStatusMsg.value = '启动失败: '+(e.response?.data?.detail||e.message)
    fsRunning.value = false
  }
}

async function pollFsStatus() {
  try {
    const s = await api.get('/ml/factor-select/status')
    fsProgress.value = s.data.progress_pct || 0
    fsStatusMsg.value = s.data.message || ''
    if (!s.data.running) {
      clearInterval(fsPollTimer.value); fsRunning.value = false
      fsProgress.value = 100; fsStatusMsg.value = s.data.message
      loadFsResult()
    }
  } catch { clearInterval(fsPollTimer.value); fsRunning.value = false }
}

async function loadFsResult() {
  try {
    const r = await api.get('/ml/factor-select/result')
    fsResult.value = r.data
    if (r.data.stages?.screen?.passed_names) {
      selectedFsFactors.value = r.data.stages.screen.passed_names
    }
    // 刷新智能模式实验记录
    loadFsHistoryList()
  } catch {}
}

function toggleFsFactor(k) {
  const i = selectedFsFactors.value.indexOf(k)
  if (i >= 0) selectedFsFactors.value.splice(i, 1)
  else selectedFsFactors.value.push(k)
}

function applySelectedFsFactors() {
  const factors = fsResult.value?.stages?.forward?.final_factors
  if (!factors?.length) return
  cfg.features = new Set(factors)
  // 切回手动模式
  trainMode.value = 'manual'
}

onMounted(() => {
  loadCurrentMeta(); loadFactorEval(); loadPredictions(); loadHistory(); loadFactorMeta()
  api.get('/ml/train/status').then(s => {
    if (s.data.running) { running.value=true; statusMsg.value=s.data.message; trainingProgress.value=s.data.progress_pct||0; pollUntilDone(s.data.job_id) }
  }).catch(()=>{})
})
</script>

<style scoped>
.ml-shell { max-width:1000px; margin:0 auto; padding:4px; color:#E6E9EE; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif; }
.ml-header { margin-bottom:24px; }
.ml-header h1 { font-size:24px; font-weight:800; margin:0 0 4px; }
.ml-header p { font-size:13px; color:#7A8494; margin:0; }

/* Card */
.ml-card { background:var(--card-bg); border:1px solid var(--border); border-radius: 8px; padding:20px; margin-bottom:16px; }
.ml-card-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.ml-card-head h2 { font-size:16px; font-weight:700; margin:0; }
.badge { padding:4px 12px; border-radius:20px; font-size:11px; font-weight:700; }
.badge-ok { background:rgba(34,197,94,0.12); color:#4ADE80; }
.badge-idle { background:#12161D; color:#7A8494; }
.badge-train { background:rgba(245,158,11,0.14); color:#F59E0B; animation:pulse-bg 1.5s infinite; }
@keyframes pulse-bg { 0%,100%{opacity:1} 50%{opacity:.6} }

/* Config */
.config-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:16px; margin-bottom:16px; }
.cfg-item { display:flex; flex-direction:column; gap:6px; }
.cfg-item > label { font-size:11px; font-weight:700; color:#98A2B3; text-transform:uppercase; }
.cfg-chips { display:flex; gap:6px; flex-wrap:wrap; }
.chip { padding:5px 12px; border-radius:6px; border:1.5px solid #262D38; background: var(--card-bg); font-size:12px; font-weight:600; cursor:pointer; color:#A4AEBB; transition:all .1s; }
.chip:hover { border-color:#7A8494; }
.chip.on { background: var(--primary); color:#fff; border-color:#E6E9EE; }
.cfg-row { display:flex; gap:10px; flex-wrap:wrap; }
.cfg-kv { display:flex; flex-direction:column; gap:2px; }
.cfg-kv span { font-size:10px; color:#7A8494; }
.kv-select { padding:5px 8px; border:1.5px solid #262D38; border-radius:6px; font-size:12px; background: var(--card-bg); }

/* Feature select */
.feature-select { margin-bottom:16px; }
.feature-select > .f-header-row { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px; }
.f-header-row > label { font-size:11px; font-weight:700; color:#98A2B3; text-transform:uppercase; }
.f-count { font-weight:400; color:#7A8494; }
.f-search { padding:5px 10px; border:1.5px solid #262D38; border-radius:8px; font-size:11px; width:200px; outline:none; transition:border-color .15s; }
.f-search:focus { border-color:#60A5FA; }
.f-chips { display:flex; gap:6px; flex-wrap:wrap; }
.f-cat-group { margin-bottom:8px; }
.f-cat-label { font-size:10px; font-weight:700; color:#98A2B3; padding:4px 0; display:flex; align-items:center; gap:4px; text-transform:uppercase; }
.f-cat-n { font-weight:400; color:#7A8494; }
.f-cat-sel { font-size:9px; color:#60A5FA; font-weight:500; margin-left:auto; }
.f-chip { font-family:'SF Mono',monospace; font-size:11px; padding:4px 10px; }
.collapse-arrow.sm { font-size:10px; line-height:1; }
.f-actions { display:flex; gap:12px; }
.f-action-link { background:none; border:none; font-size:11px; color:#60A5FA; cursor:pointer; }
.f-action-link:hover { text-decoration:underline; }

.train-btn { padding:10px 28px; border-radius:8px; border:none; background: var(--primary); color:#fff; font-size:14px; font-weight:700; cursor:pointer; }
.train-btn:disabled { opacity:.5; }
.train-note { margin-left:12px; font-size:12px; color:#98A2B3; }
.spinner-sm { display:inline-block; width:14px; height:14px; border:2px solid #fff; border-top-color:transparent; border-radius:50%; animation:spin .6s linear infinite; vertical-align:middle; }
@keyframes spin { to{transform:rotate(360deg)} }

/* Result meta */
.result-meta { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:12px; }
.rm-item { background:#12161D; border-radius:8px; padding:10px; display:flex; flex-direction:column; gap:2px; }
.rm-item span { font-size:10px; color:#7A8494; text-transform:uppercase; font-weight:600; }
.rm-item strong { font-size:14px; font-weight:700; font-family:'SF Mono',monospace; }
.rm-item strong.good { color:#4ADE80; } .rm-item strong.warn { color:#F59E0B; } .rm-item strong.bad { color:#F87171; }
.rm-importance { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.rm-imp-label { font-size:11px; color:#7A8494; font-weight:600; }
.rm-imp-chip { padding:3px 10px; border-radius: 8px; background:rgba(59,130,246,0.12); font-size:11px; font-family:'SF Mono',monospace; }
.rm-imp-chip em { font-weight:700; color:#60A5FA; font-style:normal; }
.meta-date { font-size:12px; color:#7A8494; }

/* IC Table */
.ic-table-wrap { overflow-x:auto; max-height:420px; overflow-y:auto; }
.pred-table-wrap { overflow-x:auto; max-height:480px; overflow-y:auto; }
.collapse-arrow { font-size:12px; color:#7A8494; transition:transform .2s; display:inline-block; }
.collapse-arrow.open { transform:rotate(180deg); }
.ic-table, .pred-table, .hist-table { width:100%; border-collapse:collapse; font-size:13px; }
.ic-table th, .pred-table th, .hist-table th { padding:10px 12px; text-align:left; background:#12161D; font-size:10px; font-weight:700; text-transform:uppercase; color:#7A8494; border-bottom:1px solid #161C24; }
.ic-table td, .pred-table td, .hist-table td { padding:10px 12px; border-bottom:1px solid #12161D; }
.th-num, .td-num { text-align:right; }
.td-factor { font-family:'SF Mono',monospace; font-size:12px; font-weight:600; color:#60A5FA; }
.td-num { font-family:'SF Mono',monospace; }
.td-num.strong { font-weight:700; }
.td-num.dim { color:#333B47; }
.ic-hint { margin:10px 0 6px; padding:8px 12px; background:#12161D; border:1px solid #171C24; border-radius:8px; font-size:12px; color:#98A2B3; line-height:1.7; }
.ic-hint b { color:#C9D1DB; }
.ic-row { cursor:pointer; transition:background .1s; }
.ic-row:hover td { background:#12161D; }
.ic-row.sel td { background:rgba(59,130,246,0.12); }
.ic-check { font-size:12px; margin-right:4px; }
.ic-badge { padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700; }
.ic-badge.excellent { background:rgba(34,197,94,0.12); color:#4ADE80; }
.ic-badge.good { background:rgba(59,130,246,0.12); color:#60A5FA; }
.ic-badge.moderate { background:rgba(245,158,11,0.14); color:#F59E0B; }
.ic-badge.weak { background:rgba(239,68,68,0.12); color:#F87171; }

/* Predictions */
.pred-table th { font-size:10px; }
.pred-row { cursor:pointer; transition:background .1s; }
.pred-row:hover td { background:#12161D; }
.td-rank { font-weight:700; color:#7A8494; }
.td-code { font-family:'SF Mono',monospace; font-size:12px; color:#98A2B3; font-weight:600; }
.td-name { font-weight:600; }
.up { color:#F87171; } .down { color:#4ADE80; }
.rsi-badge { padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700; font-family:'SF Mono',monospace; }
.rsi-badge.overbought { background:rgba(239,68,68,0.12); color:#F87171; }
.rsi-badge.oversold { background:rgba(34,197,94,0.12); color:#4ADE80; }

/* History */
.hist-row { cursor:pointer; }
.hist-row:hover td { background:#12161D; }

/* 智能选因子 */
.mode-toggle { display:flex; background:#161C24; border-radius:8px; padding:2px; }
.mode-toggle button { padding:5px 12px; border:none; border-radius:6px; font-size:12px; cursor:pointer; background:transparent; color:#98A2B3; transition:.15s; }
.mode-toggle button.on { background: var(--card-bg); color:#E6E9EE; font-weight:600; }
.smart-cfg { margin-top:12px; padding:12px; background:#12161D; border-radius:8px; border:1px solid #161C24; }
.smart-cfg-row { display:flex; gap:24px; flex-wrap:wrap; }
.smart-cfg-item { display:flex; align-items:center; gap:8px; font-size:12px; color:#98A2B3; }
.smart-radio { display:flex; align-items:center; gap:4px; cursor:pointer; font-size:12px; }
.stab-chip { display:inline-block; padding:4px 10px; border-radius:6px; background:#161C24; font-size:12px; cursor:pointer; transition:.15s; }
.stab-chip:hover { background:#262D38; }
.stab-chip.top { background:rgba(59,130,246,0.12); border:1px solid #60A5FA; color:#60A5FA; }
.stab-chip small { color:#7A8494; }
.drop-tag { display:inline-block; padding:2px 6px; background:rgba(239,68,68,0.12); color:#F87171; border-radius:4px; font-size:11px; margin:2px; }

/* Tab 导航 */
.tab-nav { display:flex; gap:0; border-bottom:2px solid #262D38; margin-bottom:12px; }
.tab-nav button { padding:8px 20px; border:none; background:transparent; font-size:13px; color:#98A2B3; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-2px; transition:.15s; }
.tab-nav button:hover { color:#E6E9EE; }
.tab-nav button.on { color:#60A5FA; border-bottom-color:#60A5FA; font-weight:600; }

.empty-hint { text-align:center; padding:40px 0; font-size:14px; color:#7A8494; }
</style>
