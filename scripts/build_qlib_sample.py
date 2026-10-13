#!/usr/bin/env python3
"""
由样例行情库构建 Qlib 数据集（可选，但推荐）
============================================
把 data/market.db 的日线转换成 **Qlib 原生二进制格式**，供因子分析 / 多因子轮动
回测使用。无第三方依赖（不需要安装 pyqlib），纯标准库实现。

生成结构：
    <repo>/qlib_data/
      ├── calendars/day.txt                 # 交易日历
      ├── instruments/all.txt               # 标的清单（code  start  end）
      └── features/<code>/<field>.day.bin   # 各字段二进制（float32）

用法：
    python scripts/build_qlib_sample.py                 # 输出到 <repo>/qlib_data
    QLIB_DATA_DIR=/path python scripts/build_qlib_sample.py   # 自定义目录

前置：先运行 `python examples/make_sample_data.py` 生成 data/market.db。
"""
import os
import sqlite3
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKET_DB = os.environ.get("MARKET_DB", str(ROOT / "data" / "market.db"))
QLIB_OUT = Path(os.environ.get("QLIB_DATA_DIR", str(ROOT / "qlib_data")))

# 字段名 → market.db.stock_daily 中的列
FIELDS = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "amount": "amount",
}


def _write_bin(path: Path, start_index: int, values) -> None:
    """写 Qlib 单字段二进制：float32 数组 [起始日历下标, 值...]。"""
    arr = array("f", [float(start_index)])
    arr.extend(float(v) for v in values)
    with open(path, "wb") as f:
        arr.tofile(f)


def build() -> None:
    if not Path(MARKET_DB).exists():
        raise SystemExit(
            f"未找到 {MARKET_DB}，请先运行：python examples/make_sample_data.py")

    conn = sqlite3.connect(MARKET_DB)
    conn.row_factory = sqlite3.Row

    # 1) 交易日历 = 所有股票日期的并集
    calendar = [r["date"] for r in conn.execute(
        "SELECT DISTINCT date FROM stock_daily ORDER BY date")]
    idx_of = {d: i for i, d in enumerate(calendar)}
    if not calendar:
        raise SystemExit("stock_daily 为空，请先运行 examples/make_sample_data.py")

    (QLIB_OUT / "calendars").mkdir(parents=True, exist_ok=True)
    (QLIB_OUT / "features").mkdir(parents=True, exist_ok=True)
    (QLIB_OUT / "instruments").mkdir(parents=True, exist_ok=True)

    with open(QLIB_OUT / "calendars" / "day.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(calendar) + "\n")

    codes = [r["code"] for r in conn.execute(
        "SELECT DISTINCT code FROM stock_daily ORDER BY code")]

    inst_lines = []
    for code in codes:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume, amount FROM stock_daily "
            "WHERE code=? ORDER BY date", (code,)).fetchall()
        if not rows:
            continue
        dates = [r["date"] for r in rows]
        start_index = idx_of[dates[0]]
        end_index = idx_of[dates[-1]]
        span = end_index - start_index + 1

        # 按日历位置对齐，缺失日填 NaN
        by_date = {r["date"]: r for r in rows}
        field_dir = QLIB_OUT / "features" / code
        field_dir.mkdir(parents=True, exist_ok=True)
        for field, col in FIELDS.items():
            vals = []
            for i in range(start_index, end_index + 1):
                r = by_date.get(calendar[i])
                vals.append(r[col] if r and r[col] is not None else float("nan"))
            _write_bin(field_dir / f"{field}.day.bin", start_index, vals)

        inst_lines.append(f"{code}\t{dates[0]}\t{dates[-1]}")

    with open(QLIB_OUT / "instruments" / "all.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(inst_lines) + "\n")

    conn.close()
    print(f"✅ 已生成 Qlib 数据集 → {QLIB_OUT}")
    print(f"   {len(codes)} 只标的 × {len(calendar)} 个交易日，字段：{', '.join(FIELDS)}")


if __name__ == "__main__":
    build()
