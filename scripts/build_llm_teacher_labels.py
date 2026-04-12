from __future__ import annotations

"""为训练样本补充 LLM 教师标签。"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.llm_provider import LLMProvider


def load_samples(path: str) -> List[Dict[str, Any]]:
    """读取样本列表，兼容外层包裹 `samples` 字段的格式。"""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload.get("samples", payload)


def main() -> None:
    """命令行入口：批量生成教师标签。"""
    parser = argparse.ArgumentParser(description="Build cached LLM teacher labels for appraisal/emotion samples.")
    parser.add_argument("--input", required=True, help="Dataset JSON from build_training_dataset.py")
    parser.add_argument("--output", required=True, help="Path to write teacher labels JSON")
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of samples to label")
    parser.add_argument("--provider", default=None, help="Optional provider name override")
    parser.add_argument("--checkpoint-dir", default=None, help="Cache/checkpoint directory")
    args = parser.parse_args()

    provider = LLMProvider(provider_name=args.provider, checkpoint_dir=args.checkpoint_dir)
    samples = load_samples(args.input)
    labeled: List[Dict[str, Any]] = []
    for sample in samples[: args.limit]:
        appraisal_teacher = provider.generate_appraisal_teacher_label(sample)
        emotion_teacher = provider.analyze_emotion_semantics(sample)
        labeled.append(
            {
                "agent_id": sample.get("agent_id"),
                "round_index": sample.get("round_index"),
                "teacher_appraisal": appraisal_teacher,
                "teacher_emotion": emotion_teacher,
            }
        )

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump({"labels": labeled}, handle, ensure_ascii=False, indent=2)
    print(f"wrote {len(labeled)} teacher labels -> {args.output}")


if __name__ == "__main__":
    main()
