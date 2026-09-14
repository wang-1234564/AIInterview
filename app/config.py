"""应用配置：从项目根目录的 .env 读取环境变量。

所有配置项集中在此处，其他模块通过 `from app.config import settings` 使用。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（app/config.py 的上级目录）
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载 .env（若存在）；不存在的键使用下方默认值
load_dotenv(BASE_DIR / ".env")


class Settings:
    """集中式配置。"""

    def __init__(self) -> None:
        self.deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_base_url: str = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self.deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./interview.db")
        self.use_mock_evaluator: bool = (
            os.getenv("USE_MOCK_EVALUATOR", "false").strip().lower()
            in ("true", "1", "yes")
        )
        # 用于加密数据库中保存的 API Key；留空则使用/生成项目根目录的 .secret_key
        self.app_secret_key: str = os.getenv("APP_SECRET_KEY", "")


settings = Settings()
