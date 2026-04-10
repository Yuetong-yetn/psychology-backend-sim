"""Ollama API client for local chat-based JSON generation."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

import requests


@dataclass
class OllamaConfig:
    enabled: bool = False
    base_url: str = "http://127.0.0.1:11434"
    model_name: str = "llama3.1:8b-instruct"
    timeout: float = 30.0
    retry: int = 1

    @classmethod
    def from_env(cls) -> "OllamaConfig":
        return cls(
            enabled=os.getenv("OLLAMA_ENABLED", "0").lower() in {"1", "true", "yes"},
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            model_name=os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct"),
            timeout=float(os.getenv("OLLAMA_TIMEOUT", "30")),
            retry=int(os.getenv("OLLAMA_RETRY", "1")),
        )


class OllamaClient:
    """Tiny HTTP wrapper for Ollama `/api/chat`."""

    def __init__(self, config: Optional[OllamaConfig] = None) -> None:
        self.config = config or OllamaConfig.from_env()

    def is_available(self) -> bool:
        return bool(self.config.enabled and self.config.base_url and self.config.model_name)

    def chat_json(self, system_prompt: str, user_payload: Dict[str, object]) -> Dict[str, object]:
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
            "options": {"temperature": 0.2},
        }
        last_error: Optional[Exception] = None
        for attempt in range(self.config.retry + 1):
            try:
                response = requests.post(url, json=payload, timeout=self.config.timeout)
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
