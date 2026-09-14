"""数据库引擎与会话管理。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BASE_DIR, settings

# SQLite 需要 check_same_thread=False 以配合 FastAPI 多线程
connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def get_db():
    """FastAPI 依赖：提供数据库会话并在请求结束后关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """把数据库结构升级到最新版本（通过 Alembic，幂等）。

    首次运行会自动建库建表；后续模型变更只需新增迁移脚本，
    用户重启应用即可自动升级，无需手动操作。
    """
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig(str(BASE_DIR / "alembic.ini"))
    # 用绝对路径指定脚本目录，避免依赖当前工作目录
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    command.upgrade(cfg, "head")
