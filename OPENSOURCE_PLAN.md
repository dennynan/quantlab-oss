# OPENSOURCE_PLAN.md — 策略实验室开源方案（执行版）

> 目标：把「策略实验室 QuantLab」的部分功能，按开源规范抽取为一个**独立、干净、最小可跑**的开源仓库 `quantlab-oss/`（与内部开发仓分离的独立 git 仓库，单向导出，不回灌）。

---

## 0. 决策记录（2026-10-11）

- **范围**：因子/选股 + 多因子轮动回测 + 模型实验室 + **RD-Agent 自动因子挖掘**；**去掉用户认证/登录**（开箱免登录使用）
- **许可证**：MIT
- **仓库名**：`quantlab-oss/`（独立仓库，不携带内部仓历史）
- **交付形态**：Docker + 一键启动（同时保留本地开发方式）
- **展示**：README 含「在线 Demo + 界面截图」
- **原则**：**该排除的排除，但保留最小可试运行状态**

---

## 1. 开源范围

### ✅ 纳入（公开）
- 后端路由：`qlib`（因子/选股）、`backtest`（多因子轮动回测）、`ml`（模型实验室）、`rdagent`（自动因子挖掘）
- 后端服务：`qlib_service`、`alpha158_factors`、`qlib_topk_backtest`、`ml_service`、`rdagent_service`
- 前端：Analysis / Screener / Backtest / ModelLab / AutoFactorLab + 应用框架（App、router、api、store、style）

### ❌ 排除（私有 / 无关 / 敏感）
- 认证与后台：登录鉴权、后台管理相关路由与页面
- 数据同步管道：对接私有数据源 / 私有库结构的模块（含历史修复脚本、归档代码）
- 生产数据：行情库、分钟库、业务库及其衍生产物（体积大且涉及数据授权）
- 运行环境与产物：虚拟环境、`node_modules/`、日志、报告
- 内部仓 `.git` 历史（含内部数据源/路径痕迹）——**绝不搬运**
- 个人痕迹：硬编码的本机绝对路径、维护者真名、内部主机/端口

### 🧩 替代方案（保证「最小可跑」）
- 生产行情库 → 提供 `examples/make_sample_data.py` 生成**合成小样例库**（若干股票 × 近 N 日 OHLCV，含日/周/月 K）
- Qlib 数据目录 → 提供 `scripts/build_qlib_sample.py`（生成小样例）并提供文档指引挂载自有 qlib 数据；缺失时相关功能优雅降级（返回提示而非崩溃）
- RD-Agent → 作为**可选运行模式**：文档说明需用户自行安装 RD-Agent + 配置 conda 环境；未配置时 `/api/rdagent/*` 优雅报错

---

## 2. 目标目录结构

```
quantlab-oss/
├── OPENSOURCE_PLAN.md      # 本文件
├── LICENSE                 # MIT
├── README.md               # 徽章 / 截图 / 在线 Demo / 快速开始
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── CHANGELOG.md
├── THIRD_PARTY_LICENSES.md
├── .gitignore
├── .env.example
├── Makefile                # make up / sample-data / qlib-sample / dev-frontend …
├── docker-compose.yml
├── docker/
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   └── nginx.conf
├── docs/
│   ├── screenshots/        # 界面截图
│   └── architecture.md
├── examples/
│   ├── make_sample_data.py # 合成 market.db
│   └── README.md
├── scripts/
│   ├── build_qlib_sample.py
│   ├── fetch_real_data.py  # 真实行情一键拉取（可选）
│   └── rdagent_cleanup.py
├── backend/
│   ├── main.py  config.py  database.py  models.py  schemas.py
│   ├── requirements.txt    # 锁定版本
│   ├── routers/  (qlib backtest ml rdagent + __init__)
│   └── services/ (见 §1 纳入清单)
└── frontend/
    ├── package.json  vite.config.js  index.html
    └── src/ (App.vue main.js style.css api/ router/ store/ views/ components/ assets/)
```

---

## 3. 开源合规清单

