#!/usr/bin/env python3
"""
拉取真实 A 股行情，生成 data/market.db（结构与样例库完全一致）
================================================================
**纯标准库**实现（urllib + sqlite3），不需要任何第三方依赖，也不需要 API token。

数据来源：公开行情接口（无需 token）
    - 主源：东方财富（日 K 前复权，含成交额 / 换手率）
    - 备用：腾讯财经（东财被限流时自动回退；换手率置空）
    - 日 K 线（前复权）；周 / 月 K 由日 K **本地聚合** 生成，与样例库口径一致
      （主源东方财富；被限流时自动回退腾讯源）
    - 标的池：内置 scripts/liquid300.csv（按成交额排序的高流动性标的快照）

产物：data/market.db，含 stock_info / stock_daily / stock_indicators /
      stock_weekly / stock_monthly 五张表，字段与 examples/make_sample_data.py
      **完全一致**，可直接被后端与 `make qlib-sample` 使用。

用法：
    python scripts/fetch_real_data.py                       # 内置池 300 只 × 近 1 年
    python scripts/fetch_real_data.py --top 50              # 只取前 50 只（快速验证）
    python scripts/fetch_real_data.py --symbols 600519,000001,300750
    python scripts/fetch_real_data.py --start 2025-01-01 --end 2025-12-31
    python scripts/fetch_real_data.py --out /tmp/x.db       # 不覆盖当前 data/market.db

⚠️ 数据版权归原数据源所有，**仅供本地研究与学习使用，请勿再分发**。
   本仓库不附带任何真实数据文件；脚本只在你自己的机器上按需拉取。
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import socket
import sqlite3
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "market.db"
UNIVERSE_CSV = Path(__file__).resolve().parent / "liquid300.csv"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

KLT_DAY = 101  # 日K（周/月K 由日K 本地聚合，不再额外请求）
# f51 日期 f52 开 f53 收 f54 高 f55 低 f56 量(手) f57 额(元) f58 振幅 f59 涨跌% f60 涨跌额 f61 换手%
FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"

DDL = """
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


# ─────────────────────────── 网络 ───────────────────────────
# 部分网络到东财的 IPv6 路径会返回「空响应」，强制走 IPv4 更稳。
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_only(host, *args, **kwargs):
    return [r for r in _orig_getaddrinfo(host, *args, **kwargs) if r[0] == socket.AF_INET]


socket.getaddrinfo = _ipv4_only  # type: ignore[assignment]


def http_json(url: str, retries: int = 6, timeout: int = 20) -> dict:
    """带指数退避重试的 GET + JSON 解析。

    东财接口在密集请求下会间歇性返回「空响应 / 直接断连」（防爬限流），
    因此空响应同样视为可重试错误。
    """
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "*/*",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            if not raw:
                raise IOError("空响应")
            return json.loads(raw.decode("utf-8", "ignore"))
        except Exception as e:  # noqa: BLE001 —— 网络异常一律重试
            last_err = e
            if i < retries - 1:
                time.sleep(min(1.0 * (2 ** i), 12.0) + random.uniform(0, 0.8))
    raise IOError(f"{retries} 次重试仍失败：{last_err}")


def to_secid(code: str) -> str:
    """sh600519 → 1.600519（沪=1，深/北=0）"""
    return ("1." if code[:2] == "sh" else "0.") + code[2:]


def eastmoney_bars(code: str, beg: str, end: str) -> list[dict]:
    """东财日 K（前复权），带成交量/成交额/换手率。"""
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={to_secid(code)}&ut=fa5fd1943c7b386f172d6893dbfba10b"
        f"&fields1=f1,f2,f3,f4,f5,f6&fields2={FIELDS2}"
        f"&klt={KLT_DAY}&fqt=1&beg={beg}&end={end}"
    )
    # 有备用源，东财只快试 3 次，避免被限流时白等
    data = (http_json(url, retries=3).get("data") or {})
    bars = []
    for line in data.get("klines") or []:
        p = line.split(",")
        if len(p) < 8:
            continue
        bars.append({
            "date": p[0],
            "open": float(p[1]),
            "close": float(p[2]),
            "high": float(p[3]),
            "low": float(p[4]),
            "volume": int(float(p[5])),
            "amount": float(p[6]),
            "turnover": float(p[10]) if len(p) > 10 and p[10] not in ("", "-") else None,
        })
    return bars


