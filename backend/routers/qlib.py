"""
QuantLab Qlib API 路由
因子分析 · 股票筛选 · 回测
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
import traceback

from services.alpha158_factors import get_alpha158_factor_list, CATEGORIES
from services.qlib_service import (
    get_health,
    get_stock_factors,
    get_stock_full_analysis,
    get_factor_list,
    screen_stocks,
    get_alpha158_stock_factors,
    FACTOR_DEFS,
)

router = APIRouter(prefix="/api/qlib", tags=["Qlib量化"])


# ── 请求/响应模型 ──
class ScreenCondition(BaseModel):
    factor: str = Field(..., description="因子key", examples=["momentum_5"])
    op: str = Field("gt", description="比较符: gt/lt/gte/lte/between")
    value: float = Field(..., description="阈值")


class ScreenRequest(BaseModel):
    conditions: List[ScreenCondition] = Field(..., min_length=1)
    limit: int = Field(20, ge=1, le=100)


# ── 路由 ──
@router.get("/health")
def api_qlib_health():
    """Qlib 健康状态"""
    return get_health()


@router.get("/factors")
def api_qlib_factor_list():
    """可用因子列表"""
    return {"factors": get_factor_list()}


@router.get("/factors/alpha158")
def api_alpha158_list():
    """Alpha158全部因子列表（按分类）"""
    return {"factors": get_alpha158_factor_list(), "total": sum(len(keys) for keys in CATEGORIES.values())}


@router.get("/factors/{code}")
def api_qlib_stock_factors(code: str):
    """单只股票因子分析"""
    code = code.strip().lower()
    if not code:
        raise HTTPException(400, "缺少股票代码")
    result = get_stock_factors(code)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/factors/{code}/alpha158")
def api_alpha158_stock_factors(code: str):
    """单只股票Alpha158因子查询"""
    code = code.strip().lower()
    if not code:
        raise HTTPException(400, "缺少股票代码")
    result = get_alpha158_stock_factors(code)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/factors/{code}/full")
def api_qlib_stock_full_analysis(code: str):
    """全量单股分析：指标 + 多周期形态 + 五维评分 + 研判报告（本地规则生成）"""
    code = code.strip().lower()
    if not code:
        raise HTTPException(400, "缺少股票代码")
    try:
        result = get_stock_full_analysis(code)
        if "error" in result:
            raise HTTPException(404, result["error"])
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"分析失败: {e}")


@router.post("/screen")
def api_qlib_screen(req: ScreenRequest):
    """多因子股票筛选"""
    try:
        conditions = [c.model_dump() for c in req.conditions]
        result = screen_stocks(conditions, limit=req.limit)
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"筛选失败: {e}")


@router.get("/screen/quick")
def api_qlib_quick_screen(
    momentum_min: Optional[float] = Query(None, description="5日动量最小值(%)"),
    momentum_max: Optional[float] = Query(None, description="5日动量最大值(%)"),
    rsi_min: Optional[float] = Query(None, description="RSI最小值"),
    rsi_max: Optional[float] = Query(None, description="RSI最大值"),
    ma20_dev_min: Optional[float] = Query(None, description="MA20偏离最小值(%)"),
    vol_max: Optional[float] = Query(None, description="波动率最大值(%)"),
    amount_min: Optional[float] = Query(None, description="20日均成交额最小值(万)"),
    limit: int = Query(20, ge=1, le=100),
):
    """快捷多因子筛选（GET 方式，适合浏览器）"""
    conditions = []
    if momentum_min is not None or momentum_max is not None:
        if momentum_max is not None:
            conditions.append({
                "factor": "momentum_5",
                "op": "between",
                "value": [momentum_min or -100, momentum_max],
            })
        else:
            conditions.append({
                "factor": "momentum_5",
                "op": "gt",
                "value": momentum_min,
            })
    if rsi_min is not None:
        conditions.append({"factor": "rsi_14", "op": "gt", "value": rsi_min})
    if rsi_max is not None:
        conditions.append({"factor": "rsi_14", "op": "lt", "value": rsi_max})
    if ma20_dev_min is not None:
        conditions.append({"factor": "ma20_dev", "op": "gt", "value": ma20_dev_min})
    if vol_max is not None:
        conditions.append({"factor": "volatility_20", "op": "lt", "value": vol_max})
    if amount_min is not None:
        conditions.append({"factor": "avg_amount_20", "op": "gt", "value": amount_min})

    if not conditions:
        raise HTTPException(400, "至少需要一个筛选条件")

    try:
        return screen_stocks(conditions, limit=limit)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"筛选失败: {e}")
