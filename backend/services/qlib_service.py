"""
QuantLab Qlib 量化服务层
因子分析（Qlib + Alpha158） + 股票筛选（market.db SQL）
"""
import os, sqlite3
from datetime import date
from services.alpha158_factors import (ALPHA158_FIELDS, CATEGORIES, get_alpha158_factor_list, get_alpha158_exprs)
import numpy as np
import pandas as pd
from pathlib import Path
from functools import lru_cache

def _default_qlib_data() -> str:
    """Qlib 数据目录：优先 QLIB_DATA_DIR，其次仓库内样例 qlib_data/，最后 ~/.qlib 默认。"""
    env = os.environ.get("QLIB_DATA_DIR")
    if env:
        return os.path.expanduser(env)
    repo_sample = Path(__file__).resolve().parents[2] / "qlib_data"
    if repo_sample.is_dir():
        return str(repo_sample)
    return os.path.expanduser("~/.qlib/qlib_data/cn_data")


QLIB_DATA = _default_qlib_data()
# 行情库路径（默认置于项目 data/ 下，可用环境变量 MARKET_DB 覆盖）
MARKET_DB = os.environ.get(
    "MARKET_DB", str(Path(__file__).resolve().parents[2] / "data" / "market.db"))
_qlib_ready = False


def _normalize_code(code: str) -> str:
    """补全交易所前缀：6/9/4/8 开头 → sh，其余 → sz（已带 sh/sz 前缀则原样返回）。"""
    code = (code or "").strip().lower()
    if code and not code.startswith(("sh", "sz")):
        code = ("sh" if code.startswith(("6", "9", "4", "8")) else "sz") + code
    return code


def _ensure_qlib():
    global _qlib_ready
    if _qlib_ready:
        return True
    if not Path(QLIB_DATA, "features").exists():
        return False
    try:
        import qlib
        from qlib.data import D
        qlib.init(provider_uri=QLIB_DATA, region="cn")
        _qlib_ready = True
        return True
    except Exception as e:
        print(f"[Qlib] init error: {e}")
        return False


# ── Health ──
def get_health() -> dict:
    if not _ensure_qlib():
        return {"status": "unavailable", "error": "数据未就绪"}
    from qlib.data import D
    cal = D.calendar()
    ins = D.list_instruments(D.instruments("all"), as_list=True)
    return {
        "status": "ok",
        "calendar_days": len(cal),
        "calendar_range": f"{cal[0]} ~ {cal[-1]}",
        "total_stocks": len(ins),
        "latest_trade_day": str(cal[-1]),
    }


# ── 因子定义 ──
FACTOR_DEFS = {
    "momentum_5":   {"label": "5日动量",   "unit": "%", "desc": "5日涨跌幅"},
    "momentum_20":  {"label": "20日动量",  "unit": "%", "desc": "20日涨跌幅"},
    "ma20_dev":     {"label": "MA20偏离",  "unit": "%", "desc": "收盘价距MA20偏离"},
    "ma60_dev":     {"label": "MA60偏离",  "unit": "%", "desc": "收盘价距MA60偏离"},
    "rsi_14":       {"label": "RSI(14)",   "unit": "",  "desc": "14日相对强弱"},
    "volatility_20":{"label": "20日波动率", "unit": "%", "desc": "20日年化波动率"},
    "avg_amount_20":{"label": "日均成交额", "unit": "万","desc": "当日成交额(万)"},
}


def get_factor_list() -> list:
    """返回全部因子：自建7个 + Alpha158"""
    custom = [{"key": k, "source": "custom", **v} for k, v in FACTOR_DEFS.items()]
    alpha158 = []
    for cat, keys in CATEGORIES.items():
        for k in keys:
            info = ALPHA158_FIELDS[k]
            alpha158.append({
                "key": k, "source": "alpha158", "category": cat,
                "label": info["label"], "desc": info["desc"],
                "expr": info["expr"], "unit": ""
            })
    return custom + alpha158


