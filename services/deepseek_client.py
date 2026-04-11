"""DeepSeek 客户端封装。

这里提供最小的 HTTP 调用层，用于向 DeepSeek 请求结构化 JSON 结果。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

import requests


@dataclass
class DeepSeekConfig:
    """DeepSeek 调用所需的运行参数。"""

    enabled: bool = False
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model_name: str = "deepseek-chat"
    timeout: float = 30.0
    retry: int = 1

    @classmethod
    def from_env(cls) -> "DeepSeekConfig":
        """从环境变量构造 DeepSeek 配置。"""

        return cls(
            enabled=os.getenv("DEEPSEEK_ENABLED", "0").lower() in {"1", "true", "yes"},
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model_name=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            timeout=float(os.getenv("DEEPSEEK_TIMEOUT", "30")),
            retry=int(os.getenv("DEEPSEEK_RETRY", "1")),
        )


class DeepSeekClient:
    """DeepSeek 的简易 HTTP 客户端。"""

    def __init__(self, config: Optional[DeepSeekConfig] = None) -> None:
        """初始化客户端；未显式传入时从环境变量读取配置。"""

        self.config = config or DeepSeekConfig.from_env()

    def is_available(self) -> bool:
        """判断当前配置是否足以发起请求。"""

        return bool(
            self.config.enabled
            and self.config.api_key
            and self.config.base_url
            and self.config.model_name
        )

    def chat_json(self, system_prompt: str, user_payload: Dict[str, object]) -> Dict[str, object]:
        """向 DeepSeek 发送一次 JSON 对话请求。"""

        if not self.is_available():
            raise RuntimeError("DeepSeek client is not configured.")

        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        # 保留最后一次异常，便于重试结束后统一报错。
        last_error: Optional[Exception] = None
        for attempt in range(self.config.retry + 1):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.config.timeout,
                )
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                parsed["_provider_meta"] = {
                    "provider": "deepseek",
                    "model": self.config.model_name,
                    "attempt": attempt + 1,
                    "used_api": True,
                }
                return parsed
            except Exception as exc:  # pragma: no cover - network path
                last_error = exc
                time.sleep(min(1.0, 0.25 * (attempt + 1)))
        raise RuntimeError(f"DeepSeek request failed: {last_error}")
