# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Changed（变更）
- 前端改为**深色极简**主题（Element Plus dark 变量 + 自定义 token；去投影、统一细边框与小圆角）
- **AI 分析 + AI 选股合并**为「分析 · 选股」单页（顶部 Tab 切换）
- **策略回测并入「模型实验室」**（Tab：策略回测 / 模型训练）
- 侧边栏导航精简为 3 项；旧路径（`/analysis`、`/screener`、`/backtest`、`/model-lab`）自动重定向到对应页面与 Tab，未知路径回落首页
- 样例行情库默认规模由 **8 只 × 300 日提升到 40 只 × 300 日**（含日/周/月 K）：8 只股票无法计算横截面 IC，因子筛选与模型训练会因样本不足而失败
- README「快速开始」改为**本地开发优先**（已验证路径），Docker 降为可选方式并标注「未在 CI / 实机实测」；补充 Python **3.12+** / Node **20+** 环境要求

### Added（新增）
- **RD-Agent 「挖因子」升级补丁随仓库发布**：本项目对 RD-Agent 在**挖因子环节**的升级（入库前重选「贪心前向 + 显著性门槛」、相关性剪枝、判重归一、同族窗口上限、入库前正交化、提案规整、棘轮治理）此前只存在于部署副本，现以补丁形式公开于 `patches/rdagent-factor-upgrades/`（针对上游 `v1.0.0`，含一键 `apply.sh` 与校验）；不打补丁则跑原版 RD-Agent
- **公网演示模式（`OSS_DEMO=1`）**：为「免登录开源版公开部署」而加的收敛开关——RD-Agent **只读化**（历史/状态/结果可查看，但禁止发起挖掘/清理，避免被白嫖付费 LLM 额度）+ 对训练 / 回测 / 筛选等重接口按来源 IP 限流（超限 429）；前端据此显示只读提示并禁用发起/清理按钮；本地开发不设该变量，行为不变。另：`/api/health` 增加 `demo` 字段
- **真实行情一键拉取**：新增 `make fetch-data`（`scripts/fetch_real_data.py`，**纯标准库**、无需 token）——从东方财富公开接口拉取近 1 年真实日 K（前复权，被限流时自动回退腾讯源），周/月 K 由日 K 本地聚合，MA/RSI/KDJ/BOLL 按标准公式本地计算，产出与样例库**逐列同构**的 `data/market.db`；内置 300 只高流动性标的池（`scripts/liquid300.csv`），支持 `--symbols` / `--top` / `--start` / `--end`；旧库自动备份为 `market.db.bak`
- **回测任务落盘**：结果写入 `data/backtest/<task_id>.json`，重启后仍可查询（以前任务在内存、重启即丢，轮询会 404）；新增 `GET /api/backtest/topk/history` 列出最近任务；只保留最近 **50** 条，启动时与每次写入后自动清理；内存改为 LRU（超限时从最旧的已结束任务开始淘汰）
- **回测任务按访客隔离**：后端从 `X-Anon-Id` 请求头（前端 localStorage 持久化）或 Cookie（自动下发）识别匿名访客，回测任务的查询/历史列表只返回自己的（免登录演示站下避免多位访客互相看到对方结果）
- **「策略回测」新增「🕘 历史回测」列表**：展示本访客最近的回测（时间 / 因子 / 参数 / 状态），点一条即可载入结果并回填参数表单，方便微调后重跑；带「🗑 清空」（二次确认）一键删本访客全部历史
- **界面截图**：`docs/screenshots/` 补上真实数据界面截图（个股分析 / 选股 / 模型实验室 / 自动因子挖掘），README 改为内嵌展示

### Removed（移除）
- 首页（作为独立落地页）
- 策略对比页及其 localStorage 相关代码

### Fixed（修复）
- **API 响应泄露部署路径**：`/api/backtest/topk/history` 的 `dir`、`/api/rdagent/disk` 的 `script`、
  `/api/rdagent/result` 与 `/api/rdagent/best-session` 的 `session_path` / `session_root` 一律改为
  **仓库内相对路径**（新增 `config.rel_path()`），不再向外暴露本机绝对路径
- **演示站限流误伤状态轮询 + `factor-select` 漏限流**（`OSS_DEMO=1`）：限流规则改为按「方法 + 路径」匹配，只限制**提交类 POST**，不再限制 `/api/backtest/topk/status`、`/history` 等只读轮询（否则前端轮询数秒即撞 429，任务跑完界面却看不到结果）；同时修正 `ml/factor_select` 写成了下划线、与实际路径 `ml/factor-select` 不匹配导致该条限流从未生效的问题
- 从「AI 选股」跳转到「AI 分析」时股票代码丢失（分析页此前未读取 `?code=`）
- **AI 个股分析报错 `no such table: stock_weekly`**：周/月 K 表缺失时改为由日 K 自动重采样兜底，样例生成器同步产出周/月 K
- **AI 选股报错 `no such column: sd5.close`**：交易日历改为全市场去重取日期，不再依赖硬编码股票代码
- **模型实验室训练历史 500**：训练指标含 `NaN` 导致 JSON 序列化失败，统一做非有限值清洗
- **「智能选因子」在样例库上一律失败**：阈值筛选把因子全砍光时退化为按 |IR| 每类取前 N，并在结果里给出 `note` 说明
- **AI 个股分析「MA20/MA60 偏离」恒为空**：后端补算 `ma20_dev` / `ma60_dev`
- **RD-Agent 缺环境时仍显示「挖掘中」**：启动前做环境预检，缺失时直接返回可操作的中文提示
- **RD-Agent 工作目录默认与他人部署共用**：开源版默认隔离到仓库内 `data/rdagent_demo`，并支持 `RDAGENT_CONDA_ENV` 指定 conda 环境名（默认取该目录 `.env` 的 `CONDA_ENV_NAME`）
- 「AI 选股」欢迎页写死「5204 只 A 股」→ 改为读取当前行情库实际标的数
- 「策略回测」预设卡片写死的实测收益补充口径说明（样例库为合成数据，结果不可复现）
- **「AI 研判」标签误导**：该报告两版都是**本地规则模板**生成（不调 LLM），开源版却标着 `Qlib + DeepSeek`；改为「量化研判 / Qlib 量化引擎 · 本地规则生成」，同时清理后端注释与报告标题
- **回测结果「因子构成」显示 `(NaN%)`**：`strategy_config.factors` 实为因子 key 数组（权重在并列的 `weights`），前端却按对象读 `f.key/f.weight` → 改为按位取权重并翻译因子名

## [0.1.0] - 2026-10-11

首个开源版本。

### Added（新增）
- 因子分析 + 选股（Qlib + Alpha158，market.db）
- 多因子轮动回测（Qlib Top-K 排名选股 + 定期轮动，含交易约束）
- 模型实验室（LightGBM 等）
- RD-Agent 自动因子挖掘集成（可选，需自行安装 RD-Agent）
- Docker + `make up` 一键启动
- `examples/make_sample_data.py` 合成样例行情库 + `scripts/build_qlib_sample.py` 构建 Qlib 样例数据集（保证开箱可跑）

### Removed（相较内部版本移除）
- 用户认证 / 登录 / 管理后台
- 新闻聚合页
- 自定义脚本回测引擎与 Qlib 官方回测引擎（仅保留多因子轮动）
- 数据同步管道与企业内部数据源
- 全部生产数据、密钥、内部基础设施配置

### Notes
- 开源版采用 MIT 许可证
- 无登录设计：所有请求以固定 demo 用户运行
