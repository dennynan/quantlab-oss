"""QuantLab 配置"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'quantlab.db'}"

# 说明：开源版无用户认证，不再需要 JWT 配置。
# 配额（保留默认值，demo 用户实际为无限额）
DEFAULT_DAILY_AI_LIMIT = 10
DEFAULT_DAILY_BACKTEST_LIMIT = 10

# 回测
BACKTEST_TIMEOUT_SECONDS = 30
BACKTEST_MAX_WORKERS = 2  # 回测并发数

# 服务
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "5001"))


def rel_path(p) -> str:
    """把绝对路径压成「仓库内相对路径」，避免 API 对外暴露部署路径。

    不在仓库内时退化为 ~/…；再不行只保留文件名。仅供响应展示使用。
    """
    try:
        path = Path(p)
    except Exception:
        return str(p)
    for base, prefix in ((PROJECT_ROOT, ""), (Path.home(), "~/")):
        try:
            return prefix + str(path.relative_to(base))
        except ValueError:
            continue
    return path.name
