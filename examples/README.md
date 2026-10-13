# examples

## make_sample_data.py

生成一个**合成**的最小行情库 `data/market.db`，让各页面开箱可用。

```bash
python examples/make_sample_data.py                 # 默认 40 只 × 300 交易日（≥30 只，IC 预筛/因子筛选才能工作）
python examples/make_sample_data.py --stocks 60 --days 500
```

生成表：`stock_info` / `stock_daily` / `stock_indicators`（结构与真实库一致）。
数据为随机漫步合成，**非真实行情**，仅用于跑通流程与演示。
