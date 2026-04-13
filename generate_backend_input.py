#!/usr/bin/env python3
"""Generate native backend input data for local simulation runs."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from config.backend_settings import ENVIRONMENT_DEFAULTS, GENERATION_DEFAULTS
from config.frontend_settings import DEBUG_RUN_DEFAULTS


ROOT = Path(__file__).resolve().parent


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _signed(value: float, limit: float = 1.0) -> float:
    return max(-limit, min(limit, value))


def _build_agent(agent_id: int, rng: random.Random) -> dict[str, object]:
    personas = GENERATION_DEFAULTS.personas
    base_name, role, ideology, style = personas[agent_id % len(personas)]
    name = f"{base_name}_{agent_id}"
    support = _clip(rng.uniform(*GENERATION_DEFAULTS.support_tendency_range))
    threat = _clip(rng.uniform(*GENERATION_DEFAULTS.threat_sensitivity_range))
    efficacy = _clip(rng.uniform(*GENERATION_DEFAULTS.self_efficacy_range))
    return {
        "agent_id": agent_id,
        "name": name,
        "role": role,
        "ideology": ideology,
        "communication_style": style,
        "initial_state": {
            "emotion": round(_signed(rng.uniform(*GENERATION_DEFAULTS.emotion_range)), 4),
            "stress": round(_clip(rng.uniform(*GENERATION_DEFAULTS.stress_range)), 4),
            "expectation": round(_clip(rng.uniform(*GENERATION_DEFAULTS.expectation_range)), 4),
            "satisfaction": round(_signed(rng.uniform(*GENERATION_DEFAULTS.satisfaction_range)), 4),
            "dopamine_level": round(_clip(rng.uniform(*GENERATION_DEFAULTS.dopamine_range)), 4),
            "influence_score": round(_clip(rng.uniform(*GENERATION_DEFAULTS.influence_range)), 4),
            "schema_flexibility": round(_clip(rng.uniform(*GENERATION_DEFAULTS.schema_flexibility_range)), 4),
            "empathy_level": round(_clip(rng.uniform(*GENERATION_DEFAULTS.empathy_range)), 4),
            "schemas": {
                "support_tendency": round(support, 4),
                "threat_sensitivity": round(threat, 4),
                "self_efficacy": round(efficacy, 4),
            },
        },
    }


def _build_seed_post(author_id: int, round_index: int, topic: str, rng: random.Random) -> dict[str, object]:
    sentiment = _signed(rng.uniform(*GENERATION_DEFAULTS.seed_post_sentiment_range))
    intensity = _clip(
        abs(sentiment) * GENERATION_DEFAULTS.seed_post_intensity_scale
        + rng.uniform(*GENERATION_DEFAULTS.seed_post_extra_intensity_range)
    )
    if sentiment > 0.2:
        emotion = "confidence"
    elif sentiment < -0.35:
        emotion = "anger"
    elif sentiment < -0.12:
        emotion = "anxiety"
    else:
        emotion = "calm"

    content_templates = [
        f"Discussion around {topic} seems to ignore the long-term effects.",
        f"{topic} is clearly creating stronger polarization across the platform.",
        f"If people focus only on emotional reactions, debate about {topic} will become more extreme.",
        f"I care more about how {topic} affects ordinary people than about slogans.",
    ]
    return {
        "author_id": author_id,
        "content": rng.choice(content_templates),
        "emotion": emotion,
        "intensity": round(intensity, 4),
        "sentiment": round(sentiment, 4),
        "round_index": round_index,
    }


def build_payload(num_agents: int, rounds: int, seed_posts: int, seed: int) -> dict[str, object]:
    rng = random.Random(seed)
    topic = rng.choice(GENERATION_DEFAULTS.topics)
    scenario_id = f"scenario_{seed}"
    agents = [_build_agent(agent_id=index, rng=random.Random(seed + index * 101)) for index in range(num_agents)]

    relationships = []
    for index in range(num_agents):
        if num_agents <= 1:
            break
        forward = (index + 1) % num_agents
        if forward != index:
            relationships.append(
                {
                    "source_agent_id": index,
                    "target_agent_id": forward,
                    "type": "follow",
                }
            )
        if rng.random() < GENERATION_DEFAULTS.relationship_extra_follow_probability and num_agents > 2:
            alt = (index + 2) % num_agents
            if alt != index:
                relationships.append(
                    {
                        "source_agent_id": index,
                        "target_agent_id": alt,
                        "type": "follow",
                    }
                )

    seed_items = []
    for idx in range(seed_posts):
        author_id = idx % max(1, num_agents)
        seed_items.append(
            _build_seed_post(
                author_id=author_id,
                round_index=0,
                topic=topic,
                rng=random.Random(seed + idx * 313),
            )
        )

    return {
        "meta": {
            "description": "Native backend input data for environment, platform, and multi-agent simulation testing.",
            "num_agents": num_agents,
            "rounds": rounds,
            "seed_posts": seed_posts,
            "seed": seed,
        },
        "runtime": {
            "mode": DEBUG_RUN_DEFAULTS.mode,
            "llm_provider": DEBUG_RUN_DEFAULTS.llm_provider,
            "enable_fallback": DEBUG_RUN_DEFAULTS.enable_fallback,
            "feed_limit": DEBUG_RUN_DEFAULTS.feed_limit,
            "appraisal_llm_ratio": ENVIRONMENT_DEFAULTS.appraisal_llm_ratio,
        },
        "scenario": {
            "scenario_id": scenario_id,
            "title": f"Social issue: {topic}",
            "description": (
                f"Online public discussion around '{topic}' is heating up. "
                "Users keep encountering polarized viewpoints in their feeds and react to them."
            ),
            "environment_context": list(GENERATION_DEFAULTS.context_snippets),
        },
        "agents": agents,
        "relationships": relationships,
        "seed_posts": seed_items,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", type=int, default=DEBUG_RUN_DEFAULTS.num_agents)
    parser.add_argument("--rounds", type=int, default=DEBUG_RUN_DEFAULTS.rounds)
    parser.add_argument("--seed-posts", type=int, default=DEBUG_RUN_DEFAULTS.seed_posts)
    parser.add_argument("--seed", type=int, default=DEBUG_RUN_DEFAULTS.seed)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "examples" / "backend_sample_input.json",
    )
    args = parser.parse_args()

    payload = build_payload(
        num_agents=args.agents,
        rounds=args.rounds,
        seed_posts=args.seed_posts,
        seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {args.output} (agents={args.agents}, rounds={args.rounds}, seed_posts={args.seed_posts})",
        flush=True,
    )


if __name__ == "__main__":
    main()