def tencent_bars(code: str, beg: str, end: str) -> list[dict]:
    """腾讯日 K（前复权）—— 备用源。

    东财被限流时自动改用它。差异：无换手率（置 NULL，下游因子未用到）
    与真实成交额，成交额用 收盘价×量×100 估算。
    """
    days = (date.fromisoformat(f"{end[:4]}-{end[4:6]}-{end[6:]}")
            - date.fromisoformat(f"{beg[:4]}-{beg[4:6]}-{beg[6:]}")).days
    cnt = min(max(int(days * 0.75) + 40, 60), 1600)
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={code},day,,,{cnt},qfq")
    node = (http_json(url).get("data") or {}).get(code) or {}
    rows = node.get("qfqday") or node.get("day") or []
    lo, hi = f"{beg[:4]}-{beg[4:6]}-{beg[6:]}", f"{end[:4]}-{end[4:6]}-{end[6:]}"
    bars = []
    for r in rows:
        ds = r[0]
        if not (lo <= ds <= hi) or len(r) < 6:
            continue
        o, c, h, low, v = (float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
        bars.append({"date": ds, "open": o, "close": c, "high": h, "low": low,
                     "volume": int(v), "amount": round(v * c * 100, 2), "turnover": None})
    return bars


def stock_name(code: str) -> str:
    """股票名称：东财失败时回退腾讯（GBK 文本）"""
    if not _EM["off"]:
        try:
            data = http_json("https://push2.eastmoney.com/api/qt/stock/get"
                             f"?secid={to_secid(code)}&ut=bd1d9ddb04089700cf9c27f6f7426281&fields=f58",
                             retries=2).get("data") or {}
            if data.get("f58"):
                return str(data["f58"])
        except Exception:  # noqa: BLE001
            pass
    try:
        req = urllib.request.Request(f"https://qt.gtimg.cn/q={code}",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            txt = resp.read().decode("gbk", "ignore")
        parts = txt.split('"')[1].split("~")
        if len(parts) > 1 and parts[1]:
            return parts[1]
    except Exception:  # noqa: BLE001
        pass
    return code


# 源熔断：东财连续失败若干次后本轮不再尝试，直接走腾讯
_EM = {"off": False, "fails": 0}


def fetch_daily(code: str, beg: str, end: str) -> tuple[list[dict], str]:
    """拉取日 K：东财优先，失败/为空时回退腾讯。返回 (bars, 来源)。"""
    if not _EM["off"]:
        try:
            bars = eastmoney_bars(code, beg, end)
            if bars:
                _EM["fails"] = 0
                return bars, "eastmoney"
        except Exception:  # noqa: BLE001
            pass
        _EM["fails"] += 1
        if _EM["fails"] >= 3:
            _EM["off"] = True
            print("   ⚠️ 东财连续失败（可能被限流），本轮改用腾讯源")
    bars = tencent_bars(code, beg, end)  # 再无退路，异常向上抛
    return bars, "tencent"


def aggregate_bars(rows: list[dict], period: str) -> list[dict]:
    """把日K聚合为周K(W) / 月K(M)，与 examples/make_sample_data.py 完全一致：
    open=区间首日, close=末日, high=max, low=min, 量额累加, date=区间最后一个交易日。

    用本地聚合而不是再请求一次周/月K 接口，可减少 2/3 的网络请求，也避开限流。
    """
    def key(ds: str) -> str:
        d = date.fromisoformat(ds[:10])
        if period == "W":
            iso = d.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        return f"{d.year}-{d.month:02d}"

    buckets: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        k = key(r["date"])
        if k not in buckets:
            buckets[k] = {"date": r["date"], "open": r["open"], "close": r["close"],
                          "high": r["high"], "low": r["low"],
                          "volume": r["volume"], "amount": r["amount"]}
            order.append(k)
            continue
        b = buckets[k]
        b["close"], b["date"] = r["close"], r["date"]
        b["high"] = max(b["high"], r["high"])
        b["low"] = min(b["low"], r["low"])
        b["volume"] += r["volume"]
        b["amount"] += r["amount"]
    return [buckets[k] for k in order]


# ─────────────────────────── 指标 ───────────────────────────
def sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def rsi(closes: list[float], n: int = 14) -> list[float | None]:
    """Wilder RSI"""
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= n:
        return out
    gain = loss = 0.0
    for i in range(1, n + 1):
        ch = closes[i] - closes[i - 1]
        gain += max(ch, 0.0)
        loss += max(-ch, 0.0)
    ag, al = gain / n, loss / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(ch, 0.0)) / n
        al = (al * (n - 1) + max(-ch, 0.0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def kdj(highs: list[float], lows: list[float], closes: list[float],
        n: int = 9) -> tuple[list[float | None], list[float | None], list[float | None]]:
    k_list: list[float | None] = [None] * len(closes)
    d_list: list[float | None] = [None] * len(closes)
    j_list: list[float | None] = [None] * len(closes)
    k = d = 50.0
    for i in range(len(closes)):
        if i < n - 1:
            continue
        hh = max(highs[i - n + 1:i + 1])
        ll = min(lows[i - n + 1:i + 1])
        rsv = 50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100
        k = (2 * k + rsv) / 3
        d = (2 * d + k) / 3
        k_list[i], d_list[i], j_list[i] = k, d, 3 * k - 2 * d
    return k_list, d_list, j_list


def boll(closes: list[float], n: int = 20, k: float = 2.0):
    mid = sma(closes, n)
    up: list[float | None] = [None] * len(closes)
    dn: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if mid[i] is None:
            continue
        seg = closes[i - n + 1:i + 1]
        m = mid[i]
        sd = (sum((x - m) ** 2 for x in seg) / n) ** 0.5
        up[i], dn[i] = m + k * sd, m - k * sd
    return up, mid, dn


def r2(v, nd=2):
    return None if v is None else round(v, nd)


# ─────────────────────────── 主流程 ───────────────────────────
def load_universe(symbols: str | None, top: int | None) -> list[tuple[str, str, str]]:
    if symbols:
        items = []
        for s in symbols.replace("，", ",").split(","):
            s = s.strip().lower()
            if not s:
                continue
            if not s[:2].isalpha():
                s = ("sh" if s[0] == "6" else "sz") + s
            items.append((s, "", ""))
        return items
    if not UNIVERSE_CSV.exists():
        raise SystemExit(f"未找到标的池 {UNIVERSE_CSV}，请改用 --symbols 指定股票")
    with open(UNIVERSE_CSV, encoding="utf-8") as f:
        rows = [(r["code"], r["name"], r.get("industry", "")) for r in csv.DictReader(f)]
    return rows[:top] if top else rows


def main() -> None:
    ap = argparse.ArgumentParser(description="拉取真实 A 股行情 → market.db（纯标准库）")
    ap.add_argument("--out", default=str(DEFAULT_DB), help="输出 DB 路径（默认 data/market.db）")
    ap.add_argument("--symbols", help="逗号分隔的股票代码，如 600519,000001（覆盖内置池）")
    ap.add_argument("--top", type=int, help="从内置池取前 N 只（默认全部 300 只）")
    ap.add_argument("--start", help="起始日 YYYY-MM-DD（默认：一年前）")
    ap.add_argument("--end", help="结束日 YYYY-MM-DD（默认：今天）")
    ap.add_argument("--sleep", type=float, default=0.3,
                    help="每次请求之间的间隔秒数（默认 0.3；被限流时可调大）")
    ap.add_argument("--list", action="store_true", help="只打印标的池，不拉取")
    ap.add_argument("--max-fail", type=int, default=8,
                    help="连续失败多少只就中止（防御被限流，默认 8）")
    args = ap.parse_args()

    try:  # 让进度实时可见（管道/重定向时也逐行刷新）
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    universe = load_universe(args.symbols, args.top)
    if args.list:
        for code, name, ind in universe:
            print(f"{code}\t{name}\t{ind}")
        print(f"共 {len(universe)} 只")
        return

    end = (date.fromisoformat(args.end) if args.end else date.today())
    beg = (date.fromisoformat(args.start) if args.start
           else end - timedelta(days=365))
    beg_s, end_s = beg.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        bak = out.with_suffix(out.suffix + ".bak")
        out.replace(bak)
        print(f"⚠️  已存在 {out.name}，备份为 {bak.name}")

    conn = sqlite3.connect(out)
    conn.executescript(DDL)
    cur = conn.cursor()

    today = date.today().isoformat()
    stats = {"ok": 0, "bars": 0}
    failed: list[tuple[str, str, str]] = []

    def ingest(code: str, name: str, industry: str, sleep: float) -> bool:
        """拉取并写入单只股票；返回是否成功。"""
        daily, src = fetch_daily(code, beg_s, end_s)
        if not daily:
            print(f"  - {code} 无数据（停牌/退市？）")
            time.sleep(sleep)
            return False

        if not name:  # --symbols 模式下补名称
            name = stock_name(code)

        cur.execute("INSERT OR REPLACE INTO stock_info VALUES (?,?,?,?,?,?,?)",
                    (code, name, code[:2], industry, "", today, industry))
        cur.executemany(
            "INSERT OR REPLACE INTO stock_daily (code,date,open,close,high,low,"
            "volume,amount,turnover,main_net,super_big_net) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(code, b["date"], b["open"], b["close"], b["high"], b["low"],
              b["volume"], b["amount"], b["turnover"], None, None) for b in daily])

        for key, table in (("W", "stock_weekly"), ("M", "stock_monthly")):
            bars = aggregate_bars(daily, key)
            cur.executemany(
                f"INSERT OR REPLACE INTO {table} (code,date,open,close,high,low,volume,amount) "
                "VALUES (?,?,?,?,?,?,?,?)",
                [(code, b["date"], b["open"], b["close"], b["high"], b["low"],
                  b["volume"], b["amount"]) for b in bars])

        closes = [b["close"] for b in daily]
        highs = [b["high"] for b in daily]
        lows = [b["low"] for b in daily]
        ma5, ma10, ma20, ma60 = sma(closes, 5), sma(closes, 10), sma(closes, 20), sma(closes, 60)
        rsi14 = rsi(closes, 14)
        k_l, d_l, j_l = kdj(highs, lows, closes)
        up, mid, dn = boll(closes, 20, 2)
        cur.executemany(
            "INSERT OR REPLACE INTO stock_indicators VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(code, daily[i]["date"], r2(ma5[i]), r2(ma10[i]), r2(ma20[i]), r2(ma60[i]),
              r2(rsi14[i]), r2(k_l[i]), r2(d_l[i]), r2(j_l[i]),
              r2(up[i]), r2(mid[i]), r2(dn[i])) for i in range(len(daily))])
        stats["ok"] += 1
        stats["bars"] += len(daily)
        tag = "" if src == "eastmoney" else " 〔腾讯源〕"
        print(f"  ✓ [{stats['ok']}/{len(universe)}] {code} {name} "
              f"{len(daily)} 根日K，累计 {stats['bars']}{tag}")
        time.sleep(sleep)
        return True

    def run_pass(items, sleep: float, label: str):
        print(f"🚀 {label}：{len(items)} 只 × {beg_s}~{end_s}（日 K 前复权，周/月K 本地聚合）")
        left, streak = [], 0
        for code, name, industry in items:
            try:
                good = ingest(code, name, industry, sleep)
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {code} 失败：{e}")
                good = False
            if good:
                streak = 0
            else:
                left.append((code, name, industry))
                streak += 1
                sleep = min(sleep * 1.5, 6.0)  # 失败则自动放缓
                if streak >= args.max_fail:
                    print(f"\n⚠️  连续 {streak} 只失败，疑似被数据源限流。已中止本轮。")
                    print("   建议：稍等几分钟后重跑（已写入的数据不会丢，会自动增量补齐），"
                          "或用 --sleep 调大间隔。")
                    break
            conn.commit()  # 每只都落盘，中断也不丢进度
        conn.commit()
        return left

    left = run_pass(universe, args.sleep, f"拉取 → {out}")
    # 第二轮：对失败的重试一次（拉长间隔，避开限流窗口）
    if left:
        time.sleep(5)
        print(f"↻ 重试 {len(left)} 只失败标的（间隔 {args.sleep * 3:.1f}s）")
        left = run_pass(left, args.sleep * 3, "重试")

    fail = len(left)

    conn.commit()
    cur.execute("VACUUM")
    conn.close()
    size_mb = out.stat().st_size / 1024 / 1024
    ok, total_bars = stats["ok"], stats["bars"]
    print(f"\n✅ 完成：{ok} 只成功 / {fail} 只失败，{total_bars} 根日线 → {out}（{size_mb:.1f} MB）")
    print("   下一步：make qlib-sample   # 由 market.db 构建 Qlib 数据集")
    if fail:
        codes = ",".join(c for c, _, _ in left)
        print(f"   失败代码：{codes}")
        print(f"   可重跑补齐（INSERT OR REPLACE，不会重复）：\n"
              f"     python scripts/fetch_real_data.py --symbols {codes}")


if __name__ == "__main__":
    main()
