"""pytest 共享配置：在 import app 之前设置隔离的测试数据库与 mock 评估。"""
import os
import tempfile

_TMP_DB = os.path.join(tempfile.gettempdir(), "aiinterview_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["USE_MOCK_EVALUATOR"] = "true"

import pytest

from app.database import SessionLocal, engine, init_db


def _reset_schema() -> None:
    """清空数据库并重建（走 Alembic，与生产建库路径一致）。"""
    from app.database import Base

    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        # alembic_version 不在 metadata 中，需显式删除，否则 upgrade 会跳过建表
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    init_db()


@pytest.fixture()
def db():
    """每个测试独立的空数据库会话。"""
    _reset_schema()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        _reset_schema()
