"""数据库引擎 & 会话工厂"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    """创建所有表 + 确保 demo 用户存在 — 首次启动调用"""
    from models import User, Quota, BacktestJob  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _seed_demo_user()


def _seed_demo_user():
    """开源版无登录：确保 id=1 的 demo 用户存在且配额充足。"""
    from models import User
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.id == 1).first():
            db.add(User(id=1, username="demo", password_hash="!", role="admin",
                        ai_daily_limit=10 ** 9, backtest_daily_limit=10 ** 9))
            db.commit()
    finally:
        db.close()
