"""回测路由 — 仅保留「多因子轮动」（Alpha158 因子 → TopK 持仓 → 定期轮动淘汰）

开源版说明：自定义脚本引擎与 Qlib 官方引擎已移除，只保留多因子 TopK 轮动回测。

任务持久化：回测结果同时落盘到 `data/backtest/<task_id>.json`，重启后仍可查询；
只保留最近 KEEP_TASKS 条（默认 50），启动时与每次写入后自动清理。
"""
import json
import os
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import rel_path
from deps import get_anon_id, get_db, get_current_user
from models import Quota, User
from services.qlib_topk_backtest import run_topk_backtest, get_available_factors

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

# ─── 异步任务进度管理器 ───
# 内存里只保留最近的任务（LRU），更早的一律从磁盘读，避免长时间运行后内存无限增长。
_topk_tasks: "OrderedDict[str, dict]" = OrderedDict()   # task_id → {progress, message, status, result, error}
_topk_tasks_lock = threading.Lock()
_topk_executor = ThreadPoolExecutor(max_workers=1)  # 单 worker，避免 CPU 竞争

# ─── 落盘与保留策略 ───
KEEP_TASKS = 50
BACKTEST_TASKS_DIR = Path(os.environ.get(
    "BACKTEST_TASKS_DIR",
    str(Path(__file__).resolve().parents[2] / "data" / "backtest"),
))


def _task_file(task_id: str) -> Path:
    return BACKTEST_TASKS_DIR / f"{task_id}.json"


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _persist_task(task_id: str, task: dict) -> None:
    """把任务（含结果）原子写入磁盘；写失败不影响本次回测返回。"""
    try:
        BACKTEST_TASKS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"task_id": task_id, **task}
        tmp = _task_file(task_id).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _task_file(task_id))
        _prune_disk()
    except Exception as e:
        print(f"[backtest] 任务落盘失败（{task_id}）：{e}")


def _load_task_from_disk(task_id: str) -> dict | None:
    try:
        p = _task_file(task_id)
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            d.pop("task_id", None)
            return d
    except Exception as e:
        print(f"[backtest] 读取落盘任务失败（{task_id}）：{e}")
    return None


def _prune_disk() -> None:
    """只保留最近 KEEP_TASKS 条（按 mtime，即完成时间），多余的删掉。"""
    try:
        if not BACKTEST_TASKS_DIR.is_dir():
            return
        files = [p for p in BACKTEST_TASKS_DIR.glob("*.json") if p.is_file()]
        if len(files) <= KEEP_TASKS:
            return
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[KEEP_TASKS:]:
            p.unlink(missing_ok=True)
    except Exception as e:
        print(f"[backtest] 清理历史任务失败：{e}")


def _evict_memory() -> None:
    """内存超限时，从最旧的「已结束」任务开始丢（running/pending 永不丢）。调用方需持锁。"""
    while len(_topk_tasks) > KEEP_TASKS:
        for tid, t in list(_topk_tasks.items()):
            if t.get("status") in ("done", "error"):
                _topk_tasks.pop(tid, None)
                break
        else:
            break   # 全是运行中的任务，先不丢


# 启动时：建目录 + 清理超出保留上限的历史任务
BACKTEST_TASKS_DIR.mkdir(parents=True, exist_ok=True)
_prune_disk()


def _check_quota(db: Session, user_id: int) -> None:
    """检查回测配额"""
    user = db.query(User).filter(User.id == user_id).first()
    limit = user.backtest_daily_limit if user else 10
    ok, msg = Quota.check_and_use(db, user_id, "backtest_used", limit)
    if not ok:
        raise HTTPException(status_code=429, detail=msg)


def _make_progress_cb(task_id: str):
    def cb(pct: int, msg: str):
        with _topk_tasks_lock:
            if task_id in _topk_tasks:
                _topk_tasks[task_id]["progress"] = pct
                _topk_tasks[task_id]["message"] = msg
    return cb


def _run_topk_task(task_id: str, params: dict):
    try:
        with _topk_tasks_lock:
            _topk_tasks[task_id]["status"] = "running"
            _topk_tasks[task_id]["finished_at"] = None
        result = run_topk_backtest(
            factors=params["factors"],
            weights=params.get("weights"),
            top_k=params["top_k"],
            n_drop=params["n_drop"],
            rebalance_freq=params["rebalance_freq"],
            days=params["days"],
            initial_cash=params["initial_cash"],
            hold_thresh=params.get("hold_thresh", 1),
            custom_pool=params.get("custom_pool"),
            progress_callback=_make_progress_cb(task_id),
        )
        with _topk_tasks_lock:
            t = _topk_tasks[task_id]
            t["status"] = "done"
            t["result"] = result
            t["progress"] = 100
            t["message"] = "回测完成"
            t["finished_at"] = _now_iso()
            _persist_task(task_id, dict(t))
            _evict_memory()
    except Exception as e:
        tb = __import__("traceback").format_exc()
        print(tb)
        with _topk_tasks_lock:
            t = _topk_tasks[task_id]
            t["status"] = "error"
            t["error"] = str(e)
            t["finished_at"] = _now_iso()
            _persist_task(task_id, dict(t))
            _evict_memory()


@router.get("/topk/factors")
def list_topk_factors():
    """返回可用于 TopK 轮动的因子列表（按分类）"""
    return get_available_factors()


