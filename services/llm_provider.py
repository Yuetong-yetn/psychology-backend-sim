"""认知 Provider 统一调度层。

该模块负责组织 MoE-first 认知路径、外部 provider 调用、
缓存复用以及本地 fallback 回退逻辑。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from .deepseek_client import DeepSeekClient, DeepSeekConfig
from .ollama_client import OllamaClient, OllamaConfig


Payload = Dict[str, object]
FallbackFn = Callable[[Payload], Payload]


@dataclass
class CognitiveMoEConfig:
    """统一认知 Provider 的配置。"""

    mode: str = "moe"
    llm_provider: str = "ollama"
    enable_fallback: bool = True
    cache_dir: str = ""
    use_cache: bool = True

    @classmethod
    def from_env(
        cls,
        checkpoint_dir: Optional[str] = None,
        llm_provider: Optional[str] = None,
        mode: Optional[str] = None,
        enable_fallback: Optional[bool] = None,
    ) -> "CognitiveMoEConfig":
        """从环境变量和显式参数构造配置对象。"""
        cache_root = checkpoint_dir or os.getenv("BACKEND_CHECKPOINT_DIR", "")
        cache_dir = os.path.join(cache_root, "llm_cache") if cache_root else ""
        return cls(
            mode=mode or os.getenv("COGNITIVE_MODE", "moe"),
            llm_provider=llm_provider or os.getenv("LLM_PROVIDER_NAME", "ollama"),
            enable_fallback=(
                enable_fallback
                if enable_fallback is not None
                else os.getenv("LLM_ENABLE_FALLBACK", "1").lower() in {"1", "true", "yes"}
            ),
            cache_dir=cache_dir,
            use_cache=os.getenv("LLM_PROVIDER_USE_CACHE", "1").lower() in {"1", "true", "yes"},
        )


class LocalFallbackProvider:
    """本地回退 Provider。"""

    def __init__(self) -> None:
        """初始化本地回退 Provider。"""
        self.emotion_detector = None

    def generate_appraisal(self, payload: Payload, fallback_fn: Optional[FallbackFn] = None) -> Payload:
        """生成 appraisal 的本地回退结果。"""
        if fallback_fn is not None:
            return fallback_fn(payload)
        return {
            "relevance": 0.0,
            "valence": 0.0,
            "goal_conduciveness": 0.5,
            "controllability": 0.5,
            "certainty": 0.5,
            "coping_potential": 0.5,
            "agency": "external",
        }

    def analyze_emotion(self, payload: Payload, fallback_fn: Optional[FallbackFn] = None) -> Payload:
        """生成情绪分析的本地回退结果。"""
        if fallback_fn is not None:
            return fallback_fn(payload)
        if self.emotion_detector is None:
            # 延迟初始化，避免纯 appraisal 路径下不必要导入情绪模块。
            from social_platform.emotion_detector import CompositeEmotionDetector

            self.emotion_detector = CompositeEmotionDetector()
        text = str(payload.get("text", ""))
        internal_signal = payload.get("internal_signal")
        return self.emotion_detector.analyze_text(
            text,
            overrides={"internal_signal": internal_signal},
        ).to_dict()

    def build_latent(self, payload: Payload, fallback_fn: Optional[FallbackFn] = None) -> Payload:
        """生成 latent 的本地回退结果。"""
        if fallback_fn is not None:
            return fallback_fn(payload)
        return {"emotion_latent": _engineered_latent_from_payload(payload)}


class CognitiveMoEProvider:
    """统一的认知调度器。

    该类对上层暴露统一接口，并在内部处理：
    - `mode='moe'`：优先走外部 provider
    - `mode='fallback'`：直接走本地回退
    """

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        checkpoint_dir: Optional[str] = None,
        mode: str = "moe",
        enable_fallback: bool = True,
    ) -> None:
        """初始化认知调度器。

        Args:
            llm_provider: 外部 provider 名称。
            checkpoint_dir: 缓存目录根路径。
            mode: 认知模式。
            enable_fallback: 是否允许失败时自动回退。
        """
        self.config = CognitiveMoEConfig.from_env(
            checkpoint_dir=checkpoint_dir,
            llm_provider=llm_provider,
            mode=mode,
            enable_fallback=enable_fallback,
        )
        # `client` 代表外部 provider，`local_provider` 负责所有回退逻辑。
        self.client = self._build_client()
        self.local_provider = LocalFallbackProvider()

    def generate_appraisal(
        self,
        payload: Payload,
        fallback_fn: Optional[FallbackFn] = None,
    ) -> Payload:
        """生成 appraisal 结构。"""
        system_prompt = (
            "Return JSON only. Decompose the appraisal into experts and aggregate them. "
            "Top-level keys: router, experts, appraisal. "
            "router must contain weights for threat, support, coping, social. "
            "experts must contain threat, support, coping, social objects, each with keys "
            "relevance, valence, goal_conduciveness, controllability, certainty, coping_potential. "
            "appraisal must contain relevance, valence, goal_conduciveness, controllability, "
            "certainty, coping_potential, agency."
        )
        return self._request_with_fallback(
            task_name="generate_appraisal",
            system_prompt=system_prompt,
            payload=payload,
            source="moe_experts",
            fallback_runner=lambda current: self.local_provider.generate_appraisal(current, fallback_fn=fallback_fn),
        )

    def analyze_emotion(
        self,
        payload: Payload,
        fallback_fn: Optional[FallbackFn] = None,
    ) -> Payload:
        """生成情绪分析结构。"""
        system_prompt = (
            "Return JSON only. Decompose emotion analysis into experts and aggregate them. "
            "Top-level keys: experts, emotion. "
            "experts may include text_emotion, contagion, self_state. "
            "emotion must contain emotion_probs, dominant_emotion, intensity, sentiment, pad."
        )
        return self._request_with_fallback(
            task_name="analyze_emotion",
            system_prompt=system_prompt,
            payload=payload,
            source="moe_emotion",
            fallback_runner=lambda current: self.local_provider.analyze_emotion(current, fallback_fn=fallback_fn),
        )

    def build_latent(
        self,
        payload: Payload,
        fallback_fn: Optional[FallbackFn] = None,
    ) -> Payload:
        """生成情绪 latent 结构。"""
        system_prompt = (
            "Return JSON only. Produce compact structured semantic features for emotion latent construction. "
            "Top-level keys: experts, latent_features. "
            "latent_features should be a JSON object with low-dimensional semantic features, not a free-form high-dimensional vector."
        )
        return self._request_with_fallback(
            task_name="build_latent",
            system_prompt=system_prompt,
            payload=payload,
            source="moe_latent",
            fallback_runner=lambda current: self.local_provider.build_latent(current, fallback_fn=fallback_fn),
        )

    def _request_with_fallback(
        self,
        task_name: str,
        system_prompt: str,
        payload: Payload,
        source: str,
        fallback_runner: Callable[[Payload], Payload],
    ) -> Payload:
        """执行带缓存与回退逻辑的统一请求。"""
        if self.config.mode == "fallback":
            result = fallback_runner(payload)
            return self._attach_meta(
                result,
                mode="fallback",
                provider="local",
                source="local",
                fallback_used=True,
                fallback_reason="mode_forced_fallback",
                used_external=False,
                cache_hit=False,
            )

        cache_key = self._cache_key(task_name, payload)
        if self.config.use_cache:
            cached = self._load_cache(cache_key)
            if cached is not None:
                # 命中缓存时直接返回，避免重复请求外部模型。
                return self._attach_meta(
                    cached,
                    mode="moe",
                    provider=self.config.llm_provider,
                    source=source,
                    fallback_used=False,
                    fallback_reason=None,
                    used_external=False,
                    cache_hit=True,
                )

        if self.client.is_available():
            try:
                result = self.client.chat_json(system_prompt=system_prompt, user_payload=payload)
                if self.config.use_cache:
                    # 只缓存成功结果，避免把异常或空结果固化下来。
                    self._save_cache(cache_key, result)
                return self._attach_meta(
                    result,
                    mode="moe",
                    provider=self.config.llm_provider,
                    source=source,
                    fallback_used=False,
                    fallback_reason=None,
                    used_external=True,
                    cache_hit=False,
                )
            except Exception as exc:  # pragma: no cover - network path
                if self.config.enable_fallback:
                    # 外部 provider 失败时可自动回落到本地启发式路径。
                    result = fallback_runner(payload)
                    return self._attach_meta(
                        result,
                        mode="fallback",
                        provider="local",
                        source="local",
                        fallback_used=True,
                        fallback_reason=str(exc),
                        used_external=False,
                        cache_hit=False,
                    )
                return self._attach_meta(
                    {},
                    mode="moe",
                    provider=self.config.llm_provider,
                    source=source,
                    fallback_used=False,
                    fallback_reason=str(exc),
                    used_external=False,
                    cache_hit=False,
                )

        if self.config.enable_fallback:
            result = fallback_runner(payload)
            return self._attach_meta(
                result,
                mode="fallback",
                provider="local",
                source="local",
                fallback_used=True,
                fallback_reason="provider_unavailable",
                used_external=False,
                cache_hit=False,
            )

        return self._attach_meta(
            {},
            mode="moe",
            provider=self.config.llm_provider,
            source=source,
            fallback_used=False,
            fallback_reason="provider_unavailable",
            used_external=False,
            cache_hit=False,
        )

    def _attach_meta(
        self,
        payload: Payload,
        *,
        mode: str,
        provider: Optional[str],
        source: str,
        fallback_used: bool,
        fallback_reason: Optional[str],
        used_external: bool,
        cache_hit: bool,
    ) -> Payload:
        """为返回结果补充统一的 provider 元信息。"""
        result = dict(payload)
        result["_provider_meta"] = {
            "mode": mode,
            "provider": provider,
            "model": self._current_model_name() if provider == self.config.llm_provider else None,
            "source": source,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "used_external": used_external,
            "cache_hit": cache_hit,
        }
        return result

    def _build_client(self):
        """根据当前配置创建具体外部客户端。"""
        provider = self.config.llm_provider.lower()
        if provider == "deepseek":
            return DeepSeekClient(DeepSeekConfig.from_env())
        if provider == "ollama":
            return OllamaClient(OllamaConfig.from_env())
        raise ValueError(
            f"Unsupported llm_provider={self.config.llm_provider!r}. "
            "Use 'ollama' or 'deepseek'."
        )

    def _current_model_name(self) -> Optional[str]:
        """读取当前客户端对应的模型名称。"""
        config = getattr(self.client, "config", None)
        return getattr(config, "model_name", None)

    def _cache_key(self, task_name: str, payload: Payload) -> str:
        """生成当前请求的缓存键。"""
        digest = hashlib.sha256(
            (task_name + json.dumps(payload, ensure_ascii=False, sort_keys=True)).encode("utf-8")
        ).hexdigest()
        return digest

    def _load_cache(self, cache_key: str) -> Optional[Payload]:
        """从磁盘读取缓存结果。"""
        if not self.config.cache_dir:
            return None
        path = os.path.join(self.config.cache_dir, f"{cache_key}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save_cache(self, cache_key: str, payload: Payload) -> None:
        """将结果写入磁盘缓存。"""
        if not self.config.cache_dir:
            return
        os.makedirs(self.config.cache_dir, exist_ok=True)
        path = os.path.join(self.config.cache_dir, f"{cache_key}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)


def _engineered_latent_from_payload(payload: Payload) -> list[float]:
    """从结构化输入构造工程化 latent 向量。

    Args:
        payload: 情绪、appraisal、contagion 和 schema 摘要。

    Returns:
        固定长度的低维情绪 latent 向量。
    """
    latent_dim = 16
    emotion_probs = dict(payload.get("emotion_probs", {}))
    pad = list(payload.get("pad", [0.0, 0.0, 0.0]))
    sentiment = float(payload.get("sentiment", pad[0] if pad else 0.0))
    intensity = float(payload.get("intensity", 0.0))
    appraisal_summary = dict(payload.get("appraisal_summary", {}))
    contagion_summary = dict(payload.get("contagion_summary", {}))
    schema_summary = dict(payload.get("schema_summary", {}))
    labels = [
        "anger",
        "frustration",
        "anxiety",
        "fear",
        "guilt",
        "shame",
        "hope",
        "confidence",
        "relief",
        "calm",
    ]
    # 前 10 维是离散情绪概率，后面再拼接 PAD、appraisal、感染和 schema 摘要。
    features = [float(emotion_probs.get(label, 0.0)) for label in labels] + [
        float(pad[0] if len(pad) > 0 else sentiment),
        float(pad[1] if len(pad) > 1 else intensity),
        float(pad[2] if len(pad) > 2 else 0.0),
        float(sentiment),
        float(intensity),
        float(appraisal_summary.get("valence", sentiment)),
        float(appraisal_summary.get("control", 0.5)),
        float(appraisal_summary.get("certainty", 0.5)),
        float(contagion_summary.get("sentiment", 0.0)),
        float(contagion_summary.get("arousal", 0.0)),
        float(contagion_summary.get("amplification", 0.0)),
        float(schema_summary.get("support_bias", 0.0)),
        float(schema_summary.get("threat_bias", 0.5)),
        float(schema_summary.get("efficacy_bias", 0.5)),
    ]
    latent = [0.0] * latent_dim
    if len(features) >= 24:
        latent[0] = features[10]
        latent[1] = features[11]
        latent[2] = features[12]
        latent[3] = features[13]
        latent[4] = features[14]
        latent[5] = features[6] + features[7] + features[8]
        latent[6] = sum(features[0:6])
        latent[7] = features[9]
        latent[8] = features[15]
        latent[9] = features[16]
        latent[10] = features[17]
        latent[11] = features[18]
        latent[12] = features[19]
        latent[13] = features[21]
        latent[14] = features[22]
        latent[15] = features[23]
    return [float(item) for item in latent]


# Backward-compatible alias for existing imports.
LLMProvider = CognitiveMoEProvider
LLMProviderConfig = CognitiveMoEConfig
