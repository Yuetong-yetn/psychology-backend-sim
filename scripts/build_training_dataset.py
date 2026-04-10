from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
if PARENT_ROOT not in sys.path:
    sys.path.insert(0, PARENT_ROOT)


def load_snapshot(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def appraisal_vector(appraisal: Dict[str, Any]) -> List[float]:
    return [
        float(appraisal.get("relevance", 0.0)),
        float(appraisal.get("valence", 0.0)),
        float(appraisal.get("goal_conduciveness", appraisal.get("goal_congruence", 0.5))),
        float(appraisal.get("controllability", 0.5)),
        float(appraisal.get("certainty", 0.5)),
        float(appraisal.get("coping_potential", 0.5)),
    ]


def infer_event_from_appraisal(appraisal: Dict[str, Any]) -> Dict[str, float]:
    valence = float(appraisal.get("valence", 0.0))
    novelty = float(appraisal.get("novelty", 0.0))
    relevance = float(appraisal.get("relevance", 0.0))
    certainty = float(appraisal.get("certainty", 0.5))
    return {
        "direction": valence,
        "risk": max(0.0, min(1.0, relevance * 0.55 + max(0.0, -valence) * 0.25 + novelty * 0.2)),
        "novelty": novelty,
        "consistency": max(0.0, min(1.0, certainty)),
    }


def infer_feed_features(state: Dict[str, Any]) -> Dict[str, float]:
    contagion_pad = state.get("last_contagion_pad", [0.0, 0.0, 0.0])
    contagion_vector = state.get("last_contagion_vector", [0.0] * 16)
    return {
        "direction": float(contagion_pad[0] if len(contagion_pad) > 0 else 0.0),
        "exposure_pressure": float(abs(contagion_pad[0]) * 0.3 + (contagion_pad[1] if len(contagion_pad) > 1 else 0.0) * 0.4),
        "exposure_polarity": float(contagion_pad[0] if len(contagion_pad) > 0 else 0.0),
        "consensus": max(0.0, min(1.0, 1.0 - abs(float(contagion_vector[4] if len(contagion_vector) > 4 else 0.0) - float(contagion_vector[3] if len(contagion_vector) > 3 else 0.0)))),
        "dispersion": max(0.0, min(1.0, abs(float(contagion_vector[4] if len(contagion_vector) > 4 else 0.0) - float(contagion_vector[3] if len(contagion_vector) > 3 else 0.0)))),
        "engagement": float(min(1.0, len(state.get("memory", [])) * 0.08)),
    }


def infer_memory_summary(state: Dict[str, Any]) -> Dict[str, float]:
    memory = state.get("memory", [])
    if not memory:
        return {
            "valence_bias": 0.0,
            "coherence": 0.5,
            "feed_ratio": 0.0,
            "self_generated_ratio": 0.0,
            "salience": 0.0,
        }
    valences = [float(item.get("valence", 0.0)) for item in memory]
    feed_ratio = sum(1 for item in memory if item.get("source") == "feed") / len(memory)
    self_ratio = sum(1 for item in memory if str(item.get("source", "")).startswith("self")) / len(memory)
    spread = max(valences) - min(valences) if len(valences) > 1 else 0.0
    return {
        "valence_bias": sum(valences) / len(valences),
        "coherence": max(0.0, min(1.0, 1.0 - spread * 0.5)),
        "feed_ratio": max(0.0, min(1.0, feed_ratio)),
        "self_generated_ratio": max(0.0, min(1.0, self_ratio)),
        "salience": max(0.0, min(1.0, sum(abs(v) for v in valences) / len(valences))),
    }


def build_samples(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    history = snapshot.get("history", [])
    for round_entry in history:
        results = round_entry.get("results", [])
        if isinstance(results, dict):
            iterable = results.values()
        else:
            iterable = results
        for result in iterable:
            state = result.get("state", {})
            appraisal = state.get("last_appraisal")
            if not appraisal:
                continue
            emotion_state = state.get("emotion_state", {})
            sample = {
                "agent_id": result.get("profile", {}).get("agent_id"),
                "round_index": round_entry.get("round_index"),
                "event": infer_event_from_appraisal(appraisal),
                "schemas": dict(state.get("schemas", {})),
                "emotion_state": {
                    "signed_valence": float(state.get("emotion", 0.0)),
                    "intensity": float(emotion_state.get("intensity", abs(state.get("emotion", 0.0)))),
                    "pad": list(emotion_state.get("pad", [0.0, 0.0, 0.0])),
                    "latent": list(emotion_state.get("latent", [])),
                    "emotion_probs": dict(emotion_state.get("emotion_probs", {})),
                },
                "stress": float(state.get("stress", 0.0)),
                "equilibrium_index": float(state.get("equilibrium_index", state.get("delta_eq", state.get("equilibrium", 0.5)))),
                "feed_features": infer_feed_features(state),
                "contagion_features": {
                    "sentiment": float((state.get("last_contagion_pad", [0.0, 0.0, 0.0]) or [0.0])[0]),
                    "arousal": float((state.get("last_contagion_pad", [0.0, 0.0, 0.0]) or [0.0, 0.0])[1] if len(state.get("last_contagion_pad", [0.0, 0.0, 0.0])) > 1 else 0.0),
                    "amplification": float((state.get("last_contagion_vector", [0.0] * 16) or [0.0] * 16)[12] if len(state.get("last_contagion_vector", [])) > 12 else 0.0),
                },
                "memory_summary": infer_memory_summary(state),
                "appraisal_target": appraisal_vector(appraisal),
                "appraisal_target_full": appraisal,
                "decision": result.get("decision", {}),
            }
            samples.append(sample)
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Build trainable samples from simulation snapshot.")
    parser.add_argument("--input", required=True, help="Path to exported simulation snapshot JSON.")
    parser.add_argument("--output", required=True, help="Path to write dataset JSON.")
    args = parser.parse_args()

    snapshot = load_snapshot(args.input)
    samples = build_samples(snapshot)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump({"samples": samples}, handle, ensure_ascii=False, indent=2)
    print(f"built {len(samples)} samples -> {args.output}")


if __name__ == "__main__":
    main()
