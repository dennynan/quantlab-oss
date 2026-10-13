"""
LightGBM 选股模型 + 因子 IC/IR 评估
====================================
- 可配置：目标窗口、特征集、训练窗、验证比、超参
- 从 market.db 提取特征 + 未来收益标签
- 计算因子 Rank IC / IR（Spearman 秩相关）
- LightGBM 训练：预测未来 N 日收益率
- 全市场预测 top-N 推荐
- 支持多轮实验对比
"""
import sqlite3, os, json, pickle, time, threading, math
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# ── 资源限制（控制 CPU/内存占用，避免影响 Mac 其他功能）──
try:
    import resource
    # 限制数据段内存 ~2GB（macOS 上 RLIMIT_DATA 有效）
    GB = 1024**3
    soft, hard = resource.getrlimit(resource.RLIMIT_DATA)
    if hard > 2 * GB:  # 仅在无硬限时缩小
        resource.setrlimit(resource.RLIMIT_DATA, (2 * GB, 3 * GB))
except Exception:
    pass

# 限制底层数学库的线程数（避免 102 因子计算撑满全部核心）
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "market.db")
ML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ml")

os.makedirs(ML_DIR, exist_ok=True)
MODEL_PATH = os.path.join(ML_DIR, "lightgbm_model.pkl")
TRAIN_META = os.path.join(ML_DIR, "train_meta.json")
FACTOR_EVAL = os.path.join(ML_DIR, "factor_eval.json")
PREDICTIONS = os.path.join(ML_DIR, "predictions.json")
HISTORY_PATH = os.path.join(ML_DIR, "experiment_history.json")