- [x] `LICENSE`（MIT）
- [x] `README.md`：介绍 / 功能 / 截图 / Demo / 快速开始 / 架构 / 免责声明
- [x] `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` / `SECURITY.md`
- [x] `CHANGELOG.md`（Keep a Changelog）
- [x] `.gitignore`（venv / node_modules / .env / data / \*.db / log）
- [x] `.env.example`（LLM Key / MARKET_DB / QLIB_DATA_DIR / RDAGENT_HOME / CONDA_ROOT / PORT）
- [x] `backend/requirements.txt`（已锁版本）
- [x] Docker：`docker-compose.yml` + 2 个 Dockerfile + nginx 反代 + `make up` 一键启动
- [x] `THIRD_PARTY_LICENSES.md`（第三方依赖许可）
- [x] CI（`.github/workflows/ci.yml`：后端 import 冒烟 + 前端 build；已在本地以等价环境复现通过）
- [x] Issue / PR 模板（`.github/ISSUE_TEMPLATE/*`、`.github/PULL_REQUEST_TEMPLATE.md`）
- [x] 免责声明（README / SECURITY 均含）

---

## 4. 脱敏策略（净室导出）

1. **净室新建**：`quantlab-oss/` 全新 `git init`，不搬旧 `.git`
2. **白名单复制**：逐文件 copy（非删黑名单）
3. **路径归一**：本机绝对路径（数据目录、qlib 数据等）→ 改为基于工程根 / 环境变量的相对路径
4. **密钥清零**：`.env` 不入库，仅留 `.env.example`
5. **双检**：`gitleaks` + 关键词扫描（绝对路径特征、真实姓名/用户名、`SECRET`、`api_key=` 等）
6. **可跑验证**：干净环境 clone 后按 README 起服务，合成样例数据下各页面可用

---

## 5. 分阶段计划与进度

- [x] **Phase 1 决策**：范围 / 许可证 / 仓库形态 —— ✅ 已定（见 §0）
- [x] **Phase 2 提取骨架**：净室建仓、白名单拷贝、目录重整、去认证（固定 demo 用户）
- [x] **Phase 3 脱敏 + 文档**：清路径 / 密钥清零、README / CONTRIBUTING、`.env.example`、依赖锁定
- [x] **Phase 4 可复现**：合成样例数据脚本、qlib 样例/降级、Docker + Makefile
- [x] **Phase 5 合规 + 验收**：LICENSE / CI / THIRD_PARTY、import 冒烟通过、首版提交

### 已完成
- 独立仓库 `quantlab-oss/`（独立 git 历史，白名单导出后端 + 前端，移除鉴权与数据同步管道）
- 合成样例数据生成（`make sample-data`）与 Qlib 小样例（`make qlib-sample`）
- 文档体系（README / CONTRIBUTING / CODE_OF_CONDUCT / SECURITY / CHANGELOG / THIRD_PARTY_LICENSES）
- **在线 Demo 已上线**（只读模式 `OSS_DEMO=1`：RD-Agent 历史可看、不可发起挖掘；重接口按来源 IP 限流）
- 端到端复核：干净 clone → 生成样例 → 启动后端（全路由通）→ 前端构建并逐页渲染通过

### 待办 / 后续可选项
- [ ] Issue / PR 模板已有，可按需补充 PR 模板细节
- [ ] Docker 实机构建验证（当前以本地开发方式为准）
- [ ] 用 `pip-licenses` 生成更完整的 `THIRD_PARTY_LICENSES`
- [ ] 视需要补充英文 README / 更详细架构文档

---

## 6. 验收标准

- 干净环境按 README 起服务（本地或 `docker compose up`）可跑；无 `.env` 也能起（AI 功能降级提示）
- 无任何本机绝对路径、无密钥、无生产数据残留（关键词扫描 0 命中）
- 因子查询 / 选股 / 回测 / 模型实验室 页面可访问且基于样例数据可用
- RD-Agent 页在未配置环境时给出清晰提示而非报错
- `LICENSE` = MIT，社区文件齐全，README 含截图与在线 Demo

---

_本文件为开源方案的执行记录，随项目演进更新。_
