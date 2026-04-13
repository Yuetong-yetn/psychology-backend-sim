"""Ollama 客户端封装。

用于访问本地 Ollama 服务，并要求模型返回 JSON 结构。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

import requests


@dataclass
class OllamaConfig:
    """Ollama 服务的连接配置。"""

    enabled: bool = True
    base_url: str = "http://127.0.0.1:11434"
    model_name: str = "llama3.1:8b-instruct"
    timeout: float = 30.0
    retry: int = 0
    max_tokens: int = 800

    @classmethod
    def from_env(cls) -> "OllamaConfig":
        """从环境变量构造 Ollama 配置。"""

        base_url = os.getenv("OLLAMA_BASE_URL", cls.base_url).strip()
        model_name = os.getenv("OLLAMA_MODEL", cls.model_name).strip()
        explicit_enabled = os.getenv("OLLAMA_ENABLED", "").lower()
        enabled = (
            explicit_enabled in {"1", "true", "yes"}
            if explicit_enabled
            else bool(base_url and model_name)
        )

        return cls(
            enabled=enabled,
            base_url=base_url,
            model_name=model_name,
            timeout=float(os.getenv("OLLAMA_TIMEOUT", "30")),
            retry=int(os.getenv("OLLAMA_RETRY", "0")),
            max_tokens=int(os.getenv("OLLAMA_MAX_TOKENS", "800")),
        )


class OllamaClient:
    """Ollama 的简易 HTTP 客户端。"""

    def __init__(self, config: Optional[OllamaConfig] = None) -> None:
        """初始化客户端；默认从环境变量读取配置。"""

        self.config = config or OllamaConfig.from_env()
        self.session = requests.Session()

    def is_available(self) -> bool:
        """判断当前配置是否可用于请求本地服务。"""

        return bool(self.config.enabled and self.config.base_url and self.config.model_name)

    def chat_json(self, system_prompt: str, user_payload: Dict[str, object]) -> Dict[str, object]:
        """向 Ollama 发起一次 JSON 对话请求。"""

        if not self.is_available():
            raise RuntimeError("Ollama client is not configured.")

        url = self.config.base_url.rstrip("/") + "/api/chat"
        payload = {
            "model": self.config.model_name,
            "format": "json",
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "options": {"temperature": 0.2, "num_predict": self.config.max_tokens},
        }
        last_error: Optional[Exception] = None
        for attempt in range(self.config.retry + 1):
            try:
                response = self.session.post(url, json=payload, timeout=self.config.timeout)
                response.raise_for_status()
                body = response.json()
                content = body.get("message", {}).get("content", "{}")
                parsed = json.loads(content)
                parsed["_provider_meta"] = {
                    "provider": "ollama",
                    "model": self.config.model_name,
                    "attempt": attempt + 1,
                    "used_api": True,
                }
                return parsed
            except Exception as exc:  # pragma: no cover - network path
                last_error = exc
                time.sleep(min(1.0, 0.25 * (attempt + 1)))
        raise RuntimeError(f"Ollama request failed: {last_error}")
