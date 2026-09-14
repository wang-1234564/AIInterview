"""Alembic 迁移环境。

数据库地址与目标元数据都取自应用本身（app.config / app.database），
这样 CLI（alembic upgrade head）与程序内调用（app.database.init_db）行为一致。
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 无论从哪个工作目录调用，都让 alembic 能 import app.*
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app import models  # noqa: E402,F401  导入以确保所有模型注册到 metadata

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False：避免覆盖应用/uvicorn 已有的日志配置
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# 数据库地址统一来自 .env 的 DATABASE_URL；转义 % 以免被 configparser 当成插值
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连接数据库。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite 不支持大部分 ALTER，需要 batch 模式重建表
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
