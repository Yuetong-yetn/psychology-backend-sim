#!/usr/bin/env python3
"""Generate backend-native virtual input data for simulation testing."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parent

PERSONAS: list[tuple[str, str, str, str]] = [
    ("Alex", "journalist", "moderate", "analytical"),
    ("Bea", "artist", "progressive", "expressive"),
    ("Chen", "programmer", "conservative", "direct"),
    ("Dana", "teacher", "moderate", "empathetic"),
    ("Evan", "researcher", "progressive", "measured"),
    ("Faye", "designer", "moderate", "expressive"),
    ("Gao", "engineer", "conservative", "direct"),
    ("Hana", "caregiver", "progressive", "supportive"),
    ("Ivan", "product_manager", "moderate", "balanced"),
    ("Jia", "student", "progressive", "curious"),
]

TOPICS = [
    "城市公共预算调整",
    "平台内容审核新规",
    "高校 AI 教学试点",
    "本地交通票价优化",
    "社区夜间经济开放",
    "新能源车补贴变化",
]

CONTEXT_SNIPPETS = [
    "Public opinion is divided.",
    "Some users seek consensus while others amplify conflict.",
    "Posts with strong emotion receive higher visibility.",
    "Users can post, browse, reply, like, share, and influence each other.",
]


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _signed(value: float, limit: float = 1.0) -> float:
    return max(-limit, min(limit, value))


def _build_agent(agent_id: int, rng: random.Random) -> dict[str, object]:
    base_name, role, ideology, style = PERSONAS[agent_id % len(PERSONAS)]
    name = f"{base_name}_{agent_id}"
    support = _clip(rng.uniform(0.35, 0.75))
    threat = _clip(rng.uniform(0.25, 0.7))
    efficacy = _clip(rng.uniform(0.35, 0.8))
    return {
        "agent_id": agent_id,
        "name": name,
        "role": role,
        "ideology": ideology,
        "communication_style": style,
        "initial_state": {
            "emotion": round(_signed(rng.uniform(-0.25, 0.25)), 4),
            "stress": round(_clip(rng.uniform(0.12, 0.55)), 4),
            "expectation": round(_clip(rng.uniform(0.42, 0.72)), 4),
            "satisfaction": round(_signed(rng.uniform(-0.08, 0.12)), 4),
            "dopamine_level": round(_clip(rng.uniform(0.42, 0.68)), 4),
            "influence_score": round(_clip(rng.uniform(0.3, 0.7)), 4),
            "schema_flexibility": round(_clip(rng.uniform(0.35, 0.7)), 4),
            "empathy_level": round(_clip(rng.uniform(0.4, 0.78)), 4),
            "schemas": {
                "support_tendency": round(support, 4),
                "threat_sensitivity": round(threat, 4),
                "self_efficacy": round(efficacy, 4),
            },
        },
    }


def _build_seed_post(author_id: int, round_index: int, topic: str, rng: random.Random) -> dict[str, object]:
    sentiment = _signed(rng.uniform(-0.65, 0.75))
    intensity = _clip(abs(sentiment) * 0.65 + rng.uniform(0.08, 0.22))
    if sentiment > 0.2:
        emotion = "confidence"
    elif sentiment < -0.35:
        emotion = "anger"
    elif sentiment < -0.12:
        emotion = "anxiety"
    else:
        emotion = "calm"
    content_templates = [
        f"关于{topic}，我觉得平台上有不少讨论忽略了长期影响。",
        f"{topic} 这件事正在引发越来越明显的立场分化。",
        f"如果只看情绪表态，{topic} 的讨论会越来越极端。",
        f"我更关心 {topic} 对普通人的实际影响，而不是口号。",
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
    topic = rng.choice(TOPICS)
    scenario_id = f"scenario_{seed}"
    agents = [_build_agent(agent_id=index, rng=random.Random(seed + index * 101)) for index in range(num_agents)]
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
            "description": "当前后端原生输入数据，用于环境、平台与多 agent 仿真测试。",
            "num_agents": num_agents,
            "rounds": rounds,
            "seed_posts": seed_posts,
            "seed": seed,
        },
        "runtime": {
            "mode": "fallback",
            "llm_provider": "ollama",
            "enable_fallback": True,
            "feed_limit": 5,
        },
        "scenario": {
            "scenario_id": scenario_id,
            "title": f"社会议题：{topic}",
            "description": f"围绕“{topic}”的线上公共讨论持续升温，用户在信息流中不断接触分化观点并做出反应。",
            "environment_context": CONTEXT_SNIPPETS,
        },
        "agents": agents,
        "seed_posts": seed_items,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", type=int, default=12)
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--seed-posts", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
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
