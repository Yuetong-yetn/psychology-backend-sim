"""火山引擎客户端封装。

提供带超时、重试和元信息记录的最小 HTTP 调用层。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

import requests


@dataclass
class VolcengineConfig:
    """火山引擎接口所需的配置。"""

    enabled: bool = False
    api_key: str = ""
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    model_name: str = ""
    timeout: float = 20.0
    retry: int = 1

    @classmethod
    def from_env(cls) -> "VolcengineConfig":
        """从环境变量构造火山引擎配置。"""

        enabled = os.getenv("VOLCENGINE_ENABLED", "0").lower() in {"1", "true", "yes"}
        return cls(
            enabled=enabled,
            api_key=os.getenv("VOLCENGINE_API_KEY", ""),
            base_url=os.getenv("VOLCENGINE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            model_name=os.getenv("VOLCENGINE_MODEL", ""),
            timeout=float(os.getenv("VOLCENGINE_TIMEOUT", "20")),
            retry=int(os.getenv("VOLCENGINE_RETRY", "1")),
        )


class VolcengineClient:
    """火山引擎的简易 HTTP 客户端。"""

    def __init__(self, config: Optional[VolcengineConfig] = None) -> None:
        """初始化客户端；默认从环境变量读取配置。"""

        self.config = config or VolcengineConfig.from_env()

    def is_available(self) -> bool:
        """判断当前配置是否足以发起请求。"""

        return bool(
            self.config.enabled
            and self.config.api_key
            and self.config.base_url
            and self.config.model_name
        )

    def chat_json(self, system_prompt: str, user_payload: Dict[str, object]) -> Dict[str, object]:
        """向火山引擎发送一次 JSON 对话请求。"""

        if not self.is_available():
            raise RuntimeError("Volcengine client is not configured.")

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
                    "provider": "volcengine",
                    "model": self.config.model_name,
                    "attempt": attempt + 1,
                    "used_api": True,
                }
                return parsed
            except Exception as exc:  # pragma: no cover - network path
                last_error = exc
                time.sleep(min(1.0, 0.25 * (attempt + 1)))
        raise RuntimeError(f"Volcengine request failed: {last_error}")