# ── Alpha158 单股因子 (via Qlib Expression) ──
@lru_cache(maxsize=512)
def get_alpha158_stock_factors(code: str) -> dict:
    """用Qlib表达式引擎查询单只股票的Alpha158因子"""
    if not _ensure_qlib():
        return {"error": "Qlib 未就绪"}
    from qlib.data import D

    code = _normalize_code(code)
    end = str(D.calendar()[-1])

    # 构建表达式→key映射，一次性查询所有Alpha158因子
    key_to_expr = {k: info["expr"] for k, info in ALPHA158_FIELDS.items()}
    exprs = list(key_to_expr.values())
    try:
        df = D.features(
            instruments=[code],
            fields=exprs,
            start_time="2025-01-01", end_time=end, freq="day")
    except Exception as e:
        return {"error": f"Alpha158查询失败: {e}"}

    if df is None or df.empty:
        return {"error": f"无Alpha158数据: {code}"}

    latest = df.iloc[-1]
    result = {"code": code, "date": str(df.index[-1][1])[:10]}
    
    # 构建列名→key的反向映射
    col_to_key = {}
    for k, expr in key_to_expr.items():
        if expr in df.columns:
            col_to_key[expr] = k
    
    factors = {}
    for col in df.columns:
        key = col_to_key.get(col)
        if not key:
            continue
        try:
            v = float(latest[col])
            if not (np.isnan(v) or np.isinf(v)):
                info = ALPHA158_FIELDS[key]
                factors[key] = {
                    "value": round(v, 4),
                    "label": info["label"],
                    "category": info["cat"],
                }
        except (ValueError, TypeError):
            pass

    result["factors"] = factors
    result["total"] = len(factors)
    return result


# ── 单股因子 (via Qlib) ──
@lru_cache(maxsize=256)
def get_stock_factors(code: str) -> dict:
    if not _ensure_qlib():
        return {"error": "Qlib 未就绪"}
    from qlib.data import D

    code = _normalize_code(code)
    end = str(D.calendar()[-1])

    try:
        df = D.features(
            instruments=[code],
            fields=["$close", "$open", "$high", "$low", "$volume", "$amount"],
            start_time="2024-01-01", end_time=end, freq="day")
    except Exception as e:
        return {"error": f"数据加载失败: {e}"}

    if df is None or df.empty:
        return {"error": f"无数据: {code}"}

    close = df["$close"]
    volume = df["$volume"]
    amount = df["$amount"]

    lc = float(close.iloc[-1])
    ld = str(df.index[-1][1])[:10]

    result = {
        "code": code,
        "name": _lookup_name(code),
        "latest_close": f"{lc:.2f}",
        "latest_date": ld,
    }

    # 动量
    for n in [5, 20]:
        if len(close) > n + 1:
            result[f"momentum_{n}"] = f"{(close.iloc[-1] / close.iloc[-n - 1] - 1) * 100:.2f}"

    # MA偏离
    for n in [20, 60]:
        if len(close) >= n:
            ma = float(close.rolling(n).mean().iloc[-1])
            result[f"ma{n}_dev"] = f"{(lc - ma) / ma * 100:.2f}"
            result[f"ma{n}"] = f"{ma:.2f}"

    # RSI(14)
    if len(close) >= 15:
        delta = close.diff()
        g = float(delta.clip(lower=0).rolling(14).mean().iloc[-1])
        l = float((-delta.clip(upper=0)).rolling(14).mean().iloc[-1])
        if l > 0:
            result["rsi_14"] = f"{100 - 100 / (1 + g / l):.1f}"

    # 波动率
    if len(close) >= 21:
        vol = float(close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252) * 100)
        result["volatility_20"] = f"{vol:.1f}"

    # 成交额
    if len(amount) >= 20:
        aa = float(amount.rolling(20).mean().iloc[-1]) / 1e4
        result["avg_amount_20"] = f"{aa:.0f}"

    # 换手率(估)
    if len(volume) >= 20:
        av = float(volume.rolling(20).mean().iloc[-1]) / 1e4
        result["turnover_20"] = f"{av:.1f}"

    # 均线排列
    mas = {}
    for n in [5, 10, 20, 60]:
        if len(close) >= n:
            mas[n] = float(close.rolling(n).mean().iloc[-1])
    ordered = [mas[k] for k in sorted(mas.keys())]
    result["ma_alignment"] = (
        "bullish" if all(ordered[i] >= ordered[i + 1] for i in range(len(ordered) - 1))
        else "bearish" if all(ordered[i] <= ordered[i + 1] for i in range(len(ordered) - 1))
        else "mixed"
    )

    result["ma_values"] = {f"ma{k}": f"{v:.2f}" for k, v in sorted(mas.items())}

    return result


