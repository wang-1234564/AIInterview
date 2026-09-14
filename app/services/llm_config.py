"""LLM 配置解析。

单用户本地应用：用户在「设置」页选择供应商、填写 API Key 与模型，保存在
本地数据库的 AppSetting 单行中；未配置的项回退到全局 .env（DEEPSEEK_*）。
两者都没有 Key 时，评估走 mock 模式，流程仍可跑通。
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import security
from app.config import settings
from app.models import AppSetting

# 内置供应商预设：base_url 与默认模型（自定义时留空，由用户填写）
PROVIDERS = [
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "docs": "https://platform.deepseek.com",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "docs": "https://platform.openai.com",
    },
    {
        "id": "qwen",
        "label": "通义千问（DashScope 兼容模式）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "docs": "https://dashscope.console.aliyun.com",
    },
    {
        "id": "custom",
        "label": "自定义（OpenAI 兼容接口）",
        "base_url": "",
        "model": "",
        "docs": "",
    },
]

DEFAULT_PROVIDER = "deepseek"


def provider_ids() -> set:
    return {p["id"] for p in PROVIDERS}


def provider_preset(provider: str) -> dict:
    """取供应商预设；未知供应商回退到默认预设。"""
    for p in PROVIDERS:
        if p["id"] == provider:
            return p
    return PROVIDERS[0]


@dataclass
class LLMConfig:
    provider: str
    api_key: str
    base_url: str
    model: str

    @property
    def enabled(self) -> bool:
        """是否走真实大模型：需要 API Key 且未强制 mock。"""
        return bool(self.api_key) and not settings.use_mock_evaluator


def get_setting(db: Session) -> AppSetting:
    """读取单例设置行（不存在时创建默认行）。"""
    setting = db.get(AppSetting, 1)
    if setting is None:
        setting = AppSetting(id=1, provider=DEFAULT_PROVIDER)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def migrate_plaintext_key(db: Session) -> bool:
    """把历史遗留的明文 api_key 加密回写（幂等）。返回是否发生迁移。"""
    setting = db.get(AppSetting, 1)
    if setting is None or not setting.api_key:
        return False
    if security.is_encrypted(setting.api_key):
        return False
    setting.api_key = security.encrypt(setting.api_key)
    db.commit()
    return True


def resolve_config(db: Session) -> LLMConfig:
    """解析当前生效的 LLM 配置。

    优先级：数据库设置 > 内置预设默认值。
    其中默认供应商（deepseek）额外让 .env 的 DEEPSEEK_* 生效——因为这些环境
    变量本就是给 DeepSeek 用的默认值；切到其它供应商时不再继承它们，
    以免用 DeepSeek 的 Key/模型去请求 OpenAI/Qwen。
    """
    setting = db.get(AppSetting, 1)
    provider = (setting.provider if setting else "") or DEFAULT_PROVIDER
    preset = provider_preset(provider)

    raw_base = (setting.base_url if setting else "") or ""
    raw_model = (setting.model if setting else "") or ""
    # 数据库中的 api_key 是密文，先解密再参与回退判断
    stored_key = security.decrypt((setting.api_key if setting else "") or "")

    if provider == DEFAULT_PROVIDER:
        api_key = stored_key or settings.deepseek_api_key
        base_url = raw_base.strip() or settings.deepseek_base_url or preset["base_url"]
        model = raw_model.strip() or settings.deepseek_model or preset["model"]
    else:
        api_key = stored_key
        base_url = raw_base.strip() or preset["base_url"]
        model = raw_model.strip() or preset["model"]

    return LLMConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


def mask_key(key: str) -> str:
    """脱敏展示：只保留前 4 位与后 4 位。"""
    key = key or ""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * 6}{key[-4:]}"
