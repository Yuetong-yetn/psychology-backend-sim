"""Emotion latent generation with MoE-first mode and local fallback."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from Backend.services.llm_provider import CognitiveMoEProvider


LATENT_DIM = 16


@dataclass
class EmotionRepresentationConfig:
    mode: str = "moe"
    llm_provider_name: Optional[str] = "ollama"
    enable_fallback: bool = True
    latent_dim: int = LATENT_DIM
    checkpoint_dir: Optional[str] = None


class EmotionRepresentationModule:
    """Wrapper for moe-first latent generation with local engineered fallback."""

    def __init__(self, config: Optional[EmotionRepresentationConfig] = None) -> None:
        self.config = config or EmotionRepresentationConfig()
        self.provider = CognitiveMoEProvider(
            llm_provider=self.config.llm_provider_name,
            checkpoint_dir=self.config.checkpoint_dir,
            mode=self.config.mode,
            enable_fallback=self.config.enable_fallback,
        )
        self.last_run_metadata: Dict[str, object] = {
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
        fallback_latent = self._engineered_latent(
            emotion_probs=emotion_probs,
            pad=pad,
            sentiment=sentiment,
            intensity=intensity,
            appraisal_summary=appraisal_summary,
            contagion_summary=contagion_summary,
            schema_summary=schema_summary,
        )
        if self.config.mode == "fallback":
            self.last_run_metadata = {
                "mode": "fallback",
                "provider": "local",
                "model": None,
                "source": "local",
                "fallback_used": True,
                "fallback_reason": "mode_forced_fallback",
            }
            return fallback_latent

        payload = {
            "emotion_probs": emotion_probs,
            "pad": pad,
            "sentiment": sentiment,
            "intensity": intensity,
            "appraisal_summary": appraisal_summary or {},
            "contagion_summary": contagion_summary or {},
            "schema_summary": schema_summary or {},
            "text_context": text_context or {},
        }
        result = self.provider.build_latent(
            payload,
            fallback_fn=lambda _payload: {"emotion_latent": fallback_latent},
        )
        meta = result.get("_provider_meta", {})
        self.last_run_metadata = {
            "mode": str(meta.get("mode", "fallback")),
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "source": meta.get("source", "local"),
            "fallback_used": bool(meta.get("fallback_used", False)),
            "fallback_reason": meta.get("fallback_reason"),
        }
        latent = result.get("emotion_latent")
        if not isinstance(latent, list):
            return fallback_latent
        values = [float(item) for item in latent[: self.config.latent_dim]]
        if len(values) < self.config.latent_dim:
            values.extend([0.0] * (self.config.latent_dim - len(values)))
        return values

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
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
