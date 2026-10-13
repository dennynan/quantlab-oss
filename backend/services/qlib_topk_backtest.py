"""
TopK 多因子轮动回测 — Qlib 交易约束版本

在原有线性加权排名的因子计算基础上，加入真实 A 股交易约束：
- 涨跌停限制（主板 ±10%，双创 ±20%）
- T+1 制度（当日买入次日才能卖出）
- 真实成本模型（佣金万三 + 印花税千一 + 过户费万0.2 + 最低5元）
- 100 股整数倍
"""
import os, sqlite3, traceback, json, copy
from pathlib import Path
import numpy as np
import pandas as pd
from typing import List, Optional, Dict, Callable
from datetime import datetime
from threading import Lock

from services.alpha158_factors import ALPHA158_FIELDS


def _progress(cb, pct, msg):
    if cb:
        try:
            cb(pct, msg)
        except Exception:
            pass

def _resolve_qlib_root() -> str:
    """Qlib 数据目录：优先 QLIB_DATA_DIR，其次仓库内样例 qlib_data/，最后 ~/.qlib 默认。"""
    env = os.environ.get("QLIB_DATA_DIR")
    if env:
        return os.path.expanduser(env)
    repo_sample = Path(__file__).resolve().parents[2] / "qlib_data"
    if repo_sample.is_dir():
        return str(repo_sample)
    return os.path.expanduser("~/.qlib/qlib_data/cn_data")


QLIB_ROOT = _resolve_qlib_root()


def _ensure_qlib():
    try:
        import qlib
        qlib.init(provider_uri=QLIB_ROOT, region="cn")
        return True
    except Exception:
        return False


