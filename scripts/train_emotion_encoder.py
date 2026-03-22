from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
if PARENT_ROOT not in sys.path:
    sys.path.insert(0, PARENT_ROOT)

from Backend.social_agent.emotion_representation import EmotionRepresentationConfig, EmotionRepresentationModule


def load_samples(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload.get("samples", payload)


def fit_linear(x: np.ndarray, y: np.ndarray, ridge: float = 1e-3) -> tuple[np.ndarray, np.ndarray]:
    x_aug = np.concatenate([x, np.ones((x.shape[0], 1), dtype=np.float32)], axis=1)
    eye = np.eye(x_aug.shape[1], dtype=np.float32) * ridge
    weights = np.linalg.solve(x_aug.T @ x_aug + eye, x_aug.T @ y)
    return weights[:-1], weights[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Train local emotion encoder scaffold.")
    parser.add_argument("--input", required=True, help="Dataset JSON from build_training_dataset.py")
    parser.add_argument("--checkpoint-dir", required=True, help="Directory to save emotion encoder checkpoint")
    args = parser.parse_args()

    samples = load_samples(args.input)
    module = EmotionRepresentationModule(
        EmotionRepresentationConfig(mode="engineered", checkpoint_dir=args.checkpoint_dir)
    )

    x_rows: List[np.ndarray] = []
    y_rows: List[np.ndarray] = []
    for sample in samples:
        emotion_state = sample.get("emotion_state", {})
        target = list(emotion_state.get("latent", []))
        if not target:
            continue
        features = module.feature_vector(
            emotion_probs=emotion_state.get("emotion_probs", {}),
            pad=emotion_state.get("pad", [0.0, 0.0, 0.0]),
            sentiment=float(emotion_state.get("signed_valence", 0.0)),
            intensity=float(emotion_state.get("intensity", 0.0)),
            appraisal_summary={
                "valence": float(sample.get("appraisal_target_full", {}).get("valence", 0.0)),
                "control": float(sample.get("appraisal_target_full", {}).get("controllability", 0.5)),
                "certainty": float(sample.get("appraisal_target_full", {}).get("certainty", 0.5)),
            },
            contagion_summary=sample.get("contagion_features", {}),
            schema_summary={
                "support_bias": float(sample.get("schemas", {}).get("support_tendency", 0.5) * 2 - 1),
                "threat_bias": float(sample.get("schemas", {}).get("threat_sensitivity", 0.5)),
                "efficacy_bias": float(sample.get("schemas", {}).get("self_efficacy", 0.5)),
            },
        )
        x_rows.append(features)
        y_rows.append(np.asarray(target[: module.config.latent_dim], dtype=np.float32))

    x_mat = np.stack(x_rows)
    y_mat = np.stack(y_rows)
    weights, bias = fit_linear(x_mat, y_mat)
    os.makedirs(args.checkpoint_dir, exist_ok=True)
    path = module.save_checkpoint(weights.astype(np.float32), bias.astype(np.float32))
    print(f"saved emotion encoder checkpoint -> {path}")


if __name__ == "__main__":
    main()
