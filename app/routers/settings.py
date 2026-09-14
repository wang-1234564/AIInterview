"""设置路由：查看 / 修改 LLM 供应商配置（本地单用户，存本地数据库）。

API Key 只返回脱敏值；提交时若带 `*`（前端回显的脱敏串）则视为未修改。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import security
from app.config import settings
from app.database import get_db
from app.services.deepseek import DeepSeekClient, DeepSeekError
from app.services.llm_config import (
    PROVIDERS,
    LLMConfig,
    get_setting,
    mask_key,
    provider_preset,
    resolve_config,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class LLMConfigIn(BaseModel):
    provider: str
    api_key: Optional[str] = None  # None=保持不变；""=清空；其它=更新
    base_url: str = ""
    model: str = ""


class LLMTestIn(BaseModel):
    """测试连接的入参（全部可选）：用于测试尚未保存的表单值。"""

    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


def _to_out(db: Session) -> dict:
    setting = get_setting(db)
    effective = resolve_config(db)
    stored_key = security.decrypt(setting.api_key or "")  # 库中保存的是密文
    return {
        "provider": effective.provider,
        "base_url": effective.base_url,
        "model": effective.model,
        "has_key": bool(effective.api_key),
        "api_key_masked": mask_key(stored_key),
        "using_env_key": (not stored_key) and bool(settings.deepseek_api_key),
        "enabled": effective.enabled,
        "mock_forced": settings.use_mock_evaluator,
    }


@router.get("/llm/providers")
def list_providers():
    """内置供应商预设（供设置页下拉选择）。"""
    return PROVIDERS


@router.get("/llm")
def get_llm(db: Session = Depends(get_db)):
    """当前生效的 LLM 配置（Key 脱敏）。"""
    return _to_out(db)


@router.put("/llm")
def update_llm(payload: LLMConfigIn, db: Session = Depends(get_db)):
    """保存 LLM 配置：供应商 + Key + Base URL + 模型。"""
    preset = provider_preset(payload.provider)
    if payload.provider != preset["id"]:
        raise HTTPException(400, "未知的供应商")

    setting = get_setting(db)
    setting.provider = payload.provider
    setting.base_url = (payload.base_url or "").strip() or preset["base_url"]
    setting.model = (payload.model or "").strip() or preset["model"]

    if not setting.base_url:
        raise HTTPException(400, "请填写接口地址（Base URL）")
    if not setting.model:
        raise HTTPException(400, "请填写模型名称")

    if payload.api_key is not None:
        key = payload.api_key.strip()
        # 前端回显的脱敏值（含 *）表示未实际修改，忽略之
        if key and "*" not in key:
            setting.api_key = security.encrypt(key)  # 加密后入库
        elif key == "":
            setting.api_key = ""

    db.commit()
    db.refresh(setting)
    return _to_out(db)


@router.post("/llm/test")
def test_llm(
    payload: Optional[LLMTestIn] = None, db: Session = Depends(get_db)
):
    """做一次最小调用验证连通性。

    可传入当前表单值，从而在点「保存」前就测试刚填写的 Key / 模型；
    不传则使用已保存的配置（含 .env 回退）。
    """
    saved = resolve_config(db)
    if payload is None:
        llm = saved
    else:
        api_key = saved.api_key
        if payload.api_key is not None:
            key = payload.api_key.strip()
            if key == "":
                api_key = ""  # 显式清空
            elif "*" not in key:
                api_key = key  # 回显的脱敏串（含 *）表示未修改，沿用已保存值
        llm = LLMConfig(
            provider=payload.provider or saved.provider,
            api_key=api_key,
            base_url=(payload.base_url or "").strip() or saved.base_url,
            model=(payload.model or "").strip() or saved.model,
        )

    if not llm.api_key:
        raise HTTPException(400, "尚未配置 API Key")
    client = DeepSeekClient(llm)
    try:
        text = client.chat(
            [{"role": "user", "content": "请只回复两个字：ok"}],
            temperature=0.0,
            max_tokens=64,  # 给 reasoning 模型留出思考预算，避免返回空内容
            max_retries=0,
        )
    except DeepSeekError as exc:
        raise HTTPException(400, f"连接失败：{exc}")
    return {
        "ok": True,
        "provider": llm.provider,
        "model": llm.model,
        "sample": (text or "").strip()[:50],
    }
