"""设置接口与 LLM 配置解析的测试。"""
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.llm_config import (
    get_setting,
    mask_key,
    provider_preset,
    resolve_config,
)


def test_mask_key():
    assert mask_key("") == ""
    assert mask_key("short") == "*****"
    assert mask_key("sk-1234567890abcd") == "sk-1******abcd"


def test_provider_preset_fallback():
    assert provider_preset("openai")["base_url"].startswith("https://api.openai.com")
    # 未知供应商回退到默认预设
    assert provider_preset("nope")["id"] == "deepseek"


def test_resolve_config_falls_back_to_env(db):
    """数据库无设置时，默认供应商继承 .env 的 DeepSeek 配置。"""
    cfg = resolve_config(db)
    assert cfg.provider == "deepseek"
    assert cfg.model == settings.deepseek_model
    assert cfg.base_url == settings.deepseek_base_url
    if settings.deepseek_api_key:
        assert cfg.api_key == settings.deepseek_api_key
    # conftest 设置了 USE_MOCK_EVALUATOR=true，因此不启用真实调用
    assert cfg.enabled is False


def test_env_not_inherited_by_other_providers(db):
    """.env 的 DEEPSEEK_* 只作用于默认供应商，切换后改用内置预设。"""
    setting = get_setting(db)
    setting.provider = "openai"
    db.commit()

    cfg = resolve_config(db)
    assert cfg.provider == "openai"
    assert cfg.model == provider_preset("openai")["model"]
    assert cfg.base_url == provider_preset("openai")["base_url"]
    assert cfg.api_key == ""  # 不再继承 DEEPSEEK_API_KEY


def test_settings_endpoints(db):
    with TestClient(app) as client:
        providers = client.get("/api/settings/llm/providers").json()
        assert [p["id"] for p in providers] == ["deepseek", "openai", "qwen", "custom"]

        # 保存 openai：base_url / model 自动取预设默认值
        r = client.put(
            "/api/settings/llm",
            json={"provider": "openai", "api_key": "sk-1234567890abcd"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["provider"] == "openai"
        assert body["base_url"].startswith("https://api.openai.com")
        assert body["model"] == "gpt-4o-mini"
        assert body["has_key"] is True
        assert body["api_key_masked"] == "sk-1******abcd"

        # 回显的脱敏值重提交，不应覆盖真实 key
        r2 = client.put(
            "/api/settings/llm",
            json={"provider": "openai", "api_key": body["api_key_masked"]},
        )
        assert r2.json()["api_key_masked"] == "sk-1******abcd"

        # 未知供应商
        assert client.put("/api/settings/llm", json={"provider": "bogus"}).status_code == 400

        # 自定义供应商缺 Base URL / 模型时报错
        assert client.put("/api/settings/llm", json={"provider": "custom"}).status_code == 400

        # 清空 Key
        r3 = client.put(
            "/api/settings/llm",
            json={
                "provider": "custom",
                "api_key": "",
                "base_url": "https://x/v1",
                "model": "m",
            },
        )
        assert r3.status_code == 200
        assert r3.json()["api_key_masked"] == ""


def test_api_key_is_encrypted_at_rest(db):
    """数据库里保存的应是密文，而接口返回的仍是明文脱敏值。"""
    from app import security
    from app.models import AppSetting
    from app.services.llm_config import resolve_config

    secret = "sk-plain-abcdef123456"
    with TestClient(app) as client:
        client.put("/api/settings/llm", json={"provider": "deepseek", "api_key": secret})
        body = client.get("/api/settings/llm").json()
        assert body["api_key_masked"] == mask_key(secret)
        assert body["has_key"] is True

    db.expire_all()
    stored = db.get(AppSetting, 1).api_key
    assert secret not in stored            # 明文不落库
    assert security.is_encrypted(stored)   # 存的是密文
    assert security.decrypt(stored) == secret
    assert resolve_config(db).api_key == secret


def test_plaintext_key_is_migrated(db):
    """历史遗留的明文 Key 应能被迁移为密文（幂等）。"""
    from app import security
    from app.models import AppSetting
    from app.services.llm_config import migrate_plaintext_key

    setting = AppSetting(id=1, provider="deepseek", api_key="sk-legacy-plaintext")
    db.add(setting)
    db.commit()

    assert migrate_plaintext_key(db) is True
    db.expire_all()
    stored = db.get(AppSetting, 1).api_key
    assert security.is_encrypted(stored)
    assert security.decrypt(stored) == "sk-legacy-plaintext"
    assert migrate_plaintext_key(db) is False  # 幂等
