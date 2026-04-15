from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from config.backend_settings import ENVIRONMENT_DEFAULTS
from config.frontend_settings import DEBUG_RUN_DEFAULTS


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "oasis_reddit"
DEFAULT_PROFILE_PATH = DATA_DIR / "user_data_36.json"
DEFAULT_PAIR_PATH = DATA_DIR / "counterfactual_36.json"
DEFAULT_MAPPING_CSV_PATH = DATA_DIR / "oasis_to_backend_mapping.csv"
DEFAULT_OUTPUT_PATH = ROOT / "examples" / "backend_sample_input.json"


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _signed(value: float, limit: float = 1.0) -> float:
    return max(-limit, min(limit, value))


def _stable_unit(*parts: object) -> float:
    joined = "::".join(str(item) for item in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _stable_range(lo: float, hi: float, *parts: object) -> float:
    return lo + (hi - lo) * _stable_unit(*parts)


def _load_profiles(path: Path = DEFAULT_PROFILE_PATH) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_pairs(path: Path = DEFAULT_PAIR_PATH) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_role(profession: str) -> str:
    return profession.lower().replace("&", "and").replace(",", "").replace(" ", "_")


def _infer_communication_style(profile: dict[str, object]) -> str:
    mbti = str(profile.get("mbti", "")).upper()
    text = f"{profile.get('bio', '')} {profile.get('persona', '')}".lower()
    if any(token in text for token in ("direct", "efficient", "structured", "methodical", "detail-oriented")):
        return "direct"
    if any(token in text for token in ("care", "compassion", "empathetic", "helping", "advocate", "social welfare")):
        return "supportive"
    if len(mbti) == 4 and mbti[2] == "T":
        return "analytical"
    if len(mbti) == 4 and mbti[2] == "F":
        return "empathetic"
    if len(mbti) == 4 and mbti[0] == "E":
        return "expressive"
    if len(mbti) == 4 and mbti[0] == "I":
        return "measured"
    return "balanced"


def _infer_ideology(profile: dict[str, object]) -> str:
    topics = [str(item).lower() for item in profile.get("interested_topics", [])]
    text = f"{profile.get('bio', '')} {profile.get('persona', '')} {' '.join(topics)}".lower()
    progressive_hits = sum(
        token in text
        for token in (
            "culture & society",
            "social",
            "change",
            "advocate",
            "welfare",
            "human services",
            "education",
        )
    )
    conservative_hits = sum(
        token in text
        for token in (
            "business",
            "economics",
            "finance",
            "security",
            "law",
            "public administration",
            "logistics",
        )
    )
    if progressive_hits > conservative_hits:
        return "progressive"
    if conservative_hits > progressive_hits:
        return "conservative"
    return "moderate"


def _mbti_dims(mbti: str) -> dict[str, float]:
    mbti = (mbti or "XXXX").upper()
    dims = {
        "extroversion": 0.64 if len(mbti) > 0 and mbti[0] == "E" else 0.42,
        "intuition": 0.64 if len(mbti) > 1 and mbti[1] == "N" else 0.44,
        "feeling": 0.68 if len(mbti) > 2 and mbti[2] == "F" else 0.4,
        "judging": 0.62 if len(mbti) > 3 and mbti[3] == "J" else 0.46,
    }
    return dims


def _build_initial_state(profile: dict[str, object], *, agent_id: int, seed: int) -> dict[str, object]:
    mbti = str(profile.get("mbti", ""))
    dims = _mbti_dims(mbti)
    age = int(profile.get("age", 30) or 30)
    profession = str(profile.get("profession", "")).lower()
    topics = [str(item).lower() for item in profile.get("interested_topics", [])]
    user_key = profile.get("username", f"user_{agent_id}")

    empathy = 0.4 + dims["feeling"] * 0.35
    if any(token in profession for token in ("human services", "education", "health", "care")):
        empathy += 0.08

    efficacy = 0.34 + dims["judging"] * 0.24 + (0.08 if "technology" in profession or "engineering" in profession else 0.0)
    support = 0.3 + dims["feeling"] * 0.3 + (0.08 if "culture & society" in topics or "fun" in topics else 0.0)
    threat = 0.24 + dims["judging"] * 0.18 + (0.12 if any(token in topics for token in ("politics", "general news", "law")) else 0.0)

    emotion = _signed(_stable_range(-0.16, 0.16, user_key, "emotion", seed))
    stress = _clip(0.15 + (1 - dims["intuition"]) * 0.12 + threat * 0.22 + _stable_range(0.0, 0.08, user_key, "stress", seed))
    expectation = _clip(0.42 + dims["extroversion"] * 0.12 + efficacy * 0.16 + _stable_range(-0.03, 0.03, user_key, "expectation", seed))
    satisfaction = _signed(_stable_range(-0.06, 0.1, user_key, "satisfaction", seed))
    dopamine_level = _clip(0.38 + dims["extroversion"] * 0.14 + _stable_range(0.0, 0.12, user_key, "dopamine", seed))
    influence_score = _clip(0.24 + min(age, 55) / 100 + dims["extroversion"] * 0.14 + _stable_range(0.0, 0.12, user_key, "influence", seed))
    schema_flexibility = _clip(0.3 + dims["intuition"] * 0.24 + (0.1 if len(mbti) > 3 and mbti[3] == "P" else 0.0))
    empathy_level = _clip(empathy + _stable_range(0.0, 0.06, user_key, "empathy", seed))

    return {
        "emotion": round(emotion, 4),
        "stress": round(stress, 4),
        "expectation": round(expectation, 4),
        "satisfaction": round(satisfaction, 4),
        "dopamine_level": round(dopamine_level, 4),
        "influence_score": round(influence_score, 4),
        "schema_flexibility": round(schema_flexibility, 4),
        "empathy_level": round(empathy_level, 4),
        "schemas": {
            "support_tendency": round(_clip(support), 4),
            "threat_sensitivity": round(_clip(threat), 4),
            "self_efficacy": round(_clip(efficacy), 4),
        },
    }


def _build_agent(profile: dict[str, object], *, agent_id: int, seed: int) -> dict[str, object]:
    return {
        "agent_id": agent_id,
        "name": str(profile.get("username") or profile.get("realname") or f"agent_{agent_id}"),
        "role": _normalize_role(str(profile.get("profession", "reddit_user"))),
        "ideology": _infer_ideology(profile),
        "communication_style": _infer_communication_style(profile),
        "initial_state": _build_initial_state(profile, agent_id=agent_id, seed=seed),
    }


def _relationship_score(source: dict[str, object], target: dict[str, object], seed: int) -> float:
    if source is target:
        return -1.0
    source_topics = {str(item) for item in source.get("interested_topics", [])}
    target_topics = {str(item) for item in target.get("interested_topics", [])}
    shared_topics = len(source_topics & target_topics)
    same_country = float(source.get("country") == target.get("country"))
    same_mbti_prefix = float(str(source.get("mbti", ""))[:2] == str(target.get("mbti", ""))[:2])
    profession_bonus = float(source.get("profession") == target.get("profession"))
    noise = _stable_range(0.0, 0.05, source.get("username"), target.get("username"), seed, "rel")
    return shared_topics * 0.55 + same_country * 0.18 + same_mbti_prefix * 0.1 + profession_bonus * 0.12 + noise


def _build_relationships(profiles: list[dict[str, object]], *, seed: int) -> list[dict[str, object]]:
    relationships: list[dict[str, object]] = []
    for index, source in enumerate(profiles):
        candidates: list[tuple[float, int]] = []
        for target_index, target in enumerate(profiles):
            if index == target_index:
                continue
            score = _relationship_score(source, target, seed)
            candidates.append((score, target_index))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        selected = [target_index for score, target_index in candidates[:2] if score >= 0.6]
        if not selected and candidates:
            selected = [candidates[0][1]]
        for target_index in selected:
            relationships.append(
                {
                    "source_agent_id": index,
                    "target_agent_id": target_index,
                    "type": "follow",
                }
            )
    return relationships


def _topic_counter(profiles: list[dict[str, object]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for profile in profiles:
        counter.update(str(item) for item in profile.get("interested_topics", []))
    return counter


def _topic_to_slug(topic: str) -> str:
    return topic.lower().replace("&", "and").replace(" ", "_")


def _build_scenario(profiles: list[dict[str, object]], *, seed: int) -> dict[str, object]:
    topic_counts = _topic_counter(profiles)
    top_topics = [item for item, _ in topic_counts.most_common(3)] or ["General News"]
    primary_topic = top_topics[0]
    return {
        "scenario_id": f"oasis_reddit_{seed}",
        "title": f"Reddit discussion around {primary_topic}",
        "description": (
            f"Agents are initialized from OASIS Reddit profiles and discuss topics such as "
            f"{', '.join(top_topics)} on a shared social platform."
        ),
        "environment_context": [
            "User profiles come from the OASIS Reddit dataset.",
            "Seed posts are mapped from OASIS counterfactual Reddit pairs.",
            "Follow relationships are inferred from shared topics, profession, MBTI, and country.",
            "Agent psychological states are derived deterministically from profile traits.",
        ],
        "topic_slug": _topic_to_slug(primary_topic),
    }


def _map_group_to_signal(group: str) -> tuple[str, float, float]:
    normalized = group.lower()
    if normalized == "up":
        return "confidence", 0.58, 0.64
    if normalized == "down":
        return "anger", -0.56, 0.7
    return "calm", 0.04, 0.3


def _build_seed_posts(
    pairs: list[dict[str, object]],
    profiles: list[dict[str, object]],
    *,
    seed_posts: int,
    seed: int,
) -> list[dict[str, object]]:
    rng = random.Random(seed)
    items = list(pairs)
    rng.shuffle(items)
    selected = items[: min(seed_posts, len(items))]
    posts: list[dict[str, object]] = []
    for index, pair in enumerate(selected):
        source = dict(pair.get("RS", {}))
        response = dict(pair.get("RC_1", {}))
        emotion, sentiment, intensity = _map_group_to_signal(str(response.get("group", "control")))
        content = str(source.get("selftext") or response.get("body") or "").strip()
        if not content:
            content = str(response.get("body", ""))
        posts.append(
            {
                "author_id": index % max(1, len(profiles)),
                "content": content,
                "emotion": emotion,
                "intensity": round(intensity, 4),
                "sentiment": round(sentiment, 4),
                "round_index": 0,
            }
        )
    return posts


def build_payload(
    num_agents: int,
    rounds: int,
    seed_posts: int,
    seed: int,
    *,
    profile_path: Path = DEFAULT_PROFILE_PATH,
    pair_path: Path = DEFAULT_PAIR_PATH,
) -> dict[str, object]:
    profiles = _load_profiles(profile_path)
    pairs = _load_pairs(pair_path)
    selected_profiles = profiles[: min(num_agents, len(profiles))]
    if not selected_profiles:
        raise ValueError(f"No OASIS profiles found in {profile_path}")

    scenario = _build_scenario(selected_profiles, seed=seed)
    agents = [
        _build_agent(profile, agent_id=index, seed=seed)
        for index, profile in enumerate(selected_profiles)
    ]
    relationships = _build_relationships(selected_profiles, seed=seed)
    seed_items = _build_seed_posts(
        pairs,
        selected_profiles,
        seed_posts=seed_posts,
        seed=seed,
    )

    scenario.pop("topic_slug", None)
    return {
        "meta": {
            "description": "Backend input converted from OASIS Reddit profiles and Reddit pair data.",
            "num_agents": len(selected_profiles),
            "rounds": rounds,
            "seed_posts": len(seed_items),
            "seed": seed,
            "source_dataset": {
                "profiles": str(profile_path.relative_to(ROOT)),
                "pairs": str(pair_path.relative_to(ROOT)),
            },
        },
        "runtime": {
            "mode": DEBUG_RUN_DEFAULTS.mode,
            "llm_provider": DEBUG_RUN_DEFAULTS.llm_provider,
            "enable_fallback": DEBUG_RUN_DEFAULTS.enable_fallback,
            "feed_limit": DEBUG_RUN_DEFAULTS.feed_limit,
            "appraisal_llm_ratio": ENVIRONMENT_DEFAULTS.appraisal_llm_ratio,
        },
        "scenario": scenario,
        "agents": agents,
        "relationships": relationships,
        "seed_posts": seed_items,
    }


def write_mapping_csv(path: Path = DEFAULT_MAPPING_CSV_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        ("realname", "agents[].name", "fallback", "Use username first; fall back to realname when username is empty.", "Backend name prefers handle-like identifiers."),
        ("username", "agents[].name", "direct", "Copied directly into Backend agent name.", "Matches platform-facing identity."),
        ("profession", "agents[].role", "derived", "Lowercase and normalize to underscore-separated role.", "Backend expects a compact role token."),
        ("interested_topics + persona", "agents[].ideology", "derived", "Heuristic mapping into progressive/conservative/moderate.", "No direct ideology field exists in OASIS."),
        ("mbti + bio + persona", "agents[].communication_style", "derived", "Rule-based mapping into analytical/direct/empathetic/expressive/measured/supportive/balanced.", "Backend requires a discrete style label."),
        ("age + mbti + profession + interested_topics", "agents[].initial_state.schemas.support_tendency", "derived", "Deterministic heuristic score.", "No direct psychological schema exists in OASIS."),
        ("age + mbti + profession + interested_topics", "agents[].initial_state.schemas.threat_sensitivity", "derived", "Deterministic heuristic score.", "No direct psychological schema exists in OASIS."),
        ("age + mbti + profession + interested_topics", "agents[].initial_state.schemas.self_efficacy", "derived", "Deterministic heuristic score.", "No direct psychological schema exists in OASIS."),
        ("mbti + profession + seed", "agents[].initial_state.emotion", "derived", "Stable hash-based value in Backend numeric range.", "OASIS has no scalar initial emotion field."),
        ("mbti + profession + interested_topics + seed", "agents[].initial_state.stress", "derived", "Stable heuristic score.", "Backend requires structured initial stress."),
        ("mbti + profession + seed", "agents[].initial_state.expectation", "derived", "Stable heuristic score.", "Backend requires structured expectation."),
        ("mbti + profession + seed", "agents[].initial_state.satisfaction", "derived", "Stable heuristic score.", "Backend requires structured satisfaction."),
        ("mbti + profession + seed", "agents[].initial_state.dopamine_level", "derived", "Stable heuristic score.", "Backend requires structured dopamine level."),
        ("age + mbti + profession + seed", "agents[].initial_state.influence_score", "derived", "Stable heuristic score.", "Backend requires structured influence score."),
        ("mbti + seed", "agents[].initial_state.schema_flexibility", "derived", "Stable heuristic score.", "Backend requires structured schema flexibility."),
        ("mbti + profession + seed", "agents[].initial_state.empathy_level", "derived", "Stable heuristic score.", "Backend requires structured empathy level."),
        ("shared interested_topics + same country + MBTI similarity + profession", "relationships[]", "derived", "Generate follow edges by pairwise affinity scoring.", "OASIS source JSON does not include a ready-made Reddit follow graph."),
        ("RS.selftext", "seed_posts[].content", "direct", "Copy as seed post content; fall back to RC_1.body when empty.", "Preserves OASIS post text."),
        ("RC_1.group", "seed_posts[].emotion/sentiment/intensity", "derived", "Map up/down/control to confidence/anger/calm signals.", "Backend requires structured affect metadata."),
        ("interested_topics aggregate", "scenario.title/description", "derived", "Use top shared topics among selected profiles.", "Backend requires a single scenario block."),
        ("bio", "unused_direct", "unused", "Retained in copied raw dataset only.", "Not injected directly into Backend payload."),
        ("persona", "unused_direct", "unused", "Used indirectly for style and ideology inference.", "Too verbose for direct structured insertion."),
        ("gender", "unused_direct", "unused", "Not consumed by current Backend schema.", "Available in copied OASIS raw JSON."),
        ("country", "unused_direct", "unused", "Used indirectly for relationship inference only.", "Not a direct Backend field."),
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("source_field", "backend_target", "mapping_type", "transform_rule", "notes"))
        writer.writerows(rows)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert copied OASIS Reddit data into Backend input files.")
    parser.add_argument("--agents", type=int, default=DEBUG_RUN_DEFAULTS.num_agents)
    parser.add_argument("--rounds", type=int, default=DEBUG_RUN_DEFAULTS.rounds)
    parser.add_argument("--seed-posts", type=int, default=DEBUG_RUN_DEFAULTS.seed_posts)
    parser.add_argument("--seed", type=int, default=DEBUG_RUN_DEFAULTS.seed)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--mapping-csv", type=Path, default=DEFAULT_MAPPING_CSV_PATH)
    args = parser.parse_args()

    payload = build_payload(
        num_agents=args.agents,
        rounds=args.rounds,
        seed_posts=args.seed_posts,
        seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    mapping_path = write_mapping_csv(args.mapping_csv)
    print(f"Wrote backend payload to {args.output}")
    print(f"Wrote mapping CSV to {mapping_path}")


if __name__ == "__main__":
    main()
