"""SQLAlchemy 数据模型"""
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, DateTime, Date, Text, Float, Enum as SAEnum
from sqlalchemy.orm import Session as DBSession
from database import Base, SessionLocal
import enum


# ═══════════════════════════════════
#  枚举
# ═══════════════════════════════════
class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"


class BacktestStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class BacktestType(str, enum.Enum):
    template = "template"   # 内置模板
    upload = "upload"       # 用户上传


# ═══════════════════════════════════
#  用户
# ═══════════════════════════════════
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(10), default="user")
    ai_daily_limit = Column(Integer, default=10)
    backtest_daily_limit = Column(Integer, default=10)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)


# ═══════════════════════════════════
#  每日配额
# ═══════════════════════════════════
class Quota(Base):
    __tablename__ = "quotas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    quota_date = Column(Date, nullable=False)
    ai_used = Column(Integer, default=0)
    backtest_used = Column(Integer, default=0)

    @classmethod
    def get_or_create(cls, db: DBSession, user_id: int):
        today = date.today()
        q = db.query(cls).filter(cls.user_id == user_id, cls.quota_date == today).first()
        if not q:
            q = cls(user_id=user_id, quota_date=today)
            db.add(q)
            db.commit()
            db.refresh(q)
        return q

    @classmethod
    def check_and_use(cls, db: DBSession, user_id: int, field: str, limit: int) -> tuple[bool, str]:
        """检查并扣减配额"""
        q = cls.get_or_create(db, user_id)
        current = getattr(q, field)
        if current >= limit:
            return False, f"已达每日上限 {limit} 次"
        setattr(q, field, current + 1)
        db.commit()
        remaining = limit - (current + 1)
        return True, f"配额充足，剩余 {remaining} 次"


# ═══════════════════════════════════
#  回测任务
# ═══════════════════════════════════
class BacktestJob(Base):
    __tablename__ = "backtest_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    stock_code = Column(String(20), nullable=False)
    stock_name = Column(String(50))
    strategy_name = Column(String(100))
    bt_type = Column(String(10), default="template")
    params = Column(Text)       # JSON 参数
    status = Column(String(20), default="queued")
    queue_position = Column(Integer, default=0)
    result_json = Column(Text)  # 回测结果 JSON
    result_path = Column(String(500))  # 下载文件路径
    error_msg = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
