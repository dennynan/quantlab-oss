# 架构说明

## 总览

```
浏览器 (Vue3 SPA)
      │  /api/*（开发经 vite proxy，生产经 nginx 反代）
      ▼
FastAPI 后端 (backend/)
      ├── routers/   接口层：qlib / backtest / ml / rdagent
      ├── services/  业务层：因子、回测、模型、RD-Agent 编排
      └── 存储：SQLite
            ├── data/quantlab.db   业务库（回测历史等，首次自动建表）
            ├── data/market.db     行情库（样例由 examples/make_sample_data.py 生成）
            └── qlib_data/         Qlib 数据集（样例由 scripts/build_qlib_sample.py 生成）
```

## 关键设计

- **免登录**：`deps.py` 提供固定 demo 用户；`get_current_user()` 恒返回该用户，`get_db()` 提供 DB 会话。
- **数据解耦**：不绑定任何私有数据源；行情统一走本地 `market.db`（`MARKET_DB` 可覆盖）。
- **优雅降级**：LLM / Qlib 数据 / RD-Agent 缺失时，相关接口返回提示而非崩溃。
- **RD-Agent 隔离**：后端**绝不 import rdagent 包**，而是通过 `subprocess` 拉起独立 conda 环境里的 CLI。

## 主要模块

- `services/qlib_service.py`：因子分析（Qlib + Alpha158）与选股（读 market.db）
- `services/qlib_topk_backtest.py`：多因子轮动回测（Top-K 排名选股 + 定期轮动）
- `services/alpha158_factors.py`：Alpha158 因子定义
- `services/ml_service.py`：模型训练 / 评估
- `services/rdagent_service.py`：自动因子挖掘编排（可选）

## 数据流（一次因子分析）

1. 前端调用 `GET /api/qlib/...`
2. `qlib_service` 读取 `market.db` / Qlib 数据
3. 计算因子 → 返回前端 ECharts 渲染