def _finite(v, nd=None):
    """NaN / inf → None（JSON 序列化安全检查；小样本下 IC/MSE 常为 NaN）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, nd) if nd is not None else f


def _sanitize(obj):
    """递归把 NaN/inf 换成 None，保证响应可被 JSON 序列化。"""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return _finite(obj)
    return obj

# ── 全量 Alpha158 因子（与回测引擎 qlib_topk_backtest 共用同一套因子字典）──
from services.qlib_topk_backtest import ALPHA158_FIELDS

# 构建因子元数据（中文名+分类）
FACTOR_META = {}
for k, v in ALPHA158_FIELDS.items():
    FACTOR_META[k] = {"label": v.get("label", k), "cat": v.get("cat", "其他"), "expr": v.get("expr", "")}

ALL_FEATURES = list(FACTOR_META.keys())  # 102因子（与回测页完全一致）

TRAIN_STATUS = {"running": False, "job_id": None, "message": "", "started": None, "progress_pct": 0}

# 智能选因子状态
FACTOR_SELECT_STATUS = {"running": False, "job_id": None, "stage": "", "progress_pct": 0,
                        "message": "", "started": None}
FS_RESULT_PATH = os.path.join(ML_DIR, "factor_select_result.json")


def get_conn():
    return sqlite3.connect(DB)


def prepare_training_data(days: int = 730, target_horizon: int = 5,
                          features: list = None) -> pd.DataFrame:
    """从 market.db 提取 OHLCV 数据，按 Alpha158 公式计算 20 因子 + 未来 N 日收益标签"""
    if features is None:
        features = ALL_FEATURES
    conn = get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    print(f"[ML] 加载数据（{days}天, 目标={target_horizon}d）...")

    # 只读日K（不再需要 stock_indicators，因子全部从 OHLCV 计算）
    df = pd.read_sql(f"""
        SELECT code, date, open, high, low, close, volume, amount, turnover
        FROM stock_daily WHERE date >= ?
        ORDER BY code, date
    """, conn, params=(cutoff,))
    conn.close()

    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    print(f"[ML] 日K加载: {len(df)} 行, {df.code.nunique()} 只")

    # 按 Alpha158 公式批量计算全量因子（与回测引擎严格一致）
    def feat_per_stock(grp):
        grp = grp.copy()
        c = grp["close"].astype(float)
        o = grp["open"].astype(float)
        h = grp["high"].astype(float)
        l = grp["low"].astype(float)
        v = grp["volume"].astype(float)
        amt = grp["amount"].astype(float)
        eps = 1e-12

        # === K线型态（6个）===
        grp["KMID"] = (o + c) / 2
        grp["KMID2"] = (c - o) / (h - l + eps)
        grp["KLEN"] = (h - l) / o.replace(0, np.nan)
        grp["KLOW"] = (c - l) / (h - l + eps)
        grp["KSFT"] = o.pct_change()
        grp["KSFT2"] = (o - c.shift(1)) / c.shift(1).replace(0, np.nan)
        grp["QTLU5"] = (c - l) / (h - l + eps)

        # === 日收益（5/10/20/30/60）===
        ret = c.pct_change()
        vol_ret = v.pct_change()
        for N in [5, 10, 20, 30, 60]:
            sN = str(N)
            grp[f"Rtn{sN}"] = c.pct_change(N)
            grp[f"ROC{sN}"] = c.shift(N) / c - 1
            grp[f"REVS{sN}"] = (h - c.shift(N)) / c.shift(N).replace(0, np.nan)
            grp[f"VSUE{sN}"] = v.pct_change(N)
            
            # 均线偏离
            grp[f"MA{sN}"] = c.rolling(N).mean() / c.replace(0, np.nan)
            
            # 波动率
            grp[f"STD{sN}"] = c.rolling(N).std() / c.replace(0, np.nan)
            
            # 价格位置
            grp[f"HIGH{sN}"] = h.rolling(N).max() / c.replace(0, np.nan)
            grp[f"LOW{sN}"] = l.rolling(N).min() / c.replace(0, np.nan)
            
            # 极端振幅
            if "MAX" + sN in ALL_FEATURES:
                grp[f"MAX{sN}"] = h.rolling(N).max() / l.rolling(N).min().replace(0, np.nan)

            # 趋势累计（SUMP/SUMV）
            if "SUMP" + sN in ALL_FEATURES:
                grp[f"SUMP{sN}"] = (c / o - 1).rolling(N).sum()
            if "SUMV" + sN in ALL_FEATURES:
                grp[f"SUMV{sN}"] = vol_ret.rolling(N).sum()

            # 相关性
            if "CORR" + sN in ALL_FEATURES:
                grp[f"CORR{sN}"] = c.rolling(N).corr(np.log1p(v))
            if "CORD" + sN in ALL_FEATURES:
                grp[f"CORD{sN}"] = ret.rolling(N).corr(np.log1p(vol_ret))

            # 相对强度
            if "QTLU" + sN in ALL_FEATURES and N > 5:
                grp[f"QTLU{sN}"] = (c - l.rolling(N).min()) / (h.rolling(N).max() - l.rolling(N).min() + eps)

        # === 量比均线（MAV 5/10/20）===
        for N in [5, 10, 20]:
            sN = str(N)
            grp[f"MA{sN}V"] = v.rolling(N).mean() / (v + eps)

        # === 波动（WVMA/VSTD 5/10/20）===
        intra_ret = c / o - 1
        for N in [5, 10, 20]:
            sN = str(N)
            if f"WVMA{sN}" in ALL_FEATURES:
                grp[f"WVMA{sN}"] = intra_ret.rolling(N).std()
            if f"VSTD{sN}" in ALL_FEATURES:
                grp[f"VSTD{sN}"] = vol_ret.rolling(N).std()

        # === 收益/波动比（RtnVol 5/10/20）===
        for N in [5, 10, 20]:
            sN = str(N)
            k = f"RtnVol{sN}"
            if k in ALL_FEATURES:
                std_ret = ret.rolling(N).std()
                grp[k] = c.pct_change(N) / (std_ret + eps)

        # === 涨跌统计（IMXD/CNTP/CNTN/CNTD 5/10/20）===
        up_day = (c > o).astype(float)
        dn_day = (c < o).astype(float)
        inc_day = (c > c.shift(1)).astype(float)
        for N in [5, 10, 20]:
            sN = str(N)
            if f"IMXD{sN}" in ALL_FEATURES:
                grp[f"IMXD{sN}"] = up_day.rolling(N).mean()
            if f"CNTP{sN}" in ALL_FEATURES:
                grp[f"CNTP{sN}"] = up_day.rolling(N).sum()
            if f"CNTN{sN}" in ALL_FEATURES:
                grp[f"CNTN{sN}"] = dn_day.rolling(N).sum()
            if f"CNTD{sN}" in ALL_FEATURES:
                grp[f"CNTD{sN}"] = inc_day.rolling(N).sum()

        # === 金额均线（AMT 5/10/20/30）===
        for N in [5, 10, 20, 30]:
            sN = str(N)
            k = f"AMT{sN}"
            if k in ALL_FEATURES:
                grp[k] = np.log1p(amt.rolling(N).mean().fillna(0))

        # target: 未来 N 日收益率
        grp["target"] = c.shift(-target_horizon) / c - 1
        return grp

    # 批量处理股票（每批500只，批间释放 CPU）
    codes = sorted(df.code.unique())
    batch_size = 500
    results = []
    for i in range(0, len(codes), batch_size):
        batch_codes = codes[i:i+batch_size]
        batch = df[df.code.isin(batch_codes)].copy()
        batch = batch.groupby("code", group_keys=False).apply(feat_per_stock)
        results.append(batch)
        if i + batch_size < len(codes):
            time.sleep(0.03)
    df = pd.concat(results).reset_index(drop=True)

    before = len(df)
    # 只丢弃特征列的 NaN（不丢弃 target NaN，最新几天的 target 为 NaN 但仍可用于预测）
    drop_cols = [c for c in features if c in df.columns]
    df = df.dropna(subset=drop_cols)
    print(f"[ML] 去NaN: {len(df)} 行 (丢弃 {before-len(df)})")
    df = df[df["close"] > 0]
    print(f"[ML] 最终: {len(df)} 行, {df.code.nunique()} 只, target-NA {(df['target'].isna().sum())}")
    return df


# ── 因子评估口径（2026-09-17，对齐 Kronos P0-2c 评测纪律）──
MIN_STOCKS_PER_DAY = 30   # 每个横截面日至少这么多只有效标的才算一个有效 IC 日
MIN_DAYS_TRUST = 30       # 横截面日 < 30 视为样本不足（标 insufficient，不出结论）
LS_QUANTILE = 0.2         # 多空价差取前/后 20%


def evaluate_factor_ic(df: pd.DataFrame = None, features: list = None) -> list:
    """因子 IC/IR 评估（向量化重写，2026-09-17）

    指标口径：
      - IC_mean / IC_std / IR / IC_pos_ratio / days：逐日横截面 RankIC（Spearman）
      - ls_spread / ls_t：逐日「多空价差」= 因子当日排名前 20% 与后 20% 的目标收益之差，
        再对日序列取均值与 t 值 —— **经济意义**指标；高 IR 不等于能赚钱
      - seg_ic / seg_same_sign：按时间三等分的 IC 均值 + 三段是否同号（防「只有一段显著」）
      - insufficient：days < MIN_DAYS_TRUST 时置 True，前端置灰

    实现：逐日 rank 向量化（groupby.rank(pct=True)），target 的 rank/z 全因子共享只算一次；
    各因子 rank 序列**不缓存**（df 已 ~2GB，缓存 102 列会撞内存墙）。

    与旧实现（逐因子 groupby.apply + spearman）严格等价，两个易错点已处理：
      1. ddof 校正：末尾乘 n/(n-1)（漏掉会系统性低估 |IC|，n=31 时可达 3%）
      2. 排名宇宙：因子秩只在「因子与 target 同时非空」的横截面内计算（旧实现先 dropna
         再排序）。若把「因子有值但 target 缺失」的行也算进排名，会多占名次、拉偏 pct 间距，
         在被排除前就污染了系数 —— 实测末端交易日（含停牌股）单日 IC 可差 2.7e-4。

    ⚠️ 已知设计取舍：多空分桶用 pct-rank 与 >=/<= 比较，top 桶取 n-ceil(0.8n)+1 只、
    bot 桶取 floor(0.2n) 只，两者可能相差 1 只（量化取整所致，影响 < 1/n）。
    """
    if features is None:
        features = ALL_FEATURES
    if df is None:
        df = prepare_training_data(features=features)
    results = []

    date_s = df["date"]
    gb = df.groupby("date")
    tgt = df["target"]

    # target 逐日 pct rank + 标准化（所有因子共享，只算一次）
    tgt_rank = gb["target"].rank(pct=True)
    _tr = tgt_rank.groupby(date_s)
    tgt_z = (tgt_rank - _tr.transform("mean")) / _tr.transform("std").replace(0, np.nan)

    # 因子秩只在「target 非空」的横截面内计算，与旧实现（先 dropna 再排序）口径一致
    _valid = tgt_rank.notna()

    for f in features:
        if f not in df.columns:
            continue
        # 逐日 pct rank → 日内标准化（标准化秩的乘积日均值 = Spearman IC）
        rk = df[f].where(_valid).groupby(date_s).rank(pct=True)
        _rr = rk.groupby(date_s)
        f_z = (rk - _rr.transform("mean")) / _rr.transform("std").replace(0, np.nan)

        # 有效 IC 日 = 当日因子与 target 同时非空的标的数 > MIN_STOCKS_PER_DAY
        valid_n = (rk.notna() & tgt_rank.notna()).groupby(date_s).sum()
        ok_days = valid_n.index[valid_n > MIN_STOCKS_PER_DAY]
        if len(ok_days) == 0:
            continue

        # Spearman IC = 标准化秩乘积的日内均值 × n/(n-1)
        # （f_z/tgt_z 用 ddof=1 标准化；而 Spearman = ddof=1 的 Pearson，两者差 n/(n-1)）
        # 不校正会系统性低估 |IC|：n=5000 时误差 0.02%，n=31 时高达 3%
        prod = (f_z * tgt_z).groupby(date_s).mean().reindex(ok_days)
        n_i = valid_n.reindex(ok_days)          # 当日交叠样本数（复用，零额外开销）
        daily_ics = (prod * n_i / (n_i - 1)).dropna()
        if len(daily_ics) < 5:
            continue
        ic_mean = float(daily_ics.mean())
        ic_std = float(daily_ics.std())
        if np.isnan(ic_mean) or np.isnan(ic_std):
            continue
        ir = ic_mean / ic_std if ic_std > 0 else 0.0
        ic_pos = float((daily_ics > 0).mean())

        # ── 多空价差（经济意义）──
        hi = tgt.where(rk >= 1.0 - LS_QUANTILE).groupby(date_s).mean()
        lo = tgt.where(rk <= LS_QUANTILE).groupby(date_s).mean()
        spread = (hi - lo).reindex(ok_days).dropna()
        if len(spread) > 1 and float(spread.std()) > 0:
            ls_mean = float(spread.mean())
            ls_t = float(ls_mean / spread.std() * np.sqrt(len(spread)))
        else:
            ls_mean, ls_t = None, None

        # ── 分段稳健性（时间三等分）──
        seg_ic = [round(float(np.mean(p)), 6) if len(p) else None
                  for p in np.array_split(daily_ics.values, 3)]
        _vals = [v for v in seg_ic if v is not None]
        seg_same = bool(len({1 if v > 0 else -1 for v in _vals}) == 1) if _vals else None

        results.append({
            "factor": str(f),
            "label": FACTOR_META.get(f, {}).get("label", f),
            "category": FACTOR_META.get(f, {}).get("cat", ""),
            "IC_mean": round(ic_mean, 6),
            "IC_std": round(ic_std, 6),
            "IR": round(float(ir), 4),
            "IC_pos_ratio": round(ic_pos, 4),
            "days": int(len(daily_ics)),
            "insufficient": bool(len(daily_ics) < MIN_DAYS_TRUST),
            "ls_spread": None if ls_mean is None else round(ls_mean, 6),
            "ls_t": None if ls_t is None else round(ls_t, 4),
            "seg_ic": seg_ic,
            "seg_same_sign": seg_same,
        })
    results.sort(key=lambda x: abs(x["IR"]), reverse=True)
    with open(FACTOR_EVAL, "w") as fp:
        json.dump({"results": results, "updated": datetime.now().isoformat()}, fp, ensure_ascii=False)
    return results


def train_model(df: pd.DataFrame = None, days: int = 730, valid_pct: int = 20,
                target_horizon: int = 5, features: list = None,
                lr: float = 0.05, leaves: int = 63, estimators: int = 200,
                save_model: bool = True, job_id: str = None) -> dict:
    import lightgbm as lgb
    if features is None:
        features = ALL_FEATURES

    if df is None:
        df = prepare_training_data(days=days, target_horizon=target_horizon, features=features)

    TRAIN_STATUS["running"] = True
    TRAIN_STATUS["started"] = datetime.now().isoformat()
    TRAIN_STATUS["message"] = "训练中..."

    # 去掉 target 为 NaN 的行（最新几天没有未来收益，无法训练但可用于预测）
    df = df.dropna(subset=["target"])

    # ── 标签：每日截面 rank 标准化（rank→z）──
    # 剥离「市场整体涨跌(regime)」与「尾部极端收益」，让训练目标与 Top-N 排序用法一致。
    # A/B 实测(730d/5d 同一验证窗)：原样 RankIC +0.0428 → rank-z +0.0976 (2.3x)
    y_raw = df["target"].copy()  # 原始未来收益，仅用于 val_IC 汇报口径
    _rk = df.groupby("date")["target"].rank(pct=True)
    df["target"] = ((_rk - _rk.groupby(df["date"]).transform("mean")) /
                    (_rk.groupby(df["date"]).transform("std") + 1e-12))

    # 时间分割
    all_dates = sorted(df.date.unique())
    split_n = max(1, int(len(all_dates) * valid_pct / 100))
    split_date = all_dates[-split_n]
    train_df = df[df.date < split_date]
    valid_df = df[df.date >= split_date]

    X_train = train_df[features].values
    y_train = train_df["target"].values
    X_valid = valid_df[features].values
    y_valid = valid_df["target"].values

    print(f"[ML] 训练: {len(train_df)}行 | 验证: {len(valid_df)}行")

    evals_result = {}
    # 根据特征数自适应调整：特征少时降leaves防过拟合
    n_feat = len(features) if features else len(ALL_FEATURES)
    # 注：特征数<10时 best_iteration_=1 是正常的（第1棵树即收敛）
    actual_leaves = min(leaves, max(15, n_feat * 3))
    actual_est = min(estimators, max(50, n_feat * 8))
    model = lgb.LGBMRegressor(
        objective="regression",
        n_estimators=actual_est,
        learning_rate=lr,
        num_leaves=actual_leaves,
        min_data_in_leaf=max(500, int(len(train_df) / 5000)),
        min_gain_to_split=0.01,
        reg_alpha=0.1,
        reg_lambda=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        subsample_freq=1,
        random_state=42,
        n_jobs=2,
        verbose=-1,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_valid, y_valid)],
        eval_names=["valid"],
        eval_metric="l2",
        callbacks=[lgb.early_stopping(20), lgb.record_evaluation(evals_result)],
    )
    # 诊断: 若 best_iter 过小，打印验证 loss 曲线
    if model.best_iteration_ <= 3:
        vals = evals_result.get("valid", {}).get("l2", [])
        if vals:
            print(f"[ML] ⚠️ best_iter={model.best_iteration_} | val_l2: {round(min(vals),6)}~{round(max(vals),6)} ({len(vals)}轮)")

    preds = model.predict(X_valid)
    from scipy.stats import spearmanr
    # val_IC 用原始未来收益口径（与历史实验可比）；MSE 为训练损失口径(rank-z)
    ic, ic_p = spearmanr(preds, y_raw.loc[valid_df.index].values)
    mse = float(((preds - y_valid) ** 2).mean())

    importance = sorted(zip(features, model.feature_importances_), key=lambda x: -x[1])
    imp_sum = sum(v for _, v in importance) or 1
    # 归一化到总和100%
    importance_norm = [[f, round(v / imp_sum * 100, 1)] for f, v in importance]

    if save_model:
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)

    if job_id is None:
        job_id = f"lgb_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    meta = {
        "job_id": job_id,
        "trained_at": datetime.now().isoformat(),
        "n_features": len(features),
        "features": features,
        "train_samples": int(len(train_df)),
        "valid_samples": int(len(valid_df)),
        "n_stocks": int(df.code.nunique()),
        "train_dates": str(train_df.date.min()) + " ~ " + str(train_df.date.max()),
        "validate_dates": str(valid_df.date.min()) + " ~ " + str(valid_df.date.max()),
        "val_IC": _finite(ic, 6),
        "val_IC_p": _finite(ic_p, 6),
        "val_MSE": _finite(mse, 4),
        "target_mode": "rank_z_daily",  # 标签=每日截面 rank 标准化
        "best_iteration": int(model.best_iteration_),
        "target_horizon": target_horizon,
        "learning_rate": lr,
        "num_leaves": leaves,
        "n_estimators": estimators,
        "importance_top5": _sanitize(importance_norm[:5]),
    }
    with open(TRAIN_META, "w") as fp:
        json.dump(meta, fp, ensure_ascii=False, indent=2)

    # 追加到历史
    history = []
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH) as f:
            history = json.load(f)
    history.insert(0, meta)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"[ML] ✅ 完成 | IC={ic:.4f} | MSE={mse:.4f} | iter={model.best_iteration_}")
    return meta


def predict_top_n(n: int = 30, features: list = None, precomputed_df: pd.DataFrame = None) -> dict:
    """用最新模型预测全市场 Top-N
    
    若 precomputed_df 传入（训练后复用），跳过全部数据加载和因子计算，仅做推理。
    """
    if features is None:
        features = ALL_FEATURES

    if not os.path.exists(MODEL_PATH):
        return {"predictions": [], "note": "模型不存在，请先训练"}

    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)

    if precomputed_df is not None:
        # 复用训练阶段已计算好的因子 DataFrame，只取最新日期行
        latest = precomputed_df["date"].max()
        df_latest = precomputed_df[precomputed_df["date"] == latest].copy()
        conn = get_conn()
        codes = df_latest["code"].unique().tolist()
        si_names = pd.read_sql("SELECT code, name FROM stock_info WHERE code IN ({})".format(
            ",".join(["?"] * len(codes))), conn, params=codes
        )
        conn.close()
        df_latest = df_latest.merge(si_names, on="code", how="left")
    else:
        # 独立计算模式
        conn = get_conn()
        latest = pd.read_sql("SELECT MAX(date) as d FROM stock_daily", conn).iloc[0, 0]
        window_days = 180
        start_d = (datetime.strptime(latest, "%Y-%m-%d") - timedelta(days=window_days)).strftime("%Y-%m-%d")
        print(f"[ML] 预测历史数据: {start_d} ~ {latest}")

        df = pd.read_sql("""
            SELECT code, date, open, high, low, close, volume, amount, turnover
            FROM stock_daily WHERE date >= ?
            ORDER BY code, date
        """, conn, params=(start_d,))
        si_names = pd.read_sql("SELECT DISTINCT code, name FROM stock_daily WHERE code != ''", conn)
        conn.close()

        df = df.sort_values(["code", "date"]).reset_index(drop=True)
        # 用训练数据相同的公式计算因子（单次调用，仅最新日期）
        def _compute(grp):
            grp = grp.copy()
            c = grp["close"].astype(float); o = grp["open"].astype(float)
            h = grp["high"].astype(float); l = grp["low"].astype(float)
            v = grp["volume"].astype(float); amt = grp["amount"].astype(float)
            eps = 1e-12
            grp["KMID"] = (o + c) / 2
            grp["KMID2"] = (c - o) / (h - l + eps)
            grp["KLEN"] = (h - l) / o.replace(0, np.nan)
            grp["KLOW"] = (c - l) / (h - l + eps)
            grp["KSFT"] = o.pct_change(); grp["KSFT2"] = (o - c.shift(1)) / c.shift(1).replace(0, np.nan)
            grp["QTLU5"] = (c - l) / (h - l + eps)
            ret = c.pct_change(); vol_ret = v.pct_change()
            for N in [5, 10, 20, 30, 60]:
                sN = str(N)
                grp[f"Rtn{sN}"] = c.pct_change(N)
                grp[f"ROC{sN}"] = c.shift(N) / c - 1
                grp[f"REVS{sN}"] = (h - c.shift(N)) / c.shift(N).replace(0, np.nan)
                grp[f"VSUE{sN}"] = v.pct_change(N)
                grp[f"MA{sN}"] = c.rolling(N).mean() / c.replace(0, np.nan)
                grp[f"STD{sN}"] = c.rolling(N).std() / c.replace(0, np.nan)
                grp[f"HIGH{sN}"] = h.rolling(N).max() / c.replace(0, np.nan)
                grp[f"LOW{sN}"] = l.rolling(N).min() / c.replace(0, np.nan)
                grp[f"MAX{sN}"] = h.rolling(N).max() / l.rolling(N).min().replace(0, np.nan)
                grp[f"SUMP{sN}"] = (c / o - 1).rolling(N).sum()
                if N <= 20: grp[f"SUMV{sN}"] = vol_ret.rolling(N).sum()
                grp[f"CORR{sN}"] = c.rolling(N).corr(np.log1p(v))
                grp[f"CORD{sN}"] = ret.rolling(N).corr(np.log1p(vol_ret))
                if N > 5: grp[f"QTLU{sN}"] = (c - l.rolling(N).min()) / (h.rolling(N).max() - l.rolling(N).min() + eps)
            intr = c / o - 1
            for N in [5, 10, 20]:
                sN = str(N)
                grp[f"MA{sN}V"] = v.rolling(N).mean() / (v + eps)
                grp[f"WVMA{sN}"] = intr.rolling(N).std()
                grp[f"VSTD{sN}"] = vol_ret.rolling(N).std()
                grp[f"RtnVol{sN}"] = c.pct_change(N) / (ret.rolling(N).std() + eps)
            up = (c > o).astype(float); dn = (c < o).astype(float); inc = (c > c.shift(1)).astype(float)
            for N in [5, 10, 20]:
                sN = str(N)
                grp[f"IMXD{sN}"] = up.rolling(N).mean()
                grp[f"CNTP{sN}"] = up.rolling(N).sum()
                grp[f"CNTN{sN}"] = dn.rolling(N).sum()
                grp[f"CNTD{sN}"] = inc.rolling(N).sum()
            for N in [5, 10, 20, 30]:
                grp[f"AMT{N}"] = np.log1p(amt.rolling(N).mean().fillna(0))
            return grp
        df = df.groupby("code", group_keys=False).apply(_compute).reset_index(drop=True)
        df_latest = df[df["date"] == latest].copy()
        df_latest = df_latest.merge(si_names, on="code", how="left")

    valid = df_latest.dropna(subset=[c for c in features if c in df_latest.columns])
    valid = valid[valid["close"] > 0]
    if valid.empty:
        return {"error": "无有效样本", "predictions": []}

    X = valid[features].values
    preds = model.predict(X)
    valid = valid.copy()
    valid["pred_return"] = preds.round(4)

    top = valid.nlargest(min(n, len(valid)), "pred_return")
    results = []
    for _, row in top.iterrows():
        results.append({
            "code": row["code"],
            "name": row.get("name", ""),
            "close": round(float(row["close"]), 2),
            "pred_return_5d": float(row["pred_return"]),
            "rtn20": round(float(row.get("Rtn20", 0)), 4) if pd.notna(row.get("Rtn20")) else None,
            "ma20_dev": round(float(row.get("MA20", 0) - 1), 4) if pd.notna(row.get("MA20")) else None,
        })

    payload = {"date": latest, "predictions": results}
    with open(PREDICTIONS, "w") as fp:
        json.dump(payload, fp, ensure_ascii=False)
    return payload


def train_async(days: int = 730, valid_pct: int = 20, target_horizon: int = 5,
                features: list = None, lr: float = 0.05, leaves: int = 63,
                estimators: int = 200) -> str:
    """在独立后台线程启动训练，资源受限"""
    job_id = f"lgb_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    TRAIN_STATUS["job_id"] = job_id
    TRAIN_STATUS["running"] = True
    TRAIN_STATUS["message"] = "数据准备中..."
    TRAIN_STATUS["started"] = datetime.now().isoformat()

    def _run():
        # 降低本线程优先级
        try:
            os.nice(10)
        except Exception:
            pass
        try:
            TRAIN_STATUS["progress_pct"] = 5
            df = prepare_training_data(days=days, target_horizon=target_horizon, features=features)
            TRAIN_STATUS["progress_pct"] = 30
            TRAIN_STATUS["message"] = f"数据就绪({len(df)}行)，训练中..."
            meta = train_model(df=df, days=days, valid_pct=valid_pct,
                              target_horizon=target_horizon, features=features,
                              lr=lr, leaves=leaves, estimators=estimators,
                              job_id=job_id)
            TRAIN_STATUS["progress_pct"] = 80
            TRAIN_STATUS["message"] = "IC评估中..."
            evaluate_factor_ic(df=df, features=features)
            # 保存per-job IC拷贝用于历史查阅
            job_eval = os.path.join(ML_DIR, f"factor_eval_{job_id}.json")
            if os.path.exists(FACTOR_EVAL):
                import shutil
                shutil.copy(FACTOR_EVAL, job_eval)
            TRAIN_STATUS["progress_pct"] = 90
            TRAIN_STATUS["message"] = "预测中..."
            predict_top_n(n=50, features=features, precomputed_df=df)
            # 保存per-job 预测拷贝
            job_pred = os.path.join(ML_DIR, f"predictions_{job_id}.json")
            if os.path.exists(PREDICTIONS):
                import shutil
                shutil.copy(PREDICTIONS, job_pred)
            TRAIN_STATUS["progress_pct"] = 100
            TRAIN_STATUS["message"] = "训练完成"
            TRAIN_STATUS["running"] = False
            return meta
        except Exception as e:
            TRAIN_STATUS["running"] = False
            TRAIN_STATUS["message"] = f"失败: {str(e)}"
            raise

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return job_id


def get_train_status() -> dict:
    return dict(TRAIN_STATUS)


def get_factor_eval(job_id: str = None) -> dict:
    path = os.path.join(ML_DIR, f"factor_eval_{job_id}.json") if job_id else FACTOR_EVAL
    if os.path.exists(path):
        with open(path) as f:
            return _sanitize(json.load(f))
    return {"results": [], "note": "尚未评估，请先训练"}


def get_predictions(n: int = 30, job_id: str = None) -> dict:
    path = os.path.join(ML_DIR, f"predictions_{job_id}.json") if job_id else PREDICTIONS
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        data["predictions"] = _sanitize(data["predictions"][:n])
        return _sanitize(data)
    return {"predictions": [], "note": "尚未预测，请先训练"}


def get_history() -> list:
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH) as f:
            return _sanitize(json.load(f))
    return []


# ═══════════════════════════════════════════════════════════
#  智能选因子 — IC 预筛 + 多窗口稳定性 + 前向逐步选择
# ═══════════════════════════════════════════════════════════

FS_RESULT_PATH = os.path.join(ML_DIR, "factor_select_result.json")
FACTOR_SELECT_STATUS = {"running": False, "job_id": None, "stage": "",
                         "progress_pct": 0, "message": "", "started": None}


def screen_factors(eval_results: list = None,
                   min_ir_abs: float = 0.15,
                   max_per_category: int = 5) -> dict:
    """阶段1: IC 预筛 — 从 102 个因子中过滤出 ~30 个

    过滤:
      1. |IR| < min_ir_abs \u2192 淘汰
      2. IC>0% 在 45%~55% \u2192 淘汰（方向不固定）
      3. 同分类内 IR 差距<30% 且方向一致 \u2192 只留 |IR| 最高的
      4. 每分类最多 max_per_category 个
    """
    if eval_results is None:
        data = get_factor_eval()
        eval_results = data.get("results", [])
    if not eval_results:
        return {"error": "请先训练一次以生成 IC 评估数据", "passed": [], "dropped": []}

    dropped = []; passed = []
    # NaN/inf 归一化：小样本下 IC/IR 常为 NaN，直接参与比较会静默丢光因子
    eval_results = [
        dict(f,
             IR=(_finite(f.get("IR")) or 0.0),
             IC_mean=(_finite(f.get("IC_mean")) or 0.0),
             IC_pos_ratio=(_finite(f.get("IC_pos_ratio")) if _finite(f.get("IC_pos_ratio")) is not None else 0.5))
        for f in eval_results
    ]
    for f in eval_results:
        ir = abs(f["IR"]); ic_pos = f.get("IC_pos_ratio", 0.5); name = f["factor"]
        if ir < min_ir_abs:
            dropped.append({"factor": name, "reason": f"|IR|={ir:.3f}<{min_ir_abs}", "ir": ir}); continue
        if 0.45 < ic_pos < 0.55:
            dropped.append({"factor": name, "reason": f"IC>0%=({ic_pos*100:.0f}%) 方向不稳定", "ir": ir}); continue
        passed.append(f)

    by_cat = {}
    for f in passed:
        by_cat.setdefault(f.get("category", "其他"), []).append(f)

    deduped = []; corr_dropped = []
    for cat, factors in sorted(by_cat.items()):
        if len(factors) <= 1:
            deduped.extend(factors); continue
        factors.sort(key=lambda x: abs(x["IR"]), reverse=True)
        kept = []
        for f in factors:
            redundant = False
            for k in kept:
                ir_diff = abs(abs(f["IR"]) - abs(k["IR"])) / max(abs(k["IR"]), 0.01)
                same_sign = (f["IC_mean"] * k["IC_mean"]) > 0
                if ir_diff < 0.3 and same_sign:
                    if abs(f["IR"]) > abs(k["IR"]):
                        corr_dropped.append({"factor": k["factor"], "reason": f"与{f['factor']}高相关(同'{cat}')", "ir": abs(k["IR"])})
                        kept.remove(k); kept.append(f)
                    else:
                        corr_dropped.append({"factor": f["factor"], "reason": f"与{k['factor']}高相关(同'{cat}')", "ir": abs(f["IR"])})
                    redundant = True; break
            if not redundant:
                kept.append(f)
        if len(kept) > max_per_category:
            for f in kept[max_per_category:]:
                corr_dropped.append({"factor": f["factor"], "reason": f"分类'{cat}'超{max_per_category}个限制", "ir": abs(f["IR"])})
            kept = kept[:max_per_category]
        deduped.extend(kept)

    passed_names = [f["factor"] for f in deduped]

    # 小样本 / 合成数据下，IC/IR 可能全为 NaN → 阈值筛选会把因子全砍光。
    # 此时退化为「按 |IR| 取前 N」，保证链路可跑通，并在结果里标注。
    fallback_note = None
    if not deduped and eval_results:
        fallback_note = (f"IR 阈值（|IR|≥{min_ir_abs}）无因子通过，已退化为按 |IR| 取前 {max_per_category} 个/类"
                         "（小样本或合成数据下 IC 常为 NaN，属正常现象）")
        relaxed = []
        for cat in sorted({f.get("category", "未分类") for f in eval_results}):
            group = [f for f in eval_results if f.get("category", "未分类") == cat]
            group.sort(key=lambda x: abs(x.get("IR") or 0.0), reverse=True)
            relaxed.extend(group[:max_per_category])
        deduped = relaxed
        passed_names = [f["factor"] for f in deduped]

    result = {
        "passed": deduped, "passed_names": passed_names, "n_passed": len(deduped),
        "dropped": dropped + corr_dropped, "n_dropped": len(dropped) + len(corr_dropped),
        "n_total": len(eval_results),
    }
    if fallback_note:
        result["note"] = fallback_note
    return result


def _get_db_date_range() -> tuple:
    conn = get_conn()
    r = conn.execute("SELECT MIN(date), MAX(date) FROM stock_daily").fetchone()
    conn.close()
    return r[0], r[1]


def build_training_windows(n_windows: int = 3) -> list:
    """根据 DB 日期范围构建滚动窗口 (expanding window, 步长6月)"""
    min_d, max_d = _get_db_date_range()
    if not min_d or not max_d:
        return []
    db_start = datetime.strptime(min_d, "%Y-%m-%d")
    db_end = datetime.strptime(max_d, "%Y-%m-%d")
    total_days = (db_end - db_start).days
    if total_days < 500:
        split = db_start + timedelta(days=int(total_days * 0.8))
        return [{"win": 1, "train_start": min_d, "train_end": split.strftime("%Y-%m-%d"),
                 "valid_start": split.strftime("%Y-%m-%d"), "valid_end": max_d,
                 "label": f"{min_d} ~ {max_d}"}]

    windows = []
    base_end = db_end
    for i in range(n_windows):
        mo = base_end.month - i * 6
        yr = base_end.year + (mo - 1) // 12
        mo = ((mo - 1) % 12) + 1
        valid_end = datetime(yr, mo, min(base_end.day, 28))
        if (valid_end - db_start).days < 365:
            break
        mo = valid_end.month - 4
        yr = valid_end.year + (mo - 1) // 12
        mo = ((mo - 1) % 12) + 1
        valid_start = datetime(yr, mo, min(valid_end.day, 28))
        train_end = valid_start - timedelta(days=1)
        windows.append({
            "win": i + 1,
            "train_start": db_start.strftime("%Y-%m-%d"),
            "train_end": train_end.strftime("%Y-%m-%d"),
            "valid_start": valid_start.strftime("%Y-%m-%d"),
            "valid_end": valid_end.strftime("%Y-%m-%d"),
            "label": f"T={db_start.strftime('%y%m')}~{train_end.strftime('%y%m')} V={valid_start.strftime('%y%m')}~{valid_end.strftime('%y%m')}",
        })
    return windows or [{"win": 1, "train_start": min_d, "train_end": "2026-01-01",
                        "valid_start": "2026-01-01", "valid_end": max_d,
                        "label": f"{min_d} ~ {max_d}"}]


def _train_single_window(window: dict, features: list, th: int, lr: float, leaves: int, est: int) -> dict:
    """单窗口训练"""
    conn = get_conn()
    df = pd.read_sql("SELECT code, date, open, high, low, close, volume, amount, turnover FROM stock_daily WHERE date >= ? AND date <= ? ORDER BY code, date",
                     conn, params=(window["train_start"], window["valid_end"]))
    conn.close()
    if df.empty:
        return {"win": window["win"], "error": "窗口无数据"}
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    from services.ml_service import prepare_training_data
    # 用 prepare_training_data 统一计算因子
    days_needed = (datetime.strptime(window["valid_end"], "%Y-%m-%d") - datetime.strptime(window["train_start"], "%Y-%m-%d")).days
    try:
        df_clean = prepare_training_data(days=max(days_needed, 365), target_horizon=th, features=features)
    except Exception:
        return {"win": window["win"], "label": window["label"], "error": "数据处理失败"}

    df_clean = df_clean.dropna(subset=["target"])
    split_date = window["valid_start"]
    train_df = df_clean[df_clean.date < split_date]
    valid_df = df_clean[(df_clean.date >= split_date) & (df_clean.date <= window["valid_end"])]

    if len(train_df) < 1000 or len(valid_df) < 100:
        return {"win": window["win"], "label": window["label"], "error": f"样本不足(T={len(train_df)},V={len(valid_df)})"}

    import lightgbm as lgb
    from scipy.stats import spearmanr
    Xt = train_df[features].values; yt = train_df["target"].values
    Xv = valid_df[features].values; yv = valid_df["target"].values

    model = lgb.LGBMRegressor(objective="regression", n_estimators=est, learning_rate=lr,
                               num_leaves=leaves, subsample=0.8, colsample_bytree=0.8,
                               random_state=42, n_jobs=2, verbose=-1)
    model.fit(Xt, yt, eval_set=[(Xv, yv)], eval_metric="l2", callbacks=[lgb.early_stopping(20)])
    preds = model.predict(Xv)
    ic, _ = spearmanr(preds, yv)
    imp = sorted(zip(features, model.feature_importances_), key=lambda x: -x[1])
    s = sum(v for _, v in imp) or 1
    imp_norm = {fn: round(v / s * 100, 1) for fn, v in imp}
    return {"win": window["win"], "label": window["label"], "val_IC": round(float(ic), 6),
            "train_samples": len(train_df), "valid_samples": len(valid_df),
            "best_iteration": int(model.best_iteration_), "importance": imp_norm,
            "top10": [fn for fn, _ in imp[:10]]}


def run_stability_training(features: list, windows: list, th: int = 10,
                           lr: float = 0.03, leaves: int = 63, est: int = 300) -> dict:
    """阶段2: 多窗口稳定性"""
    FACTOR_SELECT_STATUS["stage"] = "stability"
    wr = []
    for i, w in enumerate(windows):
        FACTOR_SELECT_STATUS["progress_pct"] = int(20 + (i / len(windows)) * 40)
        FACTOR_SELECT_STATUS["message"] = f"窗口 {i+1}/{len(windows)}: {w['label']}"
        wr.append(_train_single_window(w, features, th, lr, leaves, est))
        time.sleep(0.5)

    valid = [r for r in wr if "error" not in r]
    st = {}
    for f in features:
        t10 = sum(1 for r in valid if f in r.get("top10", []))
        imps = [r.get("importance", {}).get(f, 0) for r in valid]
        avg_imp = sum(imps) / max(len(imps), 1)
        ranks = []
        for r in valid:
            imp = sorted(r.get("importance", {}).items(), key=lambda x: -x[1])
            found = next((i+1 for i, (fn, _) in enumerate(imp) if fn == f), len(features))
            ranks.append(found)
        avg_rank = sum(ranks) / max(len(ranks), 1)
        rank_std = float(np.std(ranks)) if len(ranks) > 1 else 0
        hit = t10 / max(len(valid), 1)
        max_imp = max(max(r.get("importance", {}).values()) for r in valid) if valid else 1
        score = round(hit * 0.4 + max(0, 1 - rank_std / max(len(features), 1)) * 0.3 + min(avg_imp / max(max_imp, 1), 1) * 0.3, 3)
        st[f] = {"hit_rate": round(hit, 2), "avg_importance": round(avg_imp, 1),
                 "avg_rank": round(avg_rank, 1), "rank_std": round(rank_std, 1), "score": score}

    sorted_st = sorted(st.items(), key=lambda x: -x[1]["score"])
    return {"window_results": wr, "n_windows": len(wr), "n_valid_windows": len(valid),
            "stability": {fn: v for fn, v in sorted_st}, "top15": [fn for fn, _ in sorted_st[:15]]}


def _train_with_subset(features: list, th: int, lr: float, leaves: int, est: int,
                       days: int = 1095, precomputed_df=None) -> float:
    """快速训练返回 val_IC。支持传入预计算的 df 以避免重复加载数据"""
    if precomputed_df is not None:
        df = precomputed_df.copy()
    else:
        df = prepare_training_data(days=days, target_horizon=th, features=features)
    df = df.dropna(subset=["target"])
    all_dates = sorted(df.date.unique())
    s = max(1, int(len(all_dates) * 0.2))
    split = all_dates[-s]
    tr = df[df.date < split]; va = df[df.date >= split]
    if len(va) < 100:
        return 0.0
    # 只取需要的特征列进行训练
    avail = [f for f in features if f in df.columns]
    import lightgbm as lgb
    from scipy.stats import spearmanr
    m = lgb.LGBMRegressor(objective="regression", n_estimators=est, learning_rate=lr,
                          num_leaves=leaves, subsample=0.8, colsample_bytree=0.8,
                          random_state=42, n_jobs=2, verbose=-1)
    m.fit(tr[avail].values.astype(float), tr["target"].values.astype(float),
          eval_set=[(va[avail].values.astype(float), va["target"].values.astype(float))],
          eval_metric="l2", callbacks=[lgb.early_stopping(20)])
    preds = m.predict(va[avail].values.astype(float))
    ic, _ = spearmanr(preds, va["target"].values)
    return float(ic)


def forward_select(candidates: list, stability: dict, th: int = 10, lr: float = 0.03,
                   leaves: int = 63, est: int = 300, top_n: int = 5,
                   min_ic_gain: float = 0.001, days: int = 1095) -> dict:
    """阶段3: 多样性前向逐步选择

    策略：
      1. 按分类分组 candidate，每分类取 score 最高的
      2. 初选 3 个不同分类最高分因子作为种子
      3. 种子基础上做 取3组合（同分类 ≤2），两层筛法选出 best_3
      4. 逐步加第 4、5 个因子（同分类 ≤2，增益 > 0）
    """
    FACTOR_SELECT_STATUS["stage"] = "forward"
    FACTOR_SELECT_STATUS["progress_pct"] = 60
    FACTOR_SELECT_STATUS["message"] = "前向选择: 准备数据..."

    df = prepare_training_data(days=days, target_horizon=th, features=candidates)

    # ── 1. 按分类分组 ──
    cat_groups = {}  # {cat: [(name, score), ...]}
    for fn in candidates:
        score = stability.get(fn, {}).get("score", 0)
        cat = FACTOR_META.get(fn, {}).get("cat", "其他")
        cat_groups.setdefault(cat, []).append((fn, score))
    for cat in cat_groups:
        cat_groups[cat].sort(key=lambda x: -x[1])

    # ── 2. 每分类 Top-1 作为基础候选池 ──
    base_pool = [(fn, s) for items in cat_groups.values() for fn, s in items[:1]]
    base_pool.sort(key=lambda x: -x[1])

    if len(base_pool) < 3:
        return {"error": f"分类不足3个(当前{len(base_pool)}),无法选出多样组合",
                "final_factors": [], "n_final": 0, "path": []}

    # ── 3. 种子: 前 3 个不同分类最高分因子 ──
    seed = [fn for fn, _ in base_pool[:3]]
    seed_ic = _train_with_subset(seed, th, lr, leaves, est, precomputed_df=df)

    FACTOR_SELECT_STATUS["message"] = f"前向选择: 种子={','.join(seed)} IC={seed_ic:.4f}"

    # ── 4. 两层筛法: 取3组合 枚举（同分类 ≤2） ──
    # 第一层: 按稳定性得分初筛
    combo_candidates = []
    # 只使用稳定性得分 Top-N 的因子来组合（限 12 个，平衡覆盖面和速度）
    # 从每个分类取 Top-2
    top_pool = []
    for cat, items in cat_groups.items():
        for fn, s in items[:2]:
            top_pool.append((fn, s, cat))
    top_pool.sort(key=lambda x: -x[1])
    top_pool = top_pool[:12]  # 最多12个因子

    # 生成所有满足"同分类 ≤2"的 3 因子组合
    n_pool = len(top_pool)
    for i in range(n_pool):
        for j in range(i + 1, n_pool):
            for k in range(j + 1, n_pool):
                combo = [top_pool[i], top_pool[j], top_pool[k]]
                cat_counts = {}
                for _, _, c in combo:
                    cat_counts[c] = cat_counts.get(c, 0) + 1
                if any(v > 2 for v in cat_counts.values()):
                    continue
                avg_score = sum(s for _, s, _ in combo) / 3
                fn_list = [fn for fn, _, _ in combo]
                combo_candidates.append((fn_list, avg_score))

    # 按得分排序 + 保底 5 个跨分类差异最大的
    combo_candidates.sort(key=lambda x: -x[1])
    # 保底：选分类距离最远的 3 个分类各取 Top-1（如果还没有）
    if len(cat_groups) >= 3:
        cat_by_score = sorted(cat_groups.keys(), key=lambda c: -cat_groups[c][0][1])
        # 高分段（1st, mid, last）
        idx_high = cat_by_score[0]
        idx_mid = cat_by_score[len(cat_by_score) // 2]
        idx_low = cat_by_score[-1]
        diverse_combo = [cat_groups[idx_high][0][0], cat_groups[idx_mid][0][0], cat_groups[idx_low][0][0]]
        # 确保 diverse combo 在列表中
        found = any(set(c[0]) == set(diverse_combo) for c in combo_candidates)
        if not found:
            combo_candidates.insert(0, (diverse_combo, 0))

    # 取 Top 30 做第二层真训练
    top_combos = combo_candidates[:30]

    # ── 第二层: 真训练 ──
    trained_combos = []
    n_combos = len(top_combos)
    for idx, (comb, _) in enumerate(top_combos):
        pct = int(60 + (idx / max(n_combos, 1)) * 20)
        FACTOR_SELECT_STATUS["progress_pct"] = pct
        FACTOR_SELECT_STATUS["message"] = f"验证组合: {idx+1}/{n_combos} {'+'.join(comb)}"
        ic = _train_with_subset(comb, th, lr, leaves, est, precomputed_df=df)
        trained_combos.append((comb, ic))

    trained_combos.sort(key=lambda x: -x[1])
    best_3, best_ic = trained_combos[0]

    path = [{"step": "种子", "factors": seed, "val_IC": round(seed_ic, 6)}]
    path.append({"step": "最优3", "factors": best_3, "val_IC": round(best_ic, 6),
                 "n_tested": n_combos})

    # ── 5. 逐步加第 4、5 个因子 ──
    selected = list(best_3)
    cat_count = {}
    for fn in selected:
        c = FACTOR_META.get(fn, {}).get("cat", "其他")
        cat_count[c] = cat_count.get(c, 0) + 1

    remaining = [fn for fn in candidates if fn not in selected]

    for step_n in [4, 5]:
        if step_n > top_n or not remaining:
            break
        best_gain = -999; best_fn = None; best_full_ic = best_ic
        tested = 0
        for fn in remaining:
            c = FACTOR_META.get(fn, {}).get("cat", "其他")
            if cat_count.get(c, 0) >= 2:
                continue  # 同分类 ≤2 约束
            ic = _train_with_subset(selected + [fn], th, lr, leaves, est, precomputed_df=df)
            gain = ic - best_ic
            tested += 1
            if gain > best_gain:
                best_gain = gain; best_fn = fn; best_full_ic = ic
        FACTOR_SELECT_STATUS["progress_pct"] = int(80 + (step_n - 3) * 10)
        FACTOR_SELECT_STATUS["message"] = f"加第{step_n}因子: 测试{tested}个, 最优{best_fn or '无'} gain={best_gain:.4f}"
        if best_fn and best_gain > 0:
            selected.append(best_fn)
            cat_count[FACTOR_META.get(best_fn, {}).get("cat", "其他")] = cat_count.get(FACTOR_META.get(best_fn, {}).get("cat", "其他"), 0) + 1
            best_ic = best_full_ic
            path.append({"step": f"加第{step_n}", "added": best_fn, "n_selected": len(selected),
                         "val_IC": round(best_ic, 6), "gain": round(best_gain, 6),
                         "tested": tested})
        else:
            path.append({"step": f"加第{step_n}", "result": "无正向增益", "tested": tested})

    return {"final_factors": selected, "n_final": len(selected),
            "final_val_IC": round(best_ic, 6),
            "baseline_val_IC": round(seed_ic, 6),
            "seed": seed, "best_3": best_3,
            "n_combos_tested": n_combos, "path": path}


def run_factor_selection(config: dict) -> str:
    """启动智能选因子全流程"""
    job_id = f"fs_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    FACTOR_SELECT_STATUS.update({"running": True, "job_id": job_id, "stage": "screen",
                                  "progress_pct": 0, "message": "初始化...", "started": datetime.now().isoformat()})

    def _run():
        try:
            os.nice(10)
        except Exception:
            pass
        result = {"job_id": job_id, "status": "running", "stages": {}}
        try:
            screen_cfg = config.get("screener", {})
            data = get_factor_eval()
            eval_results = data.get("results", [])
            th = config.get("target_horizon", 10)
            if not eval_results or len(eval_results) < 20:
                FACTOR_SELECT_STATUS["message"] = "IC预筛: 计算全量因子..."
                FACTOR_SELECT_STATUS["progress_pct"] = 5
                df = prepare_training_data(days=730, target_horizon=th, features=ALL_FEATURES)
                eval_results = evaluate_factor_ic(df=df, features=ALL_FEATURES)
            screened = screen_factors(eval_results, min_ir_abs=screen_cfg.get("min_ir_abs", 0.15),
                                       max_per_category=screen_cfg.get("max_per_category", 5))
            result["stages"]["screen"] = screened
            FACTOR_SELECT_STATUS["progress_pct"] = 20
            if not screened.get("passed_names"):
                result["status"] = "failed"
                result["error"] = (
                    "无因子通过 IC 预筛：可能是样本量太小（默认样例库仅 8 只股票，"
                    "截面 IC 无法计算）或行情库本身缺少足够标的。\n"
                    "建议：用 `examples/make_sample_data.py --stocks 30` 生成更大的样例库，"
                    "或接入自己的行情库。"
                )
                raise RuntimeError("no factors pass IC pre-screen")
            stab_cfg = config.get("stability", {})
            windows = build_training_windows(n_windows=stab_cfg.get("n_windows", 3))
            stability = run_stability_training(screened["passed_names"], windows, th=th,
                                                lr=config.get("lr", 0.03),
                                                leaves=config.get("leaves", 63),
                                                est=config.get("estimators", 300))
            result["stages"]["stability"] = stability
            FACTOR_SELECT_STATUS["progress_pct"] = 60
            fs_cfg = config.get("forward_select", {})
            candidates = stability.get("top15", screened["passed_names"])
            forward = forward_select(candidates, stability=stability.get("stability", {}),
                                     th=th, lr=config.get("lr", 0.03),
                                     leaves=config.get("leaves", 63),
                                     est=config.get("estimators", 300),
                                     top_n=fs_cfg.get("top_n", 5),
                                     min_ic_gain=fs_cfg.get("min_ic_gain", 0.001))
            result["stages"]["forward"] = forward
            result["status"] = "done"
            result["recommendation"] = f"建议: {', '.join(forward['final_factors'])}"
            FACTOR_SELECT_STATUS["progress_pct"] = 100
            FACTOR_SELECT_STATUS["message"] = "完成!"
        except Exception as e:
            import traceback
            result["status"] = "failed"
            result["error"] = str(e)
            result["traceback"] = traceback.format_exc()
            FACTOR_SELECT_STATUS["message"] = f"失败: {str(e)[:80]}"
        finally:
            FACTOR_SELECT_STATUS["running"] = False
            with open(FS_RESULT_PATH, "w") as fp:
                json.dump(result, fp, ensure_ascii=False, indent=2)
            # 保存per-job结果，供历史查阅
            job_result_path = os.path.join(ML_DIR, f"factor_select_result_{job_id}.json")
            with open(job_result_path, "w") as fp:
                json.dump(result, fp, ensure_ascii=False, indent=2)
            _update_fs_history(result)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return job_id


def get_factor_select_status() -> dict:
    return dict(FACTOR_SELECT_STATUS)


def get_factor_select_result() -> dict:
    if os.path.exists(FS_RESULT_PATH):
        with open(FS_RESULT_PATH) as f:
            return _sanitize(json.load(f))
    return {"status": "not_started"}


FS_HISTORY = os.path.join(ML_DIR, "fs_history.json")

def _update_fs_history(result: dict):
    """追加因子筛选到历史"""
    entry = {
        "job_id": result.get("job_id", ""),
        "status": result.get("status", "unknown"),
        "final_factors": result.get("stages", {}).get("forward", {}).get("final_factors", []),
        "n_final": result.get("stages", {}).get("forward", {}).get("n_final", 0),
        "val_IC": result.get("stages", {}).get("forward", {}).get("final_val_IC", 0),
        "finished_at": datetime.now().isoformat(),
    }
    history = []
    if os.path.exists(FS_HISTORY):
        with open(FS_HISTORY) as f:
            history = json.load(f)
    history.insert(0, entry)
    with open(FS_HISTORY, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_fs_history() -> list:
    if os.path.exists(FS_HISTORY):
        with open(FS_HISTORY) as f:
            return _sanitize(json.load(f))
    # 兜底: 扫描文件系统
    results = []
    if os.path.exists(ML_DIR):
        for fn in sorted(os.listdir(ML_DIR), reverse=True):
            if fn.startswith("factor_select_result_fs_") and fn.endswith(".json"):
                job_id = fn[len("factor_select_result_"):-5]
                results.append({"job_id": job_id, "status": "done"})
    return results


# ── CLI ──
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--ic", action="store_true")
    ap.add_argument("--predict", type=int, default=30)
    ap.add_argument("--days", type=int, default=730)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--leaves", type=int, default=63)
    ap.add_argument("--estimators", type=int, default=200)
    args = ap.parse_args()

    t0 = time.time()
    feats = ALL_FEATURES
    if args.train:
        df = prepare_training_data(days=args.days, target_horizon=args.horizon, features=feats)
        train_model(df=df, features=feats, lr=args.lr, leaves=args.leaves, estimators=args.estimators,
                    target_horizon=args.horizon)
        evaluate_factor_ic(df=df, features=feats)
        predict_top_n(n=args.predict, features=feats)
    elif args.ic:
        df = prepare_training_data(features=feats)
        results = evaluate_factor_ic(df=df, features=feats)
        from pprint import pprint
        pprint(results)
    elif args.predict:
        r = predict_top_n(n=args.predict, features=feats)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    print(f"\n⏱ {time.time()-t0:.1f}s")
