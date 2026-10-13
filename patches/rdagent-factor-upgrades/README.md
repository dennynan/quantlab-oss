# RD-Agent「挖因子」升级补丁

本目录把 QuantLab OSS「自动因子挖掘」里对 [RD-Agent](https://github.com/microsoft/RD-Agent) 的**因子挖掘算法升级**，
以补丁形式公开，方便你自己装 RD-Agent 时一并打上。

| 项 | 值 |
|---|---|
| 补丁文件 | `quantlab-rdagent-factor-upgrades.patch` |
| 规模 | 23 个文件（20 处修改 + 3 个新增模块），2458 行 |
| 开发基线 | 上游提交 `32b3d39`（2026-09-04，介于 `v0.8.0` 与 `v1.0.0` 之间） |
| 已验证可应用于 | **上游 `v1.0.0`**（干净应用，应用后与本项目自用版本逐字节一致） |
| SHA256 | `af2dc29725a619dd44c1d952e5e101cccb016abcbdac3b46ba8f80801c9cd19c` |

> 不打补丁时，RD-Agent 仍可正常运行，只是**没有**下面这些升级。

---

## 一、升级内容

原版 RD-Agent 的流程是「提假设 → 写代码 → 回测」，跑得起来，但挖因子的**判据**偏弱。
本补丁给这条流水线装了四道闸：**提案先过滤 → 入池要过筛 → 冗余要剪掉 → 换基线要服众**。

### 1. 因子池「只进不出」→ 入库前重选（贪心前向 + 显著性门槛）

- 原版把 `SOTA 因子 ∪ 新因子` 直接拼接回测，**只增不减**，弱因子长期占位，新因子很难顶掉旧因子；
  实测曾出现**连续约 20 次运行生效因子一个都没变**。
- 现在每次拼接后都做一次确定性筛选：按 `|RankIC|` 降序**贪心前向选择**保留 topk，
  并用 `|ICIR|·√days` 的统计显著性门槛挡掉噪声因子。
- 配置：`factor_select_enable` / `factor_select_topk`（默认 20）/ `factor_select_min_icir_tstat`（默认 2.0）。

### 2. 冗余治理：相关性剪枝 + 判重归一 + 同族窗口上限

- **相关性剪枝**：与已选因子横截面秩相关超过 `factor_select_corr_max`（默认 0.8）直接跳过；
- **判重归一**：剥掉 `_v2`、`_filtered`、`_100d` 这类换皮后缀再判重（原版只做名字精确匹配，加后缀即可绕过）；
  重复阈值 `factor_select_dup_corr`（默认 0.95），相关系数接近 `-1` 时标记为「取负号的白跑因子」——
  实测抓到过一对 `ρ = -1.000` 的因子；
- **同族窗口上限**：同一因子族（如 5/10/20/60 日窗口）最多保留 2 个，防止堆叠。

### 3. 入库前正交化 + 可解释性留存

- 新因子**入库前对已有因子库做横截面正交化**，从机制上消除「重复投票」；
- 正交化只使用当日信息（无未来函数）；
- 同时落盘 `combined_factors_raw.parquet`（正交化前原值，供归因/复用）与 `factor_ortho_manifest.json`（对谁正交化、β、配置），保住可复现。

### 4. 残差 IC 判据（默认关闭，附完整实现）

- 动机：原始 IC 与残差 IC 常常反向。实测 `VW_HIGH_LOW_RANGE_ASYM_RATIO_5D` 原始 IC `-0.0092`、残差 IC `+0.0375`（有增量）；
  而 `VW_MOMENTUM_20D` 原始 IC `-0.0516`、残差 IC `+0.0038`（≈纯冗余）。用原始 IC 排序会同时放过冗余的、砍掉正交的。
- 实测结论：真实候选几乎都是同族变体，残差判据会把新因子全部否掉、池子冻结，**故默认回退 `raw_ic`**，
  代码与开关保留（`factor_select_rank_by`，可用 `RDAGENT_FACTOR_RANK_BY` 覆盖）。
- 这不是「没做」，而是**用实证否决了一个方案**——冗余改由上面三件事 + 组合回测终审兜住。

### 5. 提案层规整（管住 LLM 乱提）

- **最短回看窗口 ≥ 5 交易日**：LLM 偏爱 1 日窗口（`intraday_range_1d`、`overnight_gap_1d`），Rank IC 长期贴噪声底、Calmar 靠运气；
  提案层直接禁掉并自动重提（`factor_min_window`，可用 `RDAGENT_MIN_FACTOR_WINDOW` 覆盖）。
- **换皮去重**：在提案阶段就拦掉「加个后缀绕过判重」的重复提案。
- **重试升温**：重试时自动抬高 LLM 温度，打破同一 prompt 下的确定性复读（`rdagent/oai/retry_temp.py`）。

### 6. 棘轮治理（Replace Best 判据）

- **问题**：`Replace Best` 是棘轮机制，连续 no-replace 后 LLM 提案会退化成局部变体（`roe_trend_filter → roe_trend_filter_100d`），整个 loop 卡在局部最优。
- **修 1｜基线改「会话历史最优」**：原基线取上一轮，标记一旦被清空就退化成种子基线 → 实测 Calmar 从 `0.525` 掉到 `0.094`，
  结果被 `0.102` 的劣质组合覆盖（事故会话 `rd_20260920_151207`）。
- **修 2｜棘轮硬闸**：当前 Calmar 未超过基线时，强制把 Replace 降级为 no（只降不升），避免劣质组合覆盖最优。
- **修 3｜停滞自动重启**（默认关闭）：连续 `factor_restart_patience`（默认 3）轮 no-replace 后，清空 SOTA 基线回到首轮重开。
  实测有副作用，需显式开启：环境变量 `RDAGENT_FACTOR_RESTART=1`。

---

## 二、包含的文件

**新增 3 个模块**

- `rdagent/scenarios/qlib/developer/factor_selector.py` — 因子池重选 / 相关性剪枝 / 判重归一 / 同族窗口上限 / 正交化
- `rdagent/scenarios/qlib/developer/stagnation_restart.py` — 停滞自动重启
- `rdagent/oai/retry_temp.py` — 重试升温

**修改 20 个文件**（主要几处）

- `rdagent/scenarios/qlib/developer/factor_runner.py` — 接入 `select_combined_factors`
- `rdagent/scenarios/qlib/developer/feedback.py` — 基线改「会话历史最优」+ 棘轮硬闸
- `rdagent/scenarios/qlib/proposal/factor_proposal.py` — 提案规整（最短窗口、去重）
- `rdagent/app/qlib_rd_loop/conf.py` — 新增 `factor_select_*` / `factor_restart_*` 配置
- `rdagent/utils/workflow/misc.py` — 重试策略
- `rdagent/oai/backend/litellm.py` — 重试升温接入
- 其余为配置模板（`factor_template/`、`model_template/`）、prompts、`factor_coder/`、`components/workflow/` 等配套改动

---

## 三、应用方式

### 方式 A：一键（自动克隆 v1.0.0 再打补丁）

```bash
cd patches/rdagent-factor-upgrades
./apply.sh --clone            # 克隆到 ./RD-Agent 并打补丁
```

### 方式 B：对已有仓库打补丁

```bash
git clone --depth 1 --branch v1.0.0 https://github.com/microsoft/RD-Agent.git
cd /path/to/RD-Agent
git apply /path/to/patches/rdagent-factor-upgrades/quantlab-rdagent-factor-upgrades.patch
```

### 打完补丁后

```bash
conda activate <你的 rdagent 环境>
pip install -e /path/to/RD-Agent
```

然后按主 README「🤖 RD-Agent（可选）」一节配好 `<RDAGENT_HOME>/.env` 即可。

---

## 四、卸载 / 回滚

补丁未打前先备份，或直接 revert：

```bash
cd /path/to/RD-Agent
git apply -R /path/to/patches/rdagent-factor-upgrades/quantlab-rdagent-factor-upgrades.patch
```

---

## 五、许可

补丁基于 RD-Agent（MIT）修改，遵循其原始许可。RD-Agent 版权归 Microsoft 及其贡献者所有。
