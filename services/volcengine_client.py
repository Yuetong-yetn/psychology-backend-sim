"""Volcengine API client with graceful fallback behavior."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

import requests


@dataclass
class VolcengineConfig:
    enabled: bool = False
    api_key: str = ""
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    model_name: str = ""
    timeout: float = 20.0
    retry: int = 1

    @classmethod
    def from_env(cls) -> "VolcengineConfig":
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
    """Tiny HTTP client wrapper with timeout/retry and metadata."""

    def __init__(self, config: Optional[VolcengineConfig] = None) -> None:
        self.config = config or VolcengineConfig.from_env()

    def is_available(self) -> bool:
        return bool(
            self.config.enabled
            and self.config.api_key
            and self.config.base_url
            and self.config.model_name
        )

    def chat_json(self, system_prompt: str, user_payload: Dict[str, object]) -> Dict[str, object]:
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
