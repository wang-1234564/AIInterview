"""OpenAI 兼容客户端封装：调用真实大模型（DeepSeek / OpenAI / Qwen / 自定义）。

连接参数（api_key / base_url / model）由调用方通过 LLMConfig 注入，
用户可在「设置」页选择自己的供应商。是否走真实调用由
app/services/llm_config.py 的 enabled 决定（无 Key 时使用 mock）。
"""
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.services.llm_config import LLMConfig


class DeepSeekError(Exception):
    """大模型调用失败。"""


class DeepSeekClient:
    """按给定配置调用 OpenAI 兼容接口。"""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client: Optional[OpenAI] = None
        if config.api_key:
            self._client = OpenAI(
                api_key=config.api_key,
                base_url=config.base_url or None,
                timeout=60.0,
            )

    @property
    def available(self) -> bool:
        return self._client is not None

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2000,
        max_retries: int = 2,
        json_mode: bool = False,
    ) -> str:
        """调用对话补全，返回文本内容。

        json_mode=True 时请求模型返回 JSON（配合 system 提示中的 JSON 约束使用）。
        """
        if not self._client:
            raise DeepSeekError("未配置 API Key，无法调用真实评估")

        kwargs: Dict[str, Any] = dict(
            model=self._config.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_err: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                resp = self._client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content or ""
                return content
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if attempt < max_retries:
                    time.sleep(2**attempt)  # 1s、2s 指数退避
        raise DeepSeekError(f"大模型调用失败：{last_err}")
