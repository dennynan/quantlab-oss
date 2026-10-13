"""无登录版依赖注入：固定 demo 用户 + 匿名访客标识 + 数据库会话。

开源版去掉了用户认证/登录：
- 权限/配额方面所有请求以固定 demo 用户运行（不校验 token）；
- 但「回测任务」这类用户产生的数据仍需要区分归属，否则多人访问同一个
  演示站时会互相看到对方的结果。这里用**匿名访客 id**（`get_anon_id`）
  做归属标记：优先取请求头 `X-Anon-Id`（前端 localStorage 持久化），
  其次取 Cookie，都没有则新发一个。

⚠️ 这不是安全边界（header 可伪造），只是避免多访客在演示站上互相干扰。
"""
import uuid

from fastapi import Request, Response

from database import SessionLocal

# 固定 demo 用户（init_db 会确保 users 表里有这条记录）
DEMO_USER = {
    "user_id": 1,
    "username": "demo",
    "role": "admin",
}

# 匿名访客 id 的 Cookie 名
ANON_COOKIE = "ql_anon_id"


def get_db():
    """FastAPI 依赖：数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user() -> dict:
    """无登录：恒返回固定 demo 用户（保持与原接口签名兼容）。"""
    return dict(DEMO_USER)


def get_anon_id(request: Request, response: Response) -> str:
    """匿名访客 id：请求头 X-Anon-Id → Cookie → 新生成（并回写 Cookie）。"""
    raw = (request.headers.get("X-Anon-Id") or request.cookies.get(ANON_COOKIE) or "").strip()
    ok = raw and len(raw) <= 64 and all(c.isalnum() or c in "-_" for c in raw)
    if not ok:
        raw = uuid.uuid4().hex
        response.set_cookie(ANON_COOKIE, raw, max_age=3600 * 24 * 365, samesite="lax")
    return raw