@router.post("/topk")
def topk_backtest(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    anon_id: str = Depends(get_anon_id),
):
    """
    多因子 TopK 轮动回测（异步模式: 立即返回 task_id, 前端轮询 /topk/status/{task_id}）

    payload: {
        factors: ["REVS20", "Rtn20", ...],   // 因子列表
        weights: [0.4, 0.3, 0.3],             // 权重（默认等权）
        top_k: 10,                            // 持仓数量
        n_drop: 3,                            // 每次调仓替换数
        rebalance_freq: "month",              // 调仓频率: day/week/month
        days: 500,                            // 回测天数
        initial_cash: 1000000,                // 初始资金
        hold_thresh: 1,                       // 最小持有天数
        custom_pool: ["sh600519", ...],       // 可选：限定股票池
    }
    """
    factors = payload.get("factors", [])
    weights = payload.get("weights")
    top_k = payload.get("top_k", 10)
    n_drop = payload.get("n_drop", 3)
    rebalance_freq = payload.get("rebalance_freq", "month")
    days = payload.get("days", 500)
    initial_cash = payload.get("initial_cash", 1000000)
    hold_thresh = payload.get("hold_thresh", 1)

    if not factors:
        raise HTTPException(400, "请至少选择一个因子")
    if len(factors) > 10:
        raise HTTPException(400, "最多选择10个因子")
    if top_k < 1 or top_k > 50:
        raise HTTPException(400, "TopK 范围为 1-50")
    if n_drop < 1 or n_drop > top_k:
        raise HTTPException(400, f"n_drop 范围为 1-{top_k}")
    if rebalance_freq not in ("day", "week", "month"):
        raise HTTPException(400, "调仓频率仅支持 day/week/month")

    _check_quota(db, current_user["user_id"])

    task_id = uuid.uuid4().hex[:12]
    with _topk_tasks_lock:
        _topk_tasks[task_id] = {
            "progress": 0,
            "message": "排队中...",
            "status": "pending",
            "result": None,
            "error": None,
            "owner": anon_id,      # 匿名访客归属，避免多访客互相看到别人的任务
            "created_at": _now_iso(),
            "finished_at": None,
            "params": {
                "factors": factors,
                "top_k": top_k,
                "n_drop": n_drop,
                "rebalance_freq": rebalance_freq,
                "days": days,
                "initial_cash": initial_cash,
            },
        }

    _topk_executor.submit(_run_topk_task, task_id, {
        "factors": factors,
        "weights": weights,
        "top_k": top_k,
        "n_drop": n_drop,
        "rebalance_freq": rebalance_freq,
        "days": days,
        "initial_cash": initial_cash,
        "hold_thresh": hold_thresh,
        "custom_pool": payload.get("custom_pool"),
    })

    return {"task_id": task_id, "status": "pending", "message": "任务已提交"}


@router.get("/topk/status/{task_id}")
def topk_status(task_id: str, anon_id: str = Depends(get_anon_id)):
    """轮询 TopK 回测进度（内存找不到则回落到落盘记录，重启后也能查）

    只返回本访客自己的任务，别人的一律当作不存在。
    """
    with _topk_tasks_lock:
        task = _topk_tasks.get(task_id)
    source = "memory"
    if not task:
        task = _load_task_from_disk(task_id)
        source = "disk"
    if not task or task.get("owner") != anon_id:
        raise HTTPException(404, "任务不存在或已过期（超出保留的最近 50 条）")
    resp = {
        "task_id": task_id,
        "status": task["status"],
        "progress": task["progress"],
        "message": task["message"],
        "finished_at": task.get("finished_at"),
        "source": source,   # memory=当前进程内 / disk=从落盘记录读取
    }
    if task.get("result") is not None:
        resp["result"] = task["result"]
    if task.get("error"):
        resp["error"] = task["error"]
    return resp


@router.get("/topk/history")
def topk_history(limit: int = 20, anon_id: str = Depends(get_anon_id)):
    """列出**本访客**最近的 TopK 任务（不含结果体，只给元信息；数据来自落盘记录）"""
    limit = max(1, min(int(limit), KEEP_TASKS))
    items = []
    try:
        files = [p for p in BACKTEST_TASKS_DIR.glob("*.json") if p.is_file()]
    except Exception:
        files = []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        if len(items) >= limit:
            break
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("owner") != anon_id:
            continue
        items.append({
            "task_id": d.get("task_id", p.stem),
            "status": d.get("status"),
            "created_at": d.get("created_at"),
            "finished_at": d.get("finished_at"),
            "params": d.get("params"),
            "has_result": d.get("result") is not None,
        })
    return {"keep": KEEP_TASKS, "dir": rel_path(BACKTEST_TASKS_DIR), "count": len(items), "items": items}


@router.delete("/topk/history")
def topk_history_clear(anon_id: str = Depends(get_anon_id)):
    """清空**本访客**的回测历史（内存 + 落盘）。

    运行中的任务不删（删了回调/落盘会 KeyError），会返回 skipped_running 告知。
    """
    deleted_file = 0
    # ① 落盘：只删 owner 匹配且已结束的
    try:
        for p in BACKTEST_TASKS_DIR.glob("*.json"):
            if not p.is_file():
                continue
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("owner") != anon_id:
                continue
            if d.get("status") not in ("done", "error"):
                continue
            p.unlink(missing_ok=True)
            deleted_file += 1
    except Exception as e:
        print(f"[backtest] 清空历史失败：{e}")

    # ② 内存：同样只删已结束的
    deleted_mem, skipped_running = 0, 0
    with _topk_tasks_lock:
        for tid, t in list(_topk_tasks.items()):
            if t.get("owner") != anon_id:
                continue
            if t.get("status") in ("done", "error"):
                _topk_tasks.pop(tid, None)
                deleted_mem += 1
            else:
                skipped_running += 1

    return {
        "ok": True,
        "deleted": deleted_file,
        "deleted_memory": deleted_mem,
        "skipped_running": skipped_running,
        "message": f"已清空 {deleted_file} 条历史记录",
    }
