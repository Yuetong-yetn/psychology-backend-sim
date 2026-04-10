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
from Backend.social_agent.emotion_representation import EmotionRepresentationConfig, EmotionRepresentationModule


def load_samples(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload.get("samples", payload)


def routed_vector(routed: Dict[str, Any]) -> np.ndarray:
    values = []
    for key in ["relevance", "valence", "goal_conduciveness", "controllability", "certainty", "coping_potential"]:
        total = 0.0
        for expert_name, expert_weight in routed["weights"].items():
            source = routed["outputs"][expert_name]
            total += float(expert_weight) * float(
                getattr(source, key, getattr(source, "goal_congruence", 0.5) if key == "goal_conduciveness" else 0.0)
            )
        values.append(total)
    return np.asarray(values, dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate heuristic/hybrid/learned scaffolds on a dataset.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--checkpoint-dir", default=None)
    args = parser.parse_args()

    samples = load_samples(args.input)
    heuristic_router = AppraisalRouter(AppraisalMoEConfig(mode="heuristic"))
    learned_router = AppraisalRouter(AppraisalMoEConfig(mode="learned", checkpoint_dir=args.checkpoint_dir))
    latent_engineered = EmotionRepresentationModule(EmotionRepresentationConfig(mode="engineered"))
    latent_learned = EmotionRepresentationModule(EmotionRepresentationConfig(mode="learned", checkpoint_dir=args.checkpoint_dir))

    diffs: List[float] = []
    latent_diffs: List[float] = []
    for sample in samples:
        emotion_state = sample.get("emotion_state", {})

        class EmotionProxy:
            signed_valence = float(emotion_state.get("signed_valence", 0.0))
            intensity = float(emotion_state.get("intensity", 0.0))
            pad = list(emotion_state.get("pad", [0.0, 0.0, 0.0]))

        heuristic = heuristic_router.evaluate(
            event=sample.get("event", {}),
            schemas=sample.get("schemas", {}),
            emotion_state=EmotionProxy(),
            stress=float(sample.get("stress", 0.0)),
            equilibrium=float(sample.get("equilibrium_index", sample.get("delta_eq", sample.get("equilibrium", 0.5)))),
            feed_features=sample.get("feed_features", {}),
            contagion_features=sample.get("contagion_features", {}),
            memory_summary=sample.get("memory_summary", {}),
        )
        learned = learned_router.evaluate(
            event=sample.get("event", {}),
            schemas=sample.get("schemas", {}),
            emotion_state=EmotionProxy(),
            stress=float(sample.get("stress", 0.0)),
            equilibrium=float(sample.get("equilibrium_index", sample.get("delta_eq", sample.get("equilibrium", 0.5)))),
            feed_features=sample.get("feed_features", {}),
            contagion_features=sample.get("contagion_features", {}),
            memory_summary=sample.get("memory_summary", {}),
        )
        heuristic_vec = routed_vector(heuristic)
        learned_vec = routed_vector(learned)
        diffs.append(float(np.mean(np.abs(heuristic_vec - learned_vec))))

        engineered_latent = latent_engineered.encode(
            emotion_probs=emotion_state.get("emotion_probs", {}),
            pad=emotion_state.get("pad", [0.0, 0.0, 0.0]),
            sentiment=float(emotion_state.get("signed_valence", 0.0)),
            intensity=float(emotion_state.get("intensity", 0.0)),
            contagion_summary=sample.get("contagion_features", {}),
            schema_summary={
                "support_bias": float(sample.get("schemas", {}).get("support_tendency", 0.5) * 2 - 1),
                "threat_bias": float(sample.get("schemas", {}).get("threat_sensitivity", 0.5)),
                "efficacy_bias": float(sample.get("schemas", {}).get("self_efficacy", 0.5)),
            },
        )
        learned_latent = latent_learned.encode(
            emotion_probs=emotion_state.get("emotion_probs", {}),
            pad=emotion_state.get("pad", [0.0, 0.0, 0.0]),
            sentiment=float(emotion_state.get("signed_valence", 0.0)),
            intensity=float(emotion_state.get("intensity", 0.0)),
            contagion_summary=sample.get("contagion_features", {}),
            schema_summary={
                "support_bias": float(sample.get("schemas", {}).get("support_tendency", 0.5) * 2 - 1),
                "threat_bias": float(sample.get("schemas", {}).get("threat_sensitivity", 0.5)),
                "efficacy_bias": float(sample.get("schemas", {}).get("self_efficacy", 0.5)),
            },
        )
        latent_diffs.append(float(np.mean(np.abs(np.asarray(engineered_latent) - np.asarray(learned_latent)))))

    print(
        json.dumps(
            {
                "num_samples": len(samples),
                "mean_appraisal_diff": float(np.mean(diffs) if diffs else 0.0),
                "mean_latent_diff": float(np.mean(latent_diffs) if latent_diffs else 0.0),
                "checkpoint_dir": args.checkpoint_dir,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
