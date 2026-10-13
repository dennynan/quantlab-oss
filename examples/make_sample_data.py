#!/usr/bin/env python3
"""
生成最小可跑的样例行情库（data/market.db）
==========================================
开源版不附带生产数据；本脚本用**合成数据**生成一个体积很小、结构一致
（stock_info / stock_daily / stock_indicators / stock_weekly / stock_monthly）的 SQLite 库，让各页面开箱可用。

用法：
    python examples/make_sample_data.py            # 默认 8 只 × 300 交易日
    python examples/make_sample_data.py --stocks 20 --days 500
"""
import argparse
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "market.db"

STOCKS = [
    ("sh600519", "样例白酒", "sh", "食品饮料"),
    ("sh601318", "样例保险", "sh", "非银金融"),
    ("sh600036", "样例银行", "sh", "银行"),
    ("sz000858", "样例酒业", "sz", "食品饮料"),
    ("sz000333", "样例家电", "sz", "家用电器"),
    ("sz300750", "样例电池", "sz", "电力设备"),
    ("sh600276", "样例医药", "sh", "医药生物"),
    ("sz002415", "样例安防", "sz", "电子"),
]


def trading_days(n: int):
    """从今天往前取 n 个「工作日」（粗略近似交易日，够样例用）。"""
    out, d = [], date.today()
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(out))


def aggregate_bars(rows, period):
    """把日K聚合为周K(W) / 月K(M)：open=区间首日, close=末日, high=max, low=min, 量额累加。"""
    from datetime import date as _d

    def key(ds):
        d = _d.fromisoformat(ds[:10])
        if period == "W":
            iso = d.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        return f"{d.year}-{d.month:02d}"

    buckets, order = {}, []
    for r in rows:
        k = key(r["date"])
        if k not in buckets:
            buckets[k] = {
                "code": r["code"], "date": r["date"], "open": r["open"], "close": r["close"],
                "high": r["high"], "low": r["low"], "volume": r["volume"], "amount": r["amount"],
            }
            order.append(k)
            continue
        b = buckets[k]
        b["close"] = r["close"]
        b["high"] = max(b["high"], r["high"])
        b["low"] = min(b["low"], r["low"])
        b["volume"] += r["volume"]
        b["amount"] += r["amount"]
        b["date"] = r["date"]
    return [buckets[k] for k in order]


def gen(db_path: Path, n_stocks: int, n_days: int, seed: int = 42):
    random.seed(seed)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE stock_info (
            code TEXT PRIMARY KEY, name TEXT, market TEXT, industry TEXT,
            list_date TEXT, updated TEXT, sw2_industry TEXT);
        CREATE TABLE stock_daily (
            code TEXT, date TEXT, open REAL, close REAL, high REAL, low REAL,
            volume INTEGER, amount REAL, turnover REAL, main_net REAL,
            super_big_net REAL, tiger_rank INTEGER DEFAULT 0, tiger_net REAL,
            tiger_reason TEXT, created TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (code, date));
        CREATE TABLE stock_indicators (
            code TEXT, date TEXT, ma5 REAL, ma10 REAL, ma20 REAL, ma60 REAL,
            rsi14 REAL, kdj_k REAL, kdj_d REAL, kdj_j REAL,
            boll_upper REAL, boll_mid REAL, boll_lower REAL,
            PRIMARY KEY (code, date));
        CREATE TABLE stock_weekly (
            code TEXT, date TEXT, open REAL, close REAL, high REAL, low REAL,
            volume INTEGER, amount REAL, PRIMARY KEY (code, date));
        CREATE TABLE stock_monthly (
            code TEXT, date TEXT, open REAL, close REAL, high REAL, low REAL,
            volume INTEGER, amount REAL, PRIMARY KEY (code, date));
        """
    )

    days = trading_days(n_days)
    stocks = STOCKS[:n_stocks] if n_stocks <= len(STOCKS) else STOCKS + [
        (f"sz{str(300000 + i).zfill(6)}", f"样例{i}", "sz", "综合")
        for i in range(n_stocks - len(STOCKS))
    ]

    for code, name, market, industry in stocks:
        cur.execute(
            "INSERT INTO stock_info VALUES (?,?,?,?,?,?,?)",
            (code, name, market, industry, "2015-01-01", date.today().isoformat(), industry),
        )
        price = random.uniform(8, 120)
        closes = []
        daily_rows = []
        for ds in days:
            drift = random.uniform(-0.03, 0.03)
            price = max(1.0, price * (1 + drift))
            o = price * random.uniform(0.98, 1.02)
            h = max(o, price) * random.uniform(1.0, 1.02)
            low = min(o, price) * random.uniform(0.98, 1.0)
            vol = int(random.uniform(3e5, 5e6))
            amt = round(vol * price * 100, 2)
            cur.execute(
                "INSERT INTO stock_daily (code,date,open,close,high,low,volume,amount,"
                "turnover,main_net,super_big_net) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (code, ds, round(o, 2), round(price, 2), round(h, 2), round(low, 2),
                 vol, amt, round(random.uniform(0.2, 8), 2),
                 round(random.uniform(-1e7, 1e7), 2), round(random.uniform(-5e6, 5e6), 2)),
            )
            daily_rows.append({
                "code": code, "date": ds, "open": round(o, 2), "close": round(price, 2),
                "high": round(h, 2), "low": round(low, 2), "volume": vol, "amount": amt,
            })
            closes.append(price)
        # 周K / 月K（由日K聚合，与真实行情库结构一致）
        for table, period in (("stock_weekly", "W"), ("stock_monthly", "M")):
            for b in aggregate_bars(daily_rows, period):
                cur.execute(
                    f"INSERT OR REPLACE INTO {table} (code,date,open,close,high,low,volume,amount) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (b["code"], b["date"], b["open"], b["close"], b["high"],
                     b["low"], b["volume"], b["amount"]),
                )
        # 技术指标（用收盘价简单推）
        for i, ds in enumerate(days):
            def ma(k):
                seg = closes[max(0, i - k + 1):i + 1]
                return round(sum(seg) / len(seg), 2)
            c = closes[i]
            cur.execute(
                "INSERT INTO stock_indicators VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (code, ds, ma(5), ma(10), ma(20), ma(60),
                 round(random.uniform(20, 80), 2), round(random.uniform(10, 90), 2),
                 round(random.uniform(10, 90), 2), round(random.uniform(0, 100), 2),
                 round(c * 1.05, 2), round(c, 2), round(c * 0.95, 2)),
            )

    conn.commit()
    cur.execute("VACUUM")
    conn.close()
    size_kb = db_path.stat().st_size // 1024
    print(f"✅ 已生成 {db_path}（{len(stocks)} 只 × {len(days)} 交易日，约 {size_kb} KB）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--stocks", type=int, default=40,
                    help="股票数量（默认 40；小于 30 时 IC 预筛/因子筛选将无法工作）")
    ap.add_argument("--days", type=int, default=300)
    a = ap.parse_args()
    gen(Path(a.db), a.stocks, a.days)