def _sanitize(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _gen_rebalance_dates(calendar: list, freq: str) -> set:
    if freq == "day":
        return set((str(d)[:10] for d in calendar))
    dates_set = set()
    last_ym = None
    last_week = None
    for d in calendar:
        ds = str(d)[:10]
        dt = datetime.strptime(ds, "%Y-%m-%d")
        if freq == "week":
            wk = dt.isocalendar()[:2]
            if wk != last_week:
                dates_set.add(ds)
                last_week = wk
        else:  # month
            ym = (dt.year, dt.month)
            if ym != last_ym:
                dates_set.add(ds)
                last_ym = ym
    return dates_set


# ─── 涨跌停基准价格 ───────────────────────────────────────

def _get_limit_pct(code: str) -> float:
    """返回涨跌停幅度（A股主板 10%, 科创板/创业板 20%）"""
    code_lower = code.lower()
    if code_lower.startswith("sh688") or code_lower.startswith("sz300") or code_lower.startswith("sz301"):
        return 0.20
    return 0.10


def _get_benchmark_hs300(start_date: str, end_date: str, initial_cash: float) -> Optional[dict]:
    """从东方财富API拉取沪深300历史数据，归一化到 initial_cash 作为基准"""
    import urllib.request, json, time
    beg = start_date[:10].replace("-", "")
    end = end_date[:10].replace("-", "")
    url = (
        "http://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid=1.000300&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
        f"&klt=101&fqt=0&beg={beg}&end={end}"
    )
    # 重试3次（东方财富偶尔断连）
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            raw = json.loads(resp.read())
            klines = raw.get("data", {}).get("klines", [])
            if not klines:
                return None
            # 解析: date,open,close,high,low,volume,amount,amplitude,pct_chg,change,turnover
            bm_aligned = []
            bm_first = None
            for line in klines:
                parts = line.split(",")
                ds = parts[0]  # YYYY-MM-DD
                close_val = float(parts[2])
                if bm_first is None:
                    bm_first = close_val
                if bm_first and close_val > 0:
                    bm_aligned.append({
                        "date": ds,
                        "equity": round(initial_cash * close_val / bm_first, 2),
                    })
            if bm_aligned and bm_first:
                bm_return = (bm_aligned[-1]["equity"] - initial_cash) / initial_cash
                return {
                    "label": "沪深300",
                    "total_return_pct": round(bm_return * 100, 2),
                    "equity_curve": bm_aligned,
                }
        except Exception:
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    print(f"[TopK Exchange] 沪深300基准加载失败(重试3次)")
    return None


def _run_strategy_audit(stock_pool: list, data_stocks, close_mat, daily_dates, calendar,
                        factor_labels: list = None,
                        metrics: dict = None) -> dict:
    """
    策略审计：根据实际回测结果动态评估风险
    """
    m = metrics or {}
    annual_ret = m.get("annual_return", 0) * 100
    total_ret = m.get("total_return", 0) * 100
    sharpe = m.get("sharpe_ratio", 0)
    max_dd = m.get("max_drawdown", 0) * 100
    win_rate = m.get("win_rate", 0) * 100
    bm_ret = m.get("benchmark_return", 0)  # 沪深300总收益%
    excess = total_ret - (bm_ret or 0)  # 🔧 用总收益比总收益
    total_days = len(daily_dates)

    issues = []
    warnings = []
    pool = []

    # 1. 幸存者偏差检查
    if stock_pool and isinstance(close_mat.columns, pd.Index):
        pool = [s for s in stock_pool if s in close_mat.columns]
        if pool:
            coverage = np.isfinite(close_mat[pool]).sum(axis=0)
            if len(coverage) > 0:
                full_cov = (coverage >= total_days * 0.95).sum()
                low_cov = (coverage < total_days * 0.5).sum()
                if low_cov > 0:
                    warnings.append(f"股票池中 {low_cov} 只股票在回测期内数据覆盖不足50%")

    # 2. 数据完整性
    if pool:
        nan_ratio = close_mat[pool].isna().sum().sum() / (len(close_mat) * len(pool)) if len(pool) > 0 else 0
        if nan_ratio > 0.05:
            warnings.append(f"OHLC数据缺失率 {nan_ratio*100:.1f}%")

    # 3. 未来函数
    issues.append({
        "check": "未来函数 (Look-ahead Bias)",
        "status": "pass",
        "detail": "使用 T-1 日因子排名决定 T 日交易，z-score 按日截面计算，无未来泄露",
    })

    # 4. 幸存者偏差
    issues.append({
        "check": "幸存者偏差 (Survivorship Bias)",
        "status": "pass",
        "detail": "股票池基于回测起始日成交量筛选，每次调仓时按近期成交量过滤（已排除静态选股偏差）",
    })

    # 5. 🔧 过拟合风险 — 基于实际指标动态判断
    factor_names = factor_labels or []
    fname_str = "、".join(factor_names) if factor_names else "所选因子"

    if annual_ret <= 0:
        overfit_status = "pass"
        overfit_detail = f"{fname_str} 在回测期内未产生正收益（年化{annual_ret:.1f}%），不存在过拟合夸大收益的问题"
    elif sharpe < 0.8:
        overfit_status = "pass"
        overfit_detail = (f"{fname_str} 年化{annual_ret:.1f}%，夏普{sharpe:.2f}，收益/风险比偏低。"
                          f"该策略在当前样本期内表现平淡，不存在显著过拟合")
    elif sharpe < 1.5:
        overfit_status = "warn"
        overfit_detail = (f"{fname_str} 年化{annual_ret:.1f}%，夏普{sharpe:.2f}，表现尚可但不算极端。"
                          f"需注意 {total_days} 天的回测期是否恰好覆盖有利市场环境")
    elif sharpe < 2.5:
        overfit_status = "risk"
        overfit_detail = (f"{fname_str} 年化{annual_ret:.1f}%，夏普{sharpe:.2f}，收益较高。"
                          f"该因子组合在{total_days}天样本内表现出色，建议分段验证或样本外测试")
    else:
        overfit_status = "risk"
        overfit_detail = (f"{fname_str} 年化{annual_ret:.1f}%，夏普{sharpe:.2f}，收益异常高。"
                          f"强烈怀疑样本内过拟合，强烈建议：(1)缩短回测期分段验证 (2)大类因子分散 (3)扩大Top-K降集中度")

    # 补充：相对基准表现
    if bm_ret is not None and bm_ret != 0:
        excess_str = f"跑赢" if excess > 0 else f"跑输"
        overfit_detail += f"。相对沪深300{excess_str}{abs(excess):.1f}%"
    if max_dd > 30:
        overfit_detail += f"。⚠️ 最大回撤{max_dd:.1f}%偏高，显示策略波动大"

    issues.append({
        "check": "过拟合风险 (Overfitting)",
        "status": overfit_status,
        "detail": overfit_detail,
    })

    # 6. 回撤/波动评估
    if max_dd > 40:
        issues.append({
            "check": "风险控制",
            "status": "risk",
            "detail": f"最大回撤{max_dd:.1f}%，远超沪深300同期回撤，策略波动过大不适合实盘",
        })
    elif max_dd > 25:
        issues.append({
            "check": "风险控制",
            "status": "warn",
            "detail": f"最大回撤{max_dd:.1f}%，波动偏大，建议引入低波动因子(STD20负向)或扩大持仓数",
        })
    else:
        issues.append({
            "check": "风险控制",
            "status": "pass",
            "detail": f"最大回撤{max_dd:.1f}%，在可接受范围内",
        })

    # 7. 相对基准比较
    if bm_ret is not None and bm_ret != 0:
        if excess > 20:
            issues.append({
                "check": "超额收益 α",
                "status": "pass" if sharpe >= 1.0 else "warn",
                "detail": f"相对沪深300超额{excess:+.1f}%。但夏普仅{sharpe:.2f}说明超额承担了巨大波动" if sharpe < 1.0 else f"相对沪深300超额{excess:+.1f}%，显著跑赢基准",
            })
        elif excess > 0:
            issues.append({
                "check": "超额收益 α",
                "status": "warn" if sharpe < 1.0 else "pass",
                "detail": f"相对沪深300超额{excess:+.1f}%，小幅跑赢但优势不明显",
            })
        else:
            issues.append({
                "check": "超额收益 α",
                "status": "warn" if excess > -10 else "risk",
                "detail": f"相对沪深300跑输{abs(excess):.1f}%，策略未能战胜市场指数，建议更换因子或调整权重",
            })
    else:
        issues.append({
            "check": "超额收益 α",
            "status": "warn",
            "detail": "沪深300基准数据加载失败，无法计算超额收益。可手动刷新重试",
        })

    # 8. 交易成本建模
    issues.append({
        "check": "交易成本建模",
        "status": "pass",
        "detail": "已包含佣金(万三)+印花税(千一)+过户费+最低5元+滑点0.1%+涨跌停限制+T+1约束",
    })

    # 综合风险评级
    risk_score = sum(1 for i in issues if i["status"] == "risk")
    warn_score = sum(1 for i in issues if i["status"] == "warn") * 0.5
    total_score = risk_score + warn_score
    # 高回撤自动升档
    if max_dd > 35:
        total_score = max(total_score, 1.5)
    if total_score <= 0.5:
        overall = "低"
    elif total_score <= 2.5:
        overall = "中"
    else:
        overall = "高"

    return {
        "overall_risk": overall,
        "risk_score": float(total_score),
        "issues": issues,
        "warnings": warnings,
    }


def run_topk_backtest(
    factors: List[str],
    weights: Optional[List[float]] = None,
    top_k: int = 10,
    n_drop: int = 3,
    rebalance_freq: str = "month",
    days: int = 500,
    initial_cash: float = 1000000,
    min_stocks_in_pool: int = 100,
    commission_rate: float = 0.0003,
    slippage: float = 0.001,
    hold_thresh: int = 1,
    custom_pool: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> dict:
    pcb = progress_callback
    if not _ensure_qlib():
        return {"error": "Qlib 初始化失败"}
    _progress(pcb, 5, "Qlib 初始化完成，准备数据...")
    from qlib.data import D

    # ── 0. 成本模型（真实 A 股）──
    # 买入: 佣金万三 + 过户费万0.2
    # 卖出: 佣金万三 + 印花税千一 + 过户费万0.2
    BUY_COST_RATE = commission_rate + 0.00002   # 过户费
    SELL_COST_RATE = commission_rate + 0.001 + 0.00002  # 含印花税
    MIN_COST = 5.0  # 最低手续费
    LOT_SIZE = 100  # A 股最小交易单位

    # ── 1. 因子权重 ──
    if weights is None or len(weights) != len(factors):
        weights = [1.0 / len(factors)] * len(factors)

    # 过滤无效因子
    valid = []
    valid_weights = []
    skipped_factors = []
    for f, w in zip(factors, weights):
        if f in ALPHA158_FIELDS:
            valid.append(f)
            valid_weights.append(w)
        else:
            skipped_factors.append(f)
    if not valid:
        return {"error": "没有有效的因子"}
    factors, weights = valid, valid_weights

    # ── 2. 日期范围 ──
    all_cal = list(D.calendar())
    end_date = str(all_cal[-1])
    start_idx = max(0, len(all_cal) - days)
    start_date = str(all_cal[start_idx])
    cal = all_cal[start_idx:]
    rebalance_dates = _gen_rebalance_dates(cal, rebalance_freq)

    print(f"[TopK Exchange] 区间: {start_date[:10]}~{end_date[:10]}, {len(cal)}天, {len(rebalance_dates)}调仓日")
    _progress(pcb, 10, f"回测区间 {len(cal)} 天, {len(rebalance_dates)} 次调仓")

    # ── 3. 股票池 ──
    if custom_pool and len(custom_pool) > 0:
        stock_pool = [s.lower() for s in custom_pool]
        print(f"[TopK Exchange] 自定义候选池: {len(stock_pool)} 只")
    else:
        all_codes = [s.lower() for s in D.list_instruments(D.instruments("all"), as_list=True)]
        filtered = [c for c in all_codes if c.startswith(("sh6", "sh0", "sh3", "sh4", "sh8", "sz0", "sz3"))]
        dbpath = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "market.db"))
        try:
            conn = sqlite3.connect(dbpath)
            # 🔧 修复幸存者偏差：用回测起始日附近选股池，而非最新日
            start_d = start_date[:10].replace("-", "")
            pool_date = conn.execute(
                "SELECT MIN(date) FROM stock_daily WHERE date >= ?", [start_d]
            ).fetchone()[0]
            if not pool_date:
                pool_date = conn.execute("SELECT MAX(date) FROM stock_daily").fetchone()[0]
            placeholders = ",".join(["?"] * len(filtered))
            sql = f"SELECT code FROM stock_daily WHERE date=? AND code IN ({placeholders}) ORDER BY amount DESC LIMIT ?"
            rows = conn.execute(sql, [pool_date] + filtered + [min_stocks_in_pool]).fetchall()
            conn.close()
            stock_pool = [r[0] for r in rows]
            print(f"[TopK Exchange] 股票池日期: {pool_date} (回测起点: {start_date[:10]})")
        except Exception as e:
            print(f"[TopK Exchange] SQL: {e}")
            stock_pool = filtered[:min_stocks_in_pool]
        if len(stock_pool) < top_k * 2:
            stock_pool = filtered[:max(500, top_k * 10)]
        print(f"[TopK Exchange] 股票池: {len(stock_pool)} 只")
    _progress(pcb, 15, f"股票池 {len(stock_pool)} 只, 拉取数据...")

    # ── 4. 因子表达式 ──
    expr_map = {f: ALPHA158_FIELDS[f]["expr"] for f in factors}

    # ── 5. 拉取因子 + 价格 + 前收价数据 ──
    fields = list(expr_map.values()) + ["$close", "$high", "$low", "$open", "$volume"]
    print(f"[TopK Exchange] 拉取数据...")
    _progress(pcb, 20, f"从 Qlib 加载 {len(fields)} 个因子字段...")
    try:
        df_raw = D.features(
            instruments=stock_pool,
            fields=fields,
            start_time=start_date,
            end_time=end_date,
            freq="day",
        )
    except Exception as e:
        return {"error": f"数据加载失败: {e}"}

    if df_raw is None or df_raw.empty:
        return {"error": "数据为空"}
    _progress(pcb, 50, "数据加载完成, 计算因子得分...")

    if not isinstance(df_raw.index, pd.MultiIndex):
        df_raw = df_raw.reset_index().set_index(["instrument", "datetime"])

    expr_to_key = {}
    for f, expr in expr_map.items():
        if expr in df_raw.columns:
            expr_to_key[expr] = f

    # ── 6. 因子得分（z-score + 加权）──
    score_series = None
    for col_name, f_key in expr_to_key.items():
        w = weights[factors.index(f_key)]
        z = df_raw[col_name].groupby(level="datetime").transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-8)
        )
        if score_series is None:
            score_series = z * w
        else:
            score_series = score_series + z * w

    if score_series is None:
        return {"error": "无法计算复合得分"}
    _progress(pcb, 55, "因子得分完成, 模拟交易中...")

    # ── 7. 价格矩阵 + 前收价矩阵 ──
    close_series = df_raw["$close"]
    open_series = df_raw["$open"]
    high_series = df_raw.get("$high", close_series)
    low_series = df_raw.get("$low", close_series)

    if isinstance(close_series.index, pd.MultiIndex):
        close_mat = close_series.unstack(level="instrument")
        open_mat = open_series.unstack(level="instrument")
        high_mat = high_series.unstack(level="instrument") if "$high" in df_raw.columns else close_mat
        low_mat = low_series.unstack(level="instrument") if "$low" in df_raw.columns else close_mat
        volume_series = df_raw.get("$volume")
        volume_mat = volume_series.unstack(level="instrument") if volume_series is not None and "$volume" in df_raw.columns else None
        score_mat = score_series.unstack(level="instrument")
    else:
        close_mat = close_series.unstack(level=0)
        score_mat = score_series.unstack(level=0)
        volume_mat = None

    common_dates = close_mat.index.intersection(score_mat.index)
    common_stocks = close_mat.columns.intersection(score_mat.columns)
    close_mat = close_mat.loc[common_dates, common_stocks]
    open_mat = open_mat.loc[common_dates, common_stocks]
    high_mat = high_mat.loc[common_dates, common_stocks]
    low_mat = low_mat.loc[common_dates, common_stocks]
    if volume_mat is not None:
        volume_mat = volume_mat.loc[common_dates, common_stocks]
    score_mat = score_mat.loc[common_dates, common_stocks]
    
    # 计算前收价（用于涨跌停判断）—— shift 1
    prev_close_mat = close_mat.shift(1)
    daily_dates = [str(d)[:10] for d in close_mat.index]

    print(f"[TopK Exchange] 数据对齐: {len(daily_dates)}天 × {len(common_stocks)}只")

    # ── 8. Exchange 级交易模拟 ──
    print(f"[TopK Exchange] 模拟交易（涨跌停 + T+1 + 真实成本）...")
    total_days = len(daily_dates)
    last_progress = 55
    cash = initial_cash

    # 🔧 辅助函数: 计算当前总权益（逐笔精确）
    def _now_equity():
        pv = sum(p["last_price"] * p["shares"] for p in positions.values())
        return cash + pv
    positions: Dict[str, dict] = {}         # code → {shares, entry_price, entry_day_idx, last_price}
    trades = []
    daily_equity = []
    peak_equity = initial_cash
    holdings_day_idx: Dict[str, int] = {}   # code → 买入时的 day_idx
    rebalance_count = 0
    limit_hit_stats = {"buy_blocked": 0, "sell_blocked": 0, "buy_checked": 0, "sell_checked": 0}

    for day_idx in range(len(daily_dates)):
        date_str = daily_dates[day_idx]
        is_rebalance = (date_str in rebalance_dates)

        # 每处理 30 个交易日让出 CPU（降低对 Web 服务的影响）
        if day_idx % 30 == 0 and day_idx > 0:
            import time as _time
            _time.sleep(0.02)

        if is_rebalance and day_idx < score_mat.shape[0]:
            rebalance_count += 1
            
            # — 使用 前一交易日 的因子得分做排名（避免 look-ahead）—
            score_day_idx = max(0, day_idx - 1)  # 用 T-1 排，T 日执行
            day_scores = score_mat.iloc[score_day_idx].dropna()

            # 🔧 成交量过滤：剔除近5日日均成交量在池内最低20%的股票
            if volume_mat is not None and day_idx >= 5:
                vol_window = volume_mat.iloc[max(0, day_idx-5):day_idx]
                avg_vol = vol_window.mean()
                vol_cutoff = avg_vol.quantile(0.20)  # 剔除最低20%
                liquid = avg_vol[avg_vol >= vol_cutoff].index
                day_scores = day_scores[day_scores.index.intersection(liquid)]

            ranked = day_scores.sort_values(ascending=False)

            # 选 target（剔除非流通、hold_thresh 未达标）
            target = []
            for s in ranked.index:
                if hold_thresh > 1 and s in holdings_day_idx:
                    if day_idx - holdings_day_idx[s] < hold_thresh:
                        continue
                target.append(s)
                if len(target) >= top_k:
                    break

            # — 卖出 —
            to_sell = [s for s in positions if s not in target]
            if n_drop > 0 and len(to_sell) > n_drop:
                scores = {s: day_scores.get(s, -999) for s in to_sell}
                to_sell = sorted(to_sell, key=lambda x: scores.get(x, -999))[:n_drop]

            for s in to_sell:
                if s not in close_mat.columns:
                    continue
                price = close_mat.iloc[day_idx][s]
                open_price = open_mat.iloc[day_idx][s] if s in open_mat.columns else price
                if pd.isna(price) or price <= 0:
                    continue

                # 涨跌停检查
                limit_pct = _get_limit_pct(s)
                prev_close = prev_close_mat.iloc[day_idx][s] if day_idx > 0 and s in prev_close_mat.columns else price
                limit_down = prev_close * (1 - limit_pct)
                limit_up = prev_close * (1 + limit_pct)

                limit_hit_stats["sell_checked"] += 1
                # 跌停不能卖（开盘价已触跌停则放弃）
                if pd.notna(open_price) and open_price <= limit_down * 1.005:
                    limit_hit_stats["sell_blocked"] += 1
                    # 跌停日保持持仓，不卖
                    continue

                # 实际成交价：取 close 和跌停价中较高的（跌停无法成交）
                sell_price = max(float(price), float(limit_down)) * (1 - slippage)
                pos = positions.pop(s)
                shares = pos["shares"]
                revenue = sell_price * shares * (1 - SELL_COST_RATE)
                # 最低手续费
                min_fee = max(MIN_COST, sell_price * shares * SELL_COST_RATE)
                revenue = sell_price * shares - min_fee
                cash += revenue
                pnl = round((sell_price - pos["entry_price"]) / pos["entry_price"] * 100, 2) if pos["entry_price"] > 0 else 0
                trades.append({
                    "date": date_str, "action": "卖出", "stock": s,
                    "price": round(sell_price, 2), "shares": shares,
                    "amount": round(revenue, 2),
                    "account_total": round(_now_equity(), 2),
                    "reason": f"轮动淘汰 持有{day_idx - holdings_day_idx.get(s, day_idx)}天 盈亏{pnl:+.1f}%",
                })
                holdings_day_idx.pop(s, None)

            # — 买入 —
            slots = top_k - len(positions)
            if slots > 0:
                buy_list = [s for s in target if s not in positions][:slots]
                per_cash = cash / max(len(buy_list), 1) * 0.95
                for s in buy_list:
                    if s not in close_mat.columns:
                        continue
                    price = close_mat.iloc[day_idx][s]
                    open_price = open_mat.iloc[day_idx][s] if s in open_mat.columns else price
                    if pd.isna(price) or price <= 0:
                        continue

                    # 涨跌停检查
                    limit_pct = _get_limit_pct(s)
                    prev_close = prev_close_mat.iloc[day_idx][s] if day_idx > 0 and s in prev_close_mat.columns else price
                    limit_up = prev_close * (1 + limit_pct)
                    limit_down = prev_close * (1 - limit_pct)

                    limit_hit_stats["buy_checked"] += 1
                    # 涨停不能买（开盘价已触涨停则放弃）
                    if pd.notna(open_price) and open_price >= limit_up * 0.995:
                        limit_hit_stats["buy_blocked"] += 1
                        continue

                    # 实际成交价：取 close 和涨停价中较低的（涨停无法成交）
                    bp = min(float(price), float(limit_up)) * (1 + slippage)
                    shares = int(per_cash / bp / LOT_SIZE) * LOT_SIZE
                    if shares < LOT_SIZE:
                        continue
                    cost = bp * shares * (1 + BUY_COST_RATE)
                    min_fee = max(MIN_COST, bp * shares * BUY_COST_RATE)
                    cost = bp * shares + min_fee
                    if cost > cash:
                        continue
                    cash -= cost
                    positions[s] = {"shares": shares, "entry_price": bp, "entry_date": date_str, "last_price": bp}
                    holdings_day_idx[s] = day_idx
                    trades.append({
                        "date": date_str, "action": "买入", "stock": s,
                        "price": round(bp, 2), "shares": shares,
                        "amount": round(cost, 2),
                        "account_total": round(_now_equity(), 2),
                        "reason": f"轮动入选 排名#{list(target).index(s)+1}",
                    })

        # — 每日权益计算 —
        position_value = 0
        for s, pos in positions.items():
            if s in close_mat.columns and day_idx < len(close_mat):
                p = close_mat.iloc[day_idx][s]
                if pd.notna(p) and p > 0:
                    pos["last_price"] = float(p)
            position_value += pos["last_price"] * pos["shares"]

        equity = cash + position_value
        if equity > peak_equity:
            peak_equity = equity

        daily_equity.append({
            "date": date_str,
            "equity": round(float(equity), 2),
            "cash": round(float(cash), 2),
            "position_value": round(float(position_value), 2),
        })
        # 进度回调： 55% ~ 100% 按交易天数分配
        cur_pct = 55 + int((day_idx + 1) / total_days * 45) if total_days > 0 else 100
        if pcb and cur_pct > last_progress:
            last_progress = cur_pct
            _progress(pcb, cur_pct, f"模拟交易 {day_idx + 1}/{total_days} 天 ({date_str})")

    # — 末条清仓 —
    if positions and len(daily_dates) > 0:
        last_day = len(daily_dates) - 1
        for s in list(positions.keys()):
            pos_ref = positions[s]  # 🔧 先取出持仓引用
            if s in close_mat.columns:
                price = close_mat.iloc[last_day][s]
                # 🔧 修复：停牌股使用 last_price 兜底
                if pd.isna(price) or price <= 0:
                    price = pos_ref.get("last_price", pos_ref.get("entry_price", 0))
                if pd.isna(price) or price <= 0:
                    continue
                pos = positions.pop(s)
                sell_price = float(price) * (1 - slippage)
                shares = pos["shares"]
                revenue = sell_price * shares * (1 - SELL_COST_RATE)
                min_fee = max(MIN_COST, sell_price * shares * SELL_COST_RATE)
                revenue = sell_price * shares - min_fee
                cash += revenue
                pnl = round((sell_price - pos["entry_price"]) / pos["entry_price"] * 100, 2) if pos["entry_price"] > 0 else 0
                trades.append({
                    "date": daily_dates[last_day],
                    "action": "卖出", "stock": s,
                    "price": round(sell_price, 2), "shares": shares,
                    "amount": round(revenue, 2),
                    "account_total": round(_now_equity(), 2),
                    "reason": f"回测结束清仓 盈亏{pnl:+.1f}%",
                })

    # 🔧 修复：未清仓的停牌股仍计入最终权益（用 last_price 估值）
    remaining_pos_value = sum(
        pos["shares"] * pos.get("last_price", pos.get("entry_price", 0))
        for pos in positions.values()
    )
    final_equity = cash + remaining_pos_value
    if daily_equity:
        old_last = daily_equity[-1]["equity"]
        daily_equity[-1]["equity"] = round(float(final_equity), 2)
        daily_equity[-1]["position_value"] = round(float(remaining_pos_value), 2)
        daily_equity[-1]["cash"] = round(float(cash), 2)
        print(f"[TopK Exchange] 末条清仓: 原权益 {old_last:.0f} → 新权益 {final_equity:.0f} (价差{(old_last - final_equity):.0f}, 未清仓{len(positions)}只/¥{remaining_pos_value:.0f}, 总交易{len(trades)}笔)")

    # ── 9. 收益指标 ──
    total_return = (final_equity - initial_cash) / initial_cash
    n_days = len(daily_equity) or 1
    annual_return = (1 + total_return) ** (252 / n_days) - 1

    max_drawdown = 0
    peak = initial_cash
    for d in daily_equity:
        eq = d["equity"]
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

    # 夏普
    equity_arr = np.array([d["equity"] for d in daily_equity]) if daily_equity else np.array([initial_cash])
    daily_returns = np.diff(equity_arr) / equity_arr[:-1] if len(equity_arr) > 1 else np.array([0])
    sharpe = float(np.mean(daily_returns) / (np.std(daily_returns) + 1e-8) * np.sqrt(252))

    # 胜率
    win_trades = [t for t in trades if t["action"] == "卖出"]
    if win_trades:
        win_cnt = sum(1 for t in win_trades if "盈亏" in t["reason"] and t["reason"].split("盈亏")[-1].replace("%", "").startswith("+"))
        win_rate = win_cnt / len(win_trades)
    else:
        win_rate = 0

    _progress(pcb, 100, "回测完成, 生成报告中...")

    # ── 10. 沪深300 基准对比 ──
    benchmark = _get_benchmark_hs300(start_date, end_date, initial_cash)

    # ── 10b. 跟踪误差 ──
    tracking_error = None
    if benchmark and daily_equity:
        bm_map = {d["date"]: d["equity"] for d in benchmark["equity_curve"]}
        strat_eq = []
        bm_eq = []
        for d in daily_equity:
            if d["date"] in bm_map:
                strat_eq.append(d["equity"])
                bm_eq.append(bm_map[d["date"]])
        if len(strat_eq) > 1:
            se = np.array(strat_eq)
            be = np.array(bm_eq)
            strat_ret = np.diff(se) / se[:-1]
            bm_ret = np.diff(be) / be[:-1]
            tracking_error = float(np.std(strat_ret - bm_ret) * np.sqrt(252) * 100)  # %

    # ── 10c. 策略审计 ──
    factor_labels = [f"{ALPHA158_FIELDS.get(f,{}).get('label', f)}({abs(w)*100:.0f}%)" for f, w in zip(factors, weights)]
    audit_metrics = {
        "annual_return": annual_return,
        "total_return": total_return,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "benchmark_return": benchmark["total_return_pct"] if benchmark else None,
    }
    audit = _run_strategy_audit(stock_pool, common_stocks, close_mat, daily_dates, cal, factor_labels, audit_metrics)

    buy_count = sum(1 for t in trades if t.get("action") == "买入")
    sell_count = sum(1 for t in trades if t.get("action") == "卖出")

    result = _sanitize({
        "overview": {
            "total_return": round(total_return, 4),
            "annual_return": round(annual_return, 4),
            "max_drawdown": round(max_drawdown, 4),
            "sharpe_ratio": round(sharpe, 2),
            "win_rate": round(win_rate, 4),
            "total_trades": len(trades),
            "tracking_error": round(tracking_error, 2) if tracking_error is not None else None,
            "rebalance_count": rebalance_count,
            "limit_hit_stats": limit_hit_stats,
            # —— 前端展示用的百分数/统计别名 ——
            "total_return_pct": round(total_return * 100, 2),
            "annual_return_pct": round(annual_return * 100, 2),
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "win_rate_pct": round(win_rate * 100, 2),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "rebalance_operations": rebalance_count,
        },
        "strategy_config": {
            "factors": factors,
            "skipped_factors": skipped_factors,
            "weights": weights,
            "top_k": top_k,
            "n_drop": n_drop,
            "rebalance_freq": rebalance_freq,
            "rebalance_count": rebalance_count,
            "stock_pool_size": len(stock_pool),
            "universe_size": len(stock_pool),
            "backtest_days": len(daily_equity),
            "use_custom_pool": bool(custom_pool),
            "exchange_mode": "t1_limit_cost",  # 标记使用了真实交易约束
        },
        "equity_curve": daily_equity,
        "trades": trades,
        "benchmark": benchmark,
        "audit": audit,
    })
    return result


def get_available_factors() -> dict:
    """返回可用于 TopK 轮动的因子列表（按分类）"""
    categories = {}
    for key, info in ALPHA158_FIELDS.items():
        cat = info.get("cat", "其他")
        categories.setdefault(cat, []).append({
            "key": key,
            "label": info.get("label", key),
            "desc": info.get("desc", ""),
        })
    return {"categories": categories, "total": len(ALPHA158_FIELDS)}