def _lookup_name(code: str) -> str:
    try:
        conn = sqlite3.connect(MARKET_DB)
        r = conn.execute("SELECT name FROM stock_info WHERE code=?", (code,)).fetchone()
        conn.close()
        return r[0] if r else ""
    except Exception:
        return ""


# ── 股票筛选 (via market.db SQL, 秒级) ──
def screen_stocks(conditions: list, limit: int = 20) -> dict:
    db_path = MARKET_DB
    if not Path(db_path).exists():
        return {"error": "market.db 不存在"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    latest_date = conn.execute(
        "SELECT MAX(date) FROM stock_indicators"
    ).fetchone()[0]
    if not latest_date:
        conn.close()
        return {"error": "无指标数据"}

    # 历史日期 for 动量（用全市场去重交易日，不绑定某一只股票）
    dates_sql = conn.execute("""
        SELECT DISTINCT date FROM stock_daily
        ORDER BY date DESC LIMIT 22
    """).fetchall()
    dl = [r[0] for r in dates_sql]
    d5 = dl[5] if len(dl) > 5 else None
    d20 = dl[20] if len(dl) > 20 else None

    needs_m5 = any(c.get("factor") == "momentum_5" for c in conditions)
    needs_m20 = any(c.get("factor") == "momentum_20" for c in conditions)

    extra_joins = ""
    select_parts = []
    where_parts = []

    if needs_m5 and d5:
        extra_joins += f"\nLEFT JOIN stock_daily sd5 ON sd5.code = sd.code AND sd5.date = '{d5}'"
    if needs_m20 and d20:
        extra_joins += f"\nLEFT JOIN stock_daily sd20 ON sd20.code = sd.code AND sd20.date = '{d20}'"

    for cond in conditions:
        f = cond.get("factor", "")
        op = cond.get("op", "gt")
        target = cond.get("value", 0)

        if f == "momentum_5":
            if not d5:
                continue
            select_parts.append("ROUND((sd.close / sd5.close - 1) * 100, 2) as m5")
            where_parts.append(f"(sd.close / sd5.close - 1) * 100 {_op_sql(op, target)}")
        elif f == "momentum_20":
            if not d20:
                continue
            select_parts.append("ROUND((sd.close / sd20.close - 1) * 100, 2) as m20")
            where_parts.append(f"(sd.close / sd20.close - 1) * 100 {_op_sql(op, target)}")
        elif f == "ma20_dev":
            select_parts.append("ROUND((sd.close - si.ma20) / si.ma20 * 100, 2) as md20")
            where_parts.append(f"(sd.close - si.ma20) / si.ma20 * 100 {_op_sql(op, target)}")
        elif f == "ma60_dev":
            where_parts.append(f"(sd.close - si.ma60) / si.ma60 * 100 {_op_sql(op, target)}")
        elif f == "rsi_14":
            where_parts.append(f"si.rsi14 {_op_sql(op, target)}")
        elif f == "volatility_20":
            where_parts.append(
                f"(si.boll_upper - si.boll_lower) / si.boll_mid * 100 {_op_sql(op, target)}")
        elif f == "avg_amount_20":
            where_parts.append(f"sd.amount / 1e4 {_op_sql(op, target)}")

    if not where_parts:
        conn.close()
        return {"error": "不支持的筛选条件"}

    selects = ",\n".join(select_parts)
    extra_select = f",\n{selects}" if selects else ""
    where_clause = " AND ".join(where_parts)

    sql = f"""
    SELECT sd.code, sd.close, si.ma20, si.ma60, si.rsi14, inf.name{extra_select}
    FROM stock_daily sd
    JOIN stock_indicators si ON si.code = sd.code AND si.date = sd.date{extra_joins}
    LEFT JOIN stock_info inf ON inf.code = sd.code
    WHERE sd.date = '{latest_date}'
      AND ({where_clause})
      AND sd.close > 1
    ORDER BY sd.close DESC
    LIMIT {limit + 10}
    """

    try:
        rows = conn.execute(sql).fetchall()
        cnt = conn.execute(f"""
            SELECT COUNT(*) FROM stock_daily sd
            JOIN stock_indicators si ON si.code = sd.code AND si.date = sd.date{extra_joins}
            LEFT JOIN stock_info inf ON inf.code = sd.code
            WHERE sd.date = '{latest_date}' AND ({where_clause}) AND sd.close > 1
        """).fetchone()[0]
    except Exception as e:
        conn.close()
        return {"error": f"SQL: {e}"}
    conn.close()

    results = []
    for row in rows:
        d = dict(row)
        item = {
            "code": d["code"],
            "name": d.get("name", ""),
            "close": round(d["close"], 2),
        }
        if d.get("ma20") and d["close"]:
            item["ma20_dev"] = round((d["close"] - d["ma20"]) / d["ma20"] * 100, 2)
        if d.get("rsi14"):
            item["rsi_14"] = round(d["rsi14"], 1)
        if "m5" in d and d["m5"] is not None:
            item["momentum_5"] = round(d["m5"], 2)
        if "m20" in d and d["m20"] is not None:
            item["momentum_20"] = round(d["m20"], 2)
        results.append(item)

    return {
        "total_matched": cnt,
        "stocks": results[:limit],
        "has_more": cnt > limit,
        "latest_date": latest_date,
    }


# ── 全量单股分析 (分析页用) ──
def get_stock_full_analysis(code: str) -> dict:
    """综合单股分析：Qlib指标 + 多周期K线 + 形态检测 + 研判报告（本地规则生成）"""
    code = _normalize_code(code)
    db_path = MARKET_DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 1. 股票信息
    info = conn.execute("SELECT * FROM stock_info WHERE code=?", (code,)).fetchone()
    if not info:
        conn.close()
        return {"error": f"未知股票: {code}"}

    name = info["name"]

    # 2. 最近一日日K
    latest = conn.execute(
        "SELECT * FROM stock_daily WHERE code=? ORDER BY date DESC LIMIT 1", (code,)
    ).fetchone()
    if not latest:
        return {"error": f"无日K数据: {code}"}

    price = round(latest["close"], 2)
    prev_day = conn.execute(
        "SELECT close FROM stock_daily WHERE code=? AND date<? ORDER BY date DESC LIMIT 1",
        (code, latest["date"])
    ).fetchone()
    prev_close = prev_day["close"] if prev_day else price
    change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0

    # 3. 最新指标
    ind = conn.execute(
        "SELECT * FROM stock_indicators WHERE code=? ORDER BY date DESC LIMIT 1", (code,)
    ).fetchone()

    # 4. 多周期K线
    daily = _fetch_kline_rows(conn, "stock_daily", code, 90)
    weekly = _fetch_kline_rows(conn, "stock_weekly", code, 52)
    monthly = _fetch_kline_rows(conn, "stock_monthly", code, 24)

    # 5. 因子（从日K直接算）
    closes = np.array([r["close"] for r in daily])
    highs = np.array([r["high"] for r in daily])
    lows = np.array([r["low"] for r in daily])
    volumes = np.array([r["volume"] for r in daily])
    n = len(closes)

    factors = {}

    # MA
    for m in [5, 10, 20, 60]:
        if n >= m:
            factors[f"ma{m}"] = round(float(np.mean(closes[-m:])), 2)

    # RSI14
    if n >= 15:
        delta = np.diff(closes[-(15+1):])
        g = np.maximum(delta, 0); l = np.abs(np.minimum(delta, 0))
        ag = float(np.mean(g)); al = float(np.mean(l))
        factors["rsi14"] = round(100 - 100/(1 + ag/al), 1) if al > 0 else 100.0

    # 动量
    if n > 5:
        factors["momentum_5"] = round((closes[-1]/closes[-6] - 1) * 100, 2)
    if n > 20:
        factors["momentum_20"] = round((closes[-1]/closes[-21] - 1) * 100, 2)

    # 波动率
    if n > 20:
        factors["volatility_20"] = round(float(np.std(np.diff(closes[-21:])/closes[-21:-1])*np.sqrt(252)*100), 1)

    # 均线偏离（收盘价相对均线，%）— 前端「因子指标」区展示
    for m in (20, 60):
        ma = factors.get(f"ma{m}")
        if ma:
            factors[f"ma{m}_dev"] = round((closes[-1]/ma - 1) * 100, 2)

    # 均线排列
    mas_list = [factors.get(f"ma{m}", 0) for m in [5, 10, 20, 60] if f"ma{m}" in factors]
    if len(mas_list) >= 3:
        if all(mas_list[i] >= mas_list[i+1] for i in range(len(mas_list)-1)):
            factors["ma_alignment"] = "多头排列"
        elif all(mas_list[i] <= mas_list[i+1] for i in range(len(mas_list)-1)):
            factors["ma_alignment"] = "空头排列"
        else:
            factors["ma_alignment"] = "交叉震荡"

    conn.close()

    # 6. 形态检测
    patterns = _detect_patterns_simple(code, daily, weekly, monthly, factors)

    # 7. 五维评分
    scores = _compute_scores(factors, daily, volumes, price, change_pct)

    # 8. 总评
    total = _compute_total(scores)

    # 9. 研判报告（本地规则生成）
    report = _generate_ai_report(name, code, price, change_pct, factors, scores, total, patterns)

    return {
        "code": code,
        "name": name,
        "date": latest["date"],
        "price": price,
        "change_pct": change_pct,
        "open": round(latest["open"], 2),
        "high": round(latest["high"], 2),
        "low": round(latest["low"], 2),
        "volume": latest["volume"],
        "amount": latest["amount"],
        "factors": factors,
        "alpha158_factors": get_alpha158_stock_factors(code).get("factors", {}),
        "patterns": patterns,
        "scores": scores,
        "total": total,
        "report": report,
    }


def _fetch_kline_rows(conn, table, code, limit):
    """取多周期K线。若库中缺 stock_weekly/stock_monthly 表，
    则从日K实时重采样兜底（保证外部自建行情库也能用）。"""
    if not _table_exists(conn, table):
        period = "W" if table == "stock_weekly" else "M"
        return _resample_from_daily(conn, code, period, limit)
    r = conn.execute(f"SELECT * FROM {table} WHERE code=? ORDER BY date DESC LIMIT ?",
                     (code, limit)).fetchall()
    return [dict(row) for row in r[::-1]]


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _resample_from_daily(conn, code: str, period: str, limit: int) -> list:
    """把日K聚合为周K / 月K（open=首, close=尾, high=max, low=min, volume/amount=累加）。"""
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM stock_daily WHERE code=? ORDER BY date ASC", (code,)).fetchall()]
    except sqlite3.OperationalError:
        return []

    def key(ds: str):
        try:
            d = date.fromisoformat(ds[:10])
        except Exception:
            return ds
        if period == "W":
            iso = d.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        return f"{d.year}-{d.month:02d}"

    buckets: dict = {}
    order: list = []
    for r in rows:
        k = key(str(r.get("date", "")))
        if k not in buckets:
            buckets[k] = {**r}
            order.append(k)
            continue
        b = buckets[k]
        b["close"] = r.get("close", b.get("close"))
        b["high"] = max(b.get("high") or 0, r.get("high") or 0)
        b["low"] = min(b.get("low") or 0, r.get("low") or 0) if b.get("low") else r.get("low")
        b["volume"] = (b.get("volume") or 0) + (r.get("volume") or 0)
        b["amount"] = (b.get("amount") or 0) + (r.get("amount") or 0)
        b["date"] = r.get("date", b.get("date"))

    return [buckets[k] for k in order[-limit:]]


def _detect_patterns_simple(code: str, daily: list, weekly: list, monthly: list, factors: dict) -> dict:
    """多周期形态检测"""
    def detect(rows, closes=None):
        if closes is None:
            closes = np.array([r["close"] for r in rows])
        n = len(closes)
        if n < 10:
            return ["数据不足"]

        signals = []
        curr = closes[-1]

        # 均线交叉
        ma5 = np.mean(closes[-5:]) if n >= 5 else curr
        ma10 = np.mean(closes[-10:]) if n >= 10 else curr
        ma20 = np.mean(closes[-20:]) if n >= 20 else curr

        if n >= 20:
            prev_ma5 = np.mean(closes[-6:-1]) if n >= 6 else ma5
            prev_ma10 = np.mean(closes[-11:-1]) if n >= 11 else ma10
            prev_ma20 = np.mean(closes[-21:-1]) if n >= 21 else ma20

            if prev_ma5 < prev_ma10 and ma5 > ma10:
                signals.append("🔴 MA5↑金叉MA10")
            if prev_ma5 > prev_ma10 and ma5 < ma10:
                signals.append("🟢 MA5↓死叉MA10")

        # 多头/空头排列
        if n >= 60:
            ma60 = np.mean(closes[-60:])
            if ma5 > ma10 > ma20 > ma60:
                signals.append("📈 多头排列")
            elif ma5 < ma10 < ma20 < ma60:
                signals.append("📉 空头排列")

        # RSI 状态
        if factors.get("rsi14"):
            rsi = factors["rsi14"]
            if rsi > 80:
                signals.append("⚠️ RSI超买")
            elif rsi < 20:
                signals.append("💡 RSI超卖")
            elif rsi > 70:
                signals.append("📊 RSI偏高")
            elif rsi < 30:
                signals.append("🔍 RSI偏低")

        # KDJ 状态
        if len(rows) >= 9:
            r = rows[-1]
            h9 = max(row["high"] for row in rows[-9:])
            l9 = min(row["low"] for row in rows[-9:])
            if h9 != l9:
                rsv = (r["close"] - l9) / (h9 - l9) * 100
                if rsv > 80:
                    signals.append("⚠️ KDJ高位钝化")
                elif rsv < 20:
                    signals.append("💡 KDJ低位")

        # 价格位置
        if n >= 20:
            h20 = max(r["high"] for r in rows[-20:])
            l20 = min(r["low"] for r in rows[-20:])
            pos = (curr - l20) / (h20 - l20) * 100 if h20 != l20 else 50
            if pos > 90:
                signals.append("↑↑ 近20日高位")
            elif pos < 10:
                signals.append("↓↓ 近20日低位")

        # 距离MA20
        if ma20 and ma20 > 0:
            dev = (curr - ma20) / ma20 * 100
            if dev > 15:
                signals.append(f"📈 远离MA20(+{dev:.0f}%)")
            elif dev < -15:
                signals.append(f"📉 远离MA20({dev:.0f}%)")

        return signals if signals else ["无明显信号"]

    return {
        "day": detect(daily),
        "week": detect(weekly),
        "month": detect(monthly),
    }


def _compute_scores(factors: dict, daily: list, volumes, price, change_pct) -> dict:
    """五维评分：技术/价值/资金/热度/趋势"""
    scores = {}
    n = len(daily)

    # 技术面
    tech_score = 50
    tech_details = []
    rsi = factors.get("rsi14", 50)
    if rsi > 70:
        tech_score += 15; tech_details.append("RSI强势")
    elif rsi > 50:
        tech_score += 5; tech_details.append("RSI偏强")
    elif rsi < 30:
        tech_score -= 15; tech_details.append("RSI超卖")
    elif rsi < 50:
        tech_score -= 5; tech_details.append("RSI偏弱")

    ma_align = factors.get("ma_alignment", "")
    if ma_align == "多头排列":
        tech_score += 20; tech_details.append("均线多头")
    elif ma_align == "空头排列":
        tech_score -= 20; tech_details.append("均线空头")

    vol = factors.get("volatility_20", 30)
    if vol < 20:
        tech_score += 10; tech_details.append("低波动")
    elif vol > 50:
        tech_score -= 10; tech_details.append("高波动")

    m5 = factors.get("momentum_5", 0)
    if m5 > 10:
        tech_score += 15; tech_details.append("强势突破")
    elif m5 < -10:
        tech_score -= 15; tech_details.append("破位下行")

    tech_score = max(0, min(100, tech_score))
    tc = "#22c55e" if tech_score >= 60 else ("#ef4444" if tech_score <= 40 else "#f59e0b")
    tl = "强势" if tech_score >= 60 else ("弱势" if tech_score <= 40 else "中性")
    scores["technical"] = {"score": tech_score, "color": tc, "label": tl, "detail": " / ".join(tech_details) or "指标均衡"}

    # 价值面（简化：PB/PE位置）
    if n >= 120:
        closes = np.array([r["close"] for r in daily])
        h120 = float(np.max(closes))
        l120 = float(np.min(closes))
        pos_120 = (price - l120) / (h120 - l120) * 100 if h120 != l120 else 50
        value_score = round(100 - pos_120)  # 越低越有价值
        value_score = max(0, min(100, value_score))
        vc = "#22c55e" if value_score >= 60 else ("#ef4444" if value_score <= 40 else "#f59e0b")
        vl = "低位" if value_score >= 60 else ("高位" if value_score <= 40 else "适中")
        scores["value"] = {"score": value_score, "color": vc, "label": vl, "detail": f"近120日位置{pos_120:.0f}%"}
    else:
        scores["value"] = {"score": 50, "color": "#f59e0b", "label": "中性", "detail": "数据不足"}

    # 资金面（量价关系）
    flow_score = 50
    flow_details = []
    if n >= 10:
        recent_vol = np.mean(volumes[-5:])
        prev_vol = np.mean(volumes[-10:-5])
        if recent_vol > prev_vol * 1.5:
            flow_score += 20; flow_details.append("放量")
        elif recent_vol < prev_vol * 0.5:
            flow_score -= 10; flow_details.append("缩量")

        if change_pct > 3 and recent_vol > prev_vol * 1.3:
            flow_score += 15; flow_details.append("放量上涨")
        elif change_pct < -3 and recent_vol > prev_vol * 1.3:
            flow_score -= 15; flow_details.append("放量下跌")
        elif change_pct > 0 and recent_vol < prev_vol * 0.7:
            flow_score -= 5; flow_details.append("无量上涨")

    flow_score = max(0, min(100, flow_score))
    fc = "#22c55e" if flow_score >= 60 else ("#ef4444" if flow_score <= 40 else "#f59e0b")
    fl = "流入" if flow_score >= 60 else ("流出" if flow_score <= 40 else "中性")
    scores["money_flow"] = {"score": flow_score, "color": fc, "label": fl, "detail": " / ".join(flow_details) or "量价正常"}

    # 热度（换手率估算 + 动量）
    heat_score = 50
    heat_details = []
    if n >= 5:
        avg_vol = float(np.mean(volumes[-5:]))
        if avg_vol > 5e7:
            heat_score += 20; heat_details.append("高换手")
        elif avg_vol < 5e6:
            heat_score -= 10; heat_details.append("低换手")

    if abs(m5) > 5:
        heat_score += min(abs(m5), 20); heat_details.append(f"5日动量{m5:.1f}%")

    heat_score = max(0, min(100, heat_score))
    hc = "#22c55e" if heat_score >= 60 else ("#ef4444" if heat_score <= 40 else "#f59e0b")
    hl = "活跃" if heat_score >= 60 else ("冷清" if heat_score <= 40 else "正常")
    scores["heat"] = {"score": heat_score, "color": hc, "label": hl, "detail": " / ".join(heat_details) or "交易正常"}

    # 趋势
    trend_score = 50
    trend_details = []
    if m5 > 0 and factors.get("momentum_20", 0) > 0:
        trend_score += 20; trend_details.append("短中期向上")
    elif m5 < 0 and factors.get("momentum_20", 0) < 0:
        trend_score -= 20; trend_details.append("短中期向下")
    if ma_align == "多头排列":
        trend_score += 20; trend_details.append("均线多头")
    elif ma_align == "空头排列":
        trend_score -= 20

    trend_score = max(0, min(100, trend_score))
    trc = "#22c55e" if trend_score >= 60 else ("#ef4444" if trend_score <= 40 else "#f59e0b")
    trl = "上升" if trend_score >= 60 else ("下降" if trend_score <= 40 else "震荡")
    scores["trend"] = {"score": trend_score, "color": trc, "label": trl, "detail": " / ".join(trend_details) or "方向不明"}

    return scores


def _compute_total(scores: dict) -> dict:
    weights = {"technical": 0.25, "value": 0.15, "money_flow": 0.20, "heat": 0.15, "trend": 0.25}
    total = sum(scores[k]["score"] * w for k, w in weights.items())
    total = round(total)
    if total >= 70:
        color, grade = "#22c55e", "强势"
    elif total >= 50:
        color, grade = "#f59e0b", "中性偏强"
    elif total >= 30:
        color, grade = "#f97316", "中性偏弱"
    else:
        color, grade = "#ef4444", "弱势"
    return {"total": total, "color": color, "grade": grade, "weights": weights}


def _generate_ai_report(name, code, price, change_pct, factors, scores, total, patterns) -> str:
    """生成研判报告（本地规则模板，不依赖 LLM）"""
    up = "↑" if change_pct >= 0 else "↓"
    parts = [
        f"## {name}（{code}）量化研判报告",
        "",
        f"**现价：** {price} | **涨跌：** {up}{abs(change_pct)}%",
        "",
        "**【一、技术面研判】**",
        "",
    ]

    # 均线
    mas = {k: v for k, v in factors.items() if k.startswith("ma")}
    if mas:
        parts.append(f"均线：{', '.join(f'{k.upper()}={v}' for k, v in sorted(mas.items()))}")
        parts.append(f"排列状态：{factors.get('ma_alignment', '震荡')}")
    if "rsi14" in factors:
        rsi = factors["rsi14"]
        if rsi > 70:
            parts.append(f"RSI(14)={rsi}，处于超买区域，短期有回调压力")
        elif rsi < 30:
            parts.append(f"RSI(14)={rsi}，处于超卖区域，存在反弹机会")
        else:
            parts.append(f"RSI(14)={rsi}，处于正常区间")

    parts.extend(["", "**【二、形态信号】**", ""])
    for period, pname in [("day", "日线"), ("week", "周线"), ("month", "月线")]:
        sigs = patterns.get(period, [])
        parts.append(f"{pname}：{', '.join(sigs)}")

    parts.extend(["", "**【三、综合评分】**", ""])
    parts.append(f"总分：{total['total']}/100 — **{total['grade']}**")
    for k, s in scores.items():
        names = {"technical": "技术面", "value": "价值面", "money_flow": "资金面", "heat": "热度", "trend": "趋势"}
        parts.append(f"{names.get(k, k)}：{s['score']}分（{s['label']}）— {s['detail']}")

    parts.extend(["", "**【四、策略建议】**", ""])
    if total["total"] >= 70:
        parts.append("综合评分强势，可关注突破后回踩确认买点。")
        parts.append("注意RSI过高时不宜追高，等待回调至MA10/MA20附近更安全。")
    elif total["total"] >= 50:
        parts.append("综合评分中性偏强，可小仓位试探。")
        parts.append("等待放量突破关键均线或RSI转向后再加仓。")
    elif total["total"] >= 30:
        parts.append("综合评分偏弱，建议观望为主。")
        parts.append("关注RSI超卖反弹机会，但不宜重仓。")
    else:
        parts.append("综合评分弱势，建议规避。")
        parts.append("可等待均线走平、量能放大等见底信号再考虑入场。")

    parts.extend(["", "*以上分析基于量化模型和公开数据，仅供参考，不构成投资建议。*", ""])
    return "\n".join(parts)


def _op_sql(op: str, target) -> str:
    t = target
    if op == "gt": return f"> {t}"
    if op == "lt": return f"< {t}"
    if op == "gte": return f">= {t}"
    if op == "lte": return f"<= {t}"
    if op == "between" and isinstance(t, list) and len(t) == 2:
        return f"BETWEEN {t[0]} AND {t[1]}"
    return f"> {t}"
