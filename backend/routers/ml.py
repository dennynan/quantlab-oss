"""ML 模型路由：训练 / 因子评估 / 预测 / 实验历史"""
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from services.ml_service import (
    train_async, get_train_status, get_factor_eval,
    get_predictions, get_history, TRAIN_META, ALL_FEATURES, FACTOR_META,
    run_factor_selection, get_factor_select_status, get_factor_select_result,
    get_fs_history,
    FACTOR_SELECT_STATUS,
)
import os, json

router = APIRouter(prefix="/api/ml", tags=["ML模型"])


class TrainRequest(BaseModel):
    days: int = Field(default=730, ge=60, le=1460, description="训练窗口天数")
    target_horizon: int = Field(default=5, ge=1, le=60, description="预测目标(未来N日收益)")
    valid_pct: int = Field(default=20, ge=5, le=40, description="验证集占比(%)")
    lr: float = Field(default=0.05, ge=0.001, le=0.3, description="学习率")
    leaves: int = Field(default=63, ge=15, le=1023, description="叶子数")
    estimators: int = Field(default=200, ge=50, le=1000, description="树数")
    features: Optional[List[str]] = Field(default=None, description="特征集(默认全部20个Alpha158因子)")


@router.post("/train")
def api_train(req: TrainRequest):
    from services.ml_service import TRAIN_STATUS
    if TRAIN_STATUS["running"]:
        return {"ok": False, "message": "训练已在运行中", "job_id": TRAIN_STATUS["job_id"]}
    features = req.features if req.features else ALL_FEATURES
    # 验证特征有效性
    features = [f for f in features if f in ALL_FEATURES]
    if not features:
        return {"ok": False, "message": "至少选择一个有效特征"}
    job_id = train_async(
        days=req.days, valid_pct=req.valid_pct,
        target_horizon=req.target_horizon,
        features=features,
        lr=req.lr, leaves=req.leaves, estimators=req.estimators,
    )
    return {"ok": True, "job_id": job_id, "message": "训练已启动",
            "features": features, "target_horizon": req.target_horizon}


@router.get("/train/status")
def api_status():
    return get_train_status()


@router.get("/train/meta")
def api_meta():
    if os.path.exists(TRAIN_META):
        with open(TRAIN_META) as f:
            return json.load(f)
    return {"note": "尚未训练"}


@router.get("/train/history")
def api_history():
    return {"experiments": get_history()}


@router.get("/factor_eval")
def api_factor_eval(job_id: str = Query(default=None)):
    return get_factor_eval(job_id=job_id)

@router.get("/factor_meta")
def api_factor_meta():
    """返回20个Alpha158因子元数据（中文名+分类）"""
    return {"factors": FACTOR_META, "count": len(FACTOR_META)}


@router.get("/predictions")
def api_predictions(n: int = Query(default=30, ge=5, le=100), job_id: str = Query(default=None)):
    return get_predictions(n=n, job_id=job_id)


# ── 智能选因子 ──

class FactorSelectRequest(BaseModel):
    mode: str = Field(default="full", description="full | screen_only | stability_only")
    target_horizon: int = Field(default=10, ge=1, le=60)
    lr: float = Field(default=0.03, ge=0.001, le=0.3)
    leaves: int = Field(default=63, ge=15, le=1023)
    estimators: int = Field(default=300, ge=50, le=1000)
    screener: dict = Field(default_factory=lambda: {"min_ir_abs": 0.15, "max_per_category": 5})
    stability: dict = Field(default_factory=lambda: {"n_windows": 3})
    forward_select: dict = Field(default_factory=lambda: {"top_n": 10, "min_ic_gain": 0.001})


@router.post("/factor-select")
def api_start_factor_select(req: FactorSelectRequest):
    if FACTOR_SELECT_STATUS["running"]:
        return {"ok": False, "message": "选因子已在运行中", "job_id": FACTOR_SELECT_STATUS["job_id"]}
    config = {
        "mode": req.mode,
        "target_horizon": req.target_horizon,
        "lr": req.lr,
        "leaves": req.leaves,
        "estimators": req.estimators,
        "screener": req.screener,
        "stability": req.stability,
        "forward_select": req.forward_select,
    }
    job_id = run_factor_selection(config)
    return {"ok": True, "job_id": job_id, "message": "智能选因子已启动"}


@router.get("/factor-select/status")
def api_factor_select_status():
    return get_factor_select_status()


@router.get("/factor-select/result")
def api_factor_select_result(job_id: str = Query(default=None)):
    if job_id:
        import os
        from services.ml_service import ML_DIR
        job_path = os.path.join(ML_DIR, f"factor_select_result_{job_id}.json")
        if os.path.exists(job_path):
            with open(job_path) as f:
                return json.load(f)
        return {"status": "not_found", "error": f"job {job_id} not found"}
    return get_factor_select_result()


@router.get("/factor-select/history")
def api_fs_history():
    return {"experiments": get_fs_history()}
