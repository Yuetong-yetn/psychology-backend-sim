"""情绪 latent 表示模块。

优先支持 MoE/外部 provider，也保留本地可回退的工程化编码方案。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from services.llm_provider import CognitiveMoEProvider


LATENT_DIM = 16


@dataclass
class EmotionRepresentationConfig:
    """情绪表示模块的运行配置。"""

    mode: str = "moe"
    llm_provider_name: Optional[str] = "ollama"
    enable_fallback: bool = True
    latent_dim: int = LATENT_DIM
    checkpoint_dir: Optional[str] = None


class EmotionRepresentationModule:
    """情绪 latent 生成器，支持外部推理与本地回退。"""

    def __init__(self, config: Optional[EmotionRepresentationConfig] = None) -> None:
        self.config = config or EmotionRepresentationConfig()
        self.provider = CognitiveMoEProvider(
            llm_provider=self.config.llm_provider_name,
            checkpoint_dir=self.config.checkpoint_dir,
            mode=self.config.mode,
            enable_fallback=self.config.enable_fallback,
        )
        self.last_run_metadata: Dict[str, object] = {
            # 记录最近一次编码到底走了外部 provider 还是本地回退。
            "mode": self.config.mode,
            "provider": None,
            "model": None,
            "source": "local",
            "fallback_used": False,
            "fallback_reason": None,
        }

    def encode(
        self,
        emotion_probs: Dict[str, float],
        pad: List[float],
        sentiment: float,
        intensity: float,
        appraisal_summary: Optional[Dict[str, float]] = None,
        contagion_summary: Optional[Dict[str, float]] = None,
        schema_summary: Optional[Dict[str, float]] = None,
        text_context: Optional[Dict[str, object]] = None,
    ) -> List[float]:
        """把情绪分布、PAD 和摘要特征编码为 latent 向量。"""

        fallback_latent = self._engineered_latent(
            emotion_probs=emotion_probs,
            pad=pad,
            sentiment=sentiment,
            intensity=intensity,
            appraisal_summary=appraisal_summary,
            contagion_summary=contagion_summary,
            schema_summary=schema_summary,
        )
        self.last_run_metadata = {
            "mode": "local_only",
            "provider": "local",
            "model": None,
            "source": "engineered_latent",
            "fallback_used": False,
            "fallback_reason": None,
        }
        return fallback_latent

    def feature_vector(
        self,
        emotion_probs: Dict[str, float],
        pad: List[float],
        sentiment: float,
        intensity: float,
        appraisal_summary: Optional[Dict[str, float]] = None,
        contagion_summary: Optional[Dict[str, float]] = None,
        schema_summary: Optional[Dict[str, float]] = None,
    ) -> np.ndarray:
        """把输入压成固定长度的数值特征向量。"""

        appraisal_summary = appraisal_summary or {}
        contagion_summary = contagion_summary or {}
        schema_summary = schema_summary or {}
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
        return np.asarray(features, dtype=np.float32)

    def _engineered_latent(
        self,
        emotion_probs: Dict[str, float],
        pad: List[float],
        sentiment: float,
        intensity: float,
        appraisal_summary: Optional[Dict[str, float]],
        contagion_summary: Optional[Dict[str, float]],
        schema_summary: Optional[Dict[str, float]],
    ) -> List[float]:
        """使用固定投影构造本地工程化 latent。"""

        feature_vector = self.feature_vector(
            emotion_probs=emotion_probs,
            pad=pad,
            sentiment=sentiment,
            intensity=intensity,
            appraisal_summary=appraisal_summary,
            contagion_summary=contagion_summary,
            schema_summary=schema_summary,
        )
        fixed_projection = np.asarray([[0.0] * feature_vector.shape[0] for _ in range(self.config.latent_dim)], dtype=np.float32)
        fixed_projection[0, 10] = 1.0
        fixed_projection[1, 11] = 1.0
        fixed_projection[2, 12] = 1.0
        fixed_projection[3, 13] = 1.0
        fixed_projection[4, 14] = 1.0
        fixed_projection[5, 6] = 1.0
        fixed_projection[5, 7] = 1.0
        fixed_projection[5, 8] = 1.0
        fixed_projection[6, 0] = 1.0
        fixed_projection[6, 1] = 1.0
        fixed_projection[6, 2] = 1.0
        fixed_projection[6, 3] = 1.0
        fixed_projection[6, 4] = 1.0
        fixed_projection[6, 5] = 1.0
        fixed_projection[7, 9] = 1.0
        fixed_projection[8, 15] = 1.0
        fixed_projection[9, 16] = 1.0
        fixed_projection[10, 17] = 1.0
        fixed_projection[11, 18] = 1.0
        fixed_projection[12, 19] = 1.0
        fixed_projection[13, 21] = 1.0
        fixed_projection[14, 22] = 1.0
        fixed_projection[15, 23] = 1.0
        latent = fixed_projection @ feature_vector
        return [float(item) for item in latent.tolist()]


def save_encoder_metadata(output_path: str, payload: Dict[str, object]) -> None:
    """把编码器元信息落盘到 JSON 文件。"""

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
