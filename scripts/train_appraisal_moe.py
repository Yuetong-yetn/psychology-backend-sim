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

from Backend.social_agent.appraisal_moe import AppraisalMoEConfig, AppraisalRouter


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
    parser = argparse.ArgumentParser(description="Train numpy appraisal MoE scaffold from heuristic/teacher labels.")
    parser.add_argument("--input", required=True, help="Dataset JSON from build_training_dataset.py")
    parser.add_argument("--checkpoint-dir", required=True, help="Directory to save appraisal_moe_checkpoint.npz")
    args = parser.parse_args()

    samples = load_samples(args.input)
    router = AppraisalRouter(AppraisalMoEConfig(mode="heuristic", checkpoint_dir=args.checkpoint_dir))
    learned = router.learned_moe

    x_rows: List[np.ndarray] = []
    y_rows: List[np.ndarray] = []
    gate_rows: List[np.ndarray] = []
    for sample in samples:
        emotion_state = sample.get("emotion_state", {})
        class EmotionProxy:
            signed_valence = float(emotion_state.get("signed_valence", 0.0))
            intensity = float(emotion_state.get("intensity", 0.0))
            pad = list(emotion_state.get("pad", [0.0, 0.0, 0.0]))

        x = learned.vectorize(
            event=sample.get("event", {}),
            schemas=sample.get("schemas", {}),
            emotion_state=EmotionProxy(),
            stress=float(sample.get("stress", 0.0)),
            equilibrium=float(sample.get("equilibrium", 0.5)),
            feed_features=sample.get("feed_features", {}),
            contagion_features=sample.get("contagion_features", {}),
            memory_summary=sample.get("memory_summary", {}),
        )
        routed = router.route(
            event=sample.get("event", {}),
            schemas=sample.get("schemas", {}),
            emotion_state=EmotionProxy(),
            stress=float(sample.get("stress", 0.0)),
            equilibrium=float(sample.get("equilibrium", 0.5)),
            feed_features=sample.get("feed_features", {}),
            contagion_features=sample.get("contagion_features", {}),
            memory_summary=sample.get("memory_summary", {}),
        )
        x_rows.append(x)
        y_rows.append(np.asarray(sample.get("appraisal_target", [0.0] * 6), dtype=np.float32))
        gate_rows.append(
            np.asarray(
                [
                    float(routed.get("threat", 0.25)),
                    float(routed.get("support", 0.25)),
                    float(routed.get("coping", 0.25)),
                    float(routed.get("social", 0.25)),
                ],
                dtype=np.float32,
            )
        )

    x_mat = np.stack(x_rows)
    y_mat = np.stack(y_rows)
    gate_mat = np.stack(gate_rows)

    router_w, router_b = fit_linear(x_mat, gate_mat)
    expert_weights = np.zeros((learned.num_experts, learned.input_dim, learned.output_dim), dtype=np.float32)
    expert_bias = np.zeros((learned.num_experts, learned.output_dim), dtype=np.float32)
    for expert_index in range(learned.num_experts):
        w, b = fit_linear(x_mat, y_mat)
        expert_weights[expert_index] = w
        expert_bias[expert_index] = b

    os.makedirs(args.checkpoint_dir, exist_ok=True)
    path = learned.save_checkpoint(router_w.astype(np.float32), router_b.astype(np.float32), expert_weights, expert_bias)
    print(f"saved appraisal MoE checkpoint -> {path}")


if __name__ == "__main__":
    main()
