"""RD-Agent 自动因子挖掘路由"""
from config import rel_path
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from services.rdagent_service import (
    start_mining, get_status, get_result, get_history, run_cleanup, get_disk_info,
    RDAGENT_STATUS, find_best_sota_session,
)

router = APIRouter(prefix="/api/rdagent", tags=["自动因子挖掘"])

# 响应中可能包含本机绝对路径的字段：对外统一转为仓库相对路径，避免暴露部署路径
_PATH_KEYS = ("session_path", "session_root")


def _sanitize_paths(obj):
    if isinstance(obj, dict):
        for k in _PATH_KEYS:
            if isinstance(obj.get(k), str):
                obj[k] = rel_path(obj[k])
    return obj


class MiningRequest(BaseModel):
    loop_n: int = Field(default=1, ge=1, le=10, description="迭代圈数(1-10)")
    resume: bool = Field(default=False, description="是否续跑上次会话")
    resume_best: bool = Field(
        default=False,
        description="P0-4：续挖到「当前生效 SOTA 最高」的历史会话（与 resume 二选一，resume_best 优先）",
    )


class CleanupRequest(BaseModel):
    dry_run: bool = Field(default=False, description="只预览可清理项，不删除")


@router.post("/start")
def api_start(req: MiningRequest):
    if RDAGENT_STATUS["running"]:
        return {"ok": False, "message": "已有挖掘任务在运行中", "job_id": RDAGENT_STATUS["job_id"]}
    try:
        info = start_mining(loop_n=req.loop_n, resume=req.resume, resume_best=req.resume_best)
    except RuntimeError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": True, "job_id": info["job_id"], "message": "挖掘已启动",
            "resume": info["resume"], "resume_from": info["resume_from"],
            "total_loops": info["total_loops"]}


@router.get("/best-session")
def api_best_session():
    """P0-4：返回「当前生效 SOTA 最高、且可续跑」的会话（供前端「续挖到最佳会话」按钮展示）。"""
    try:
        target = find_best_sota_session()
    except Exception as e:  # 读 jobs.json 失败不应 500，前端降级处理即可
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}
    if target is None:
        return {"ok": False, "message": "暂无可续跑的历史 SOTA 会话"}
    return _sanitize_paths({"ok": True, **target})


@router.get("/status")
def api_status():
    return get_status()


@router.get("/result")
def api_result(job_id: str = Query(default=None)):
    return _sanitize_paths(dict(get_result(job_id=job_id)))


@router.get("/history")
def api_history():
    return {"jobs": get_history()}


@router.get("/disk")
def api_disk():
    """RD-Agent 产物体积 + 磁盘余量。"""
    return get_disk_info()


@router.post("/cleanup")
def api_cleanup(req: CleanupRequest):
    """清理历史缓存（走废纸篓，可恢复）；dry_run=true 只预览。"""
    try:
        return run_cleanup(dry_run=req.dry_run)
    except RuntimeError as e:
        return {"ok": False, "message": str(e)}
