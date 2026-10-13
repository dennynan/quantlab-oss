"""QuantLab — AI量化分析平台 主入口"""
import sys, os
import time
from collections import defaultdict, deque
from pathlib import Path

# ── 资源控制：启动时限制线程数 + 降低进程优先级 ──
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
try:
    os.nice(5)
except Exception:
    pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from database import init_db
from routers import backtest, qlib, ml, rdagent

# ── 演示模式 ──
# 公网 Demo 用：开源版免登录、无鉴权，直接暴露到公网时必须收敛能力——
#   1) RD-Agent 只读化：历史/状态/结果可查看，但禁止发起挖掘/清理
#      （否则公网任何人都能白嫖付费 LLM 额度、拉子进程、写磁盘）
#   2) 对训练 / 回测 / 筛选等重接口按来源 IP 限流，只读接口不限
# 本地开发不设该变量，行为与原来完全一致。
OSS_DEMO = os.environ.get("OSS_DEMO", "").strip().lower() in ("1", "true", "yes", "on")

app = FastAPI(
    title="QuantLab OSS",
    description="AI 量化分析平台 API（开源版：去登录，固定 demo 用户）",
    version="0.1.0",
)

# CORS — 允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 演示站：RD-Agent 只读守卫（仅 OSS_DEMO 时启用） ──
# 查看历史/状态/结果放行（GET）；发起挖掘、清理等写操作一律 403。
class ReadOnlyRdagentMiddleware(BaseHTTPMiddleware):
    PREFIX = "/api/rdagent"
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(self.PREFIX) and request.method in self.WRITE_METHODS:
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "message": "演示站为只读模式：历史记录可查看，但不支持发起挖掘（会消耗付费 LLM 额度）",
                },
            )
        return await call_next(request)


# ── 演示站轻量限流（仅 OSS_DEMO 时启用） ──
# 规则：(HTTP 方法, 路径前缀, 窗口内最大次数, 窗口秒数)。按来源 IP（Tailscale Funnel 会带
# X-Forwarded-For）分桶，超限返回 429 + Retry-After。
# ⚠️ 只限制**提交类写操作**（POST），不限制状态轮询/历史等只读 GET——否则前端轮询
#    几秒就会撞限速，任务其实跑完了界面却看不到结果。
_RL_BUCKETS = defaultdict(deque)


class RateLimitMiddleware(BaseHTTPMiddleware):
    RULES = (
        ("POST", "/api/ml/train", 3, 300),
        ("POST", "/api/ml/factor-select", 3, 300),
        ("POST", "/api/backtest/topk", 10, 60),
        ("POST", "/api/qlib/screen", 30, 60),
    )

    @staticmethod
    def _client(request: Request) -> str:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        rule = next((r for r in self.RULES if method == r[0] and path.startswith(r[1])), None)
        if rule:
            _, prefix, limit, window = rule
            key = (self._client(request), prefix)
            now = time.time()
            dq = _RL_BUCKETS[key]
            while dq and now - dq[0] > window:
                dq.popleft()
            if len(dq) >= limit:
                retry = max(1, int(window - (now - dq[0])) + 1)
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"请求过于频繁，请 {retry} 秒后再试"},
                    headers={"Retry-After": str(retry)},
                )
            dq.append(now)
        return await call_next(request)


if OSS_DEMO:
    app.add_middleware(ReadOnlyRdagentMiddleware)
    app.add_middleware(RateLimitMiddleware)

# 注册路由（开源版无 auth/admin）
app.include_router(backtest.router)
app.include_router(qlib.router)
app.include_router(ml.router)
app.include_router(rdagent.router)


@app.on_event("startup")
def startup():
    init_db()
    # 2026-10-11：启动自愈——清理上一次运行残留的「僵尸 running」挖掘记录
    # （服务重启会中断挖掘线程、jobs.json 滞留 running，进而误阻塞历史缓存清理）
    if OSS_DEMO:
        return
    try:
        from services.rdagent_service import reconcile_stale_running
        n = reconcile_stale_running()
        if n:
            print(f"[rdagent] 启动自愈：{n} 条僵尸 running 已归零")
    except Exception as e:
        print(f"[rdagent][warn] 僵尸 running 自愈失败: {e}")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "QuantLab", "version": "0.1.0", "demo": OSS_DEMO}


# ── 直接启动 ──
if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
