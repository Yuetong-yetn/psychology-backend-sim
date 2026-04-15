#!/usr/bin/env python3
"""Build a frontend handoff SQLite database from existing backend JSON artifacts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "examples" / "backend_sample_input.json"
DEFAULT_OUTPUT_CANDIDATES = [
    ROOT / "outputs" / "backend_sample_output.json",
    ROOT / "outputs" / "simulation_snapshot.json",
    ROOT / "outputs" / "test_snapshot.json",
]
DEFAULT_DB = ROOT / "psychology_backend_frontend.db"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _bool(value: Any) -> int:
    return 1 if bool(value) else 0


def _resolve_snapshot_path() -> Path:
    for candidate in DEFAULT_OUTPUT_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No backend snapshot JSON file was found in outputs/.")


def _reset_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;

        DROP TABLE IF EXISTS input_meta;
        DROP TABLE IF EXISTS input_runtime;
        DROP TABLE IF EXISTS input_scenario;
        DROP TABLE IF EXISTS input_agents;
        DROP TABLE IF EXISTS input_relationships;
        DROP TABLE IF EXISTS input_seed_posts;

        DROP TABLE IF EXISTS snapshot_info;
        DROP TABLE IF EXISTS snapshot_debug;
        DROP TABLE IF EXISTS platform_snapshot;
        DROP TABLE IF EXISTS platform_posts;
        DROP TABLE IF EXISTS platform_replies;
        DROP TABLE IF EXISTS platform_likes;
        DROP TABLE IF EXISTS platform_shares;
        DROP TABLE IF EXISTS platform_influence_events;
        DROP TABLE IF EXISTS platform_traces;
        DROP TABLE IF EXISTS agent_graph_info;
        DROP TABLE IF EXISTS agent_graph_edges;
        DROP TABLE IF EXISTS agent_snapshots;
        DROP TABLE IF EXISTS round_history;
        DROP TABLE IF EXISTS round_results;

        CREATE TABLE input_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            description TEXT NOT NULL,
            num_agents INTEGER NOT NULL,
            rounds INTEGER NOT NULL,
            seed_posts INTEGER NOT NULL,
            seed INTEGER NOT NULL,
            debug_run_config_json TEXT
        );

        CREATE TABLE input_runtime (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            mode TEXT NOT NULL,
            llm_provider TEXT NOT NULL,
            enable_fallback INTEGER NOT NULL,
            feed_limit INTEGER NOT NULL,
            appraisal_llm_ratio REAL NOT NULL
        );

        CREATE TABLE input_scenario (
            scenario_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            environment_context_json TEXT NOT NULL
        );

        CREATE TABLE input_agents (
            agent_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            ideology TEXT NOT NULL,
            communication_style TEXT NOT NULL,
            emotion REAL NOT NULL,
            stress REAL NOT NULL,
            expectation REAL NOT NULL,
            satisfaction REAL NOT NULL,
            dopamine_level REAL NOT NULL,
            influence_score REAL NOT NULL,
            schema_flexibility REAL NOT NULL,
            empathy_level REAL NOT NULL,
            schemas_json TEXT NOT NULL
        );

        CREATE TABLE input_relationships (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_agent_id INTEGER NOT NULL,
            target_agent_id INTEGER NOT NULL,
            type TEXT NOT NULL
        );

        CREATE TABLE input_seed_posts (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            emotion TEXT NOT NULL,
            intensity REAL NOT NULL,
            sentiment REAL NOT NULL,
            round_index INTEGER NOT NULL
        );

        CREATE TABLE snapshot_info (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            round_index INTEGER NOT NULL,
            scenario_prompt TEXT NOT NULL,
            export_path TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE snapshot_debug (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            exposed_frontend_params_json TEXT NOT NULL,
            provider_behavior_json TEXT NOT NULL,
            why_results_appear_without_api_key TEXT NOT NULL,
            auto_run_on_snapshot INTEGER NOT NULL,
            history_rounds INTEGER NOT NULL,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE platform_snapshot (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_round INTEGER NOT NULL,
            scenario_prompt TEXT NOT NULL,
            agent_count INTEGER NOT NULL,
            agents_json TEXT NOT NULL,
            trace_size INTEGER NOT NULL,
            runtime_profile_json TEXT NOT NULL
        );

        CREATE TABLE platform_posts (
            post_id INTEGER PRIMARY KEY,
            author_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            emotion TEXT NOT NULL,
            dominant_emotion TEXT NOT NULL,
            intensity REAL NOT NULL,
            sentiment REAL NOT NULL,
            emotion_probs_json TEXT NOT NULL,
            pad_json TEXT NOT NULL,
            emotion_latent_json TEXT NOT NULL,
            like_count INTEGER NOT NULL,
            share_count INTEGER NOT NULL,
            shared_post_id INTEGER,
            round_index INTEGER NOT NULL
        );

        CREATE TABLE platform_replies (
            reply_id INTEGER PRIMARY KEY,
            post_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            emotion TEXT NOT NULL,
            dominant_emotion TEXT NOT NULL,
            intensity REAL NOT NULL,
            sentiment REAL NOT NULL,
            emotion_probs_json TEXT NOT NULL,
            pad_json TEXT NOT NULL,
            emotion_latent_json TEXT NOT NULL,
            round_index INTEGER NOT NULL
        );

        CREATE TABLE platform_likes (
            like_id INTEGER PRIMARY KEY,
            post_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            round_index INTEGER NOT NULL
        );

        CREATE TABLE platform_shares (
            share_id INTEGER PRIMARY KEY,
            post_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            round_index INTEGER NOT NULL
        );

        CREATE TABLE platform_influence_events (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_index INTEGER NOT NULL,
            source_agent_id INTEGER NOT NULL,
            target_agent_id INTEGER NOT NULL,
            delta REAL NOT NULL,
            reason TEXT NOT NULL
        );

        CREATE TABLE platform_traces (
            trace_index INTEGER PRIMARY KEY,
            type TEXT NOT NULL,
            round_index INTEGER,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE agent_graph_info (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            num_nodes INTEGER NOT NULL,
            num_edges INTEGER NOT NULL
        );

        CREATE TABLE agent_graph_edges (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_agent_id INTEGER NOT NULL,
            target_agent_id INTEGER NOT NULL
        );

        CREATE TABLE agent_snapshots (
            agent_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            ideology TEXT NOT NULL,
            communication_style TEXT NOT NULL,
            emotion REAL NOT NULL,
            emotion_state_json TEXT NOT NULL,
            stress REAL NOT NULL,
            expectation REAL NOT NULL,
            satisfaction REAL NOT NULL,
            dopamine_level REAL NOT NULL,
            performance_prediction REAL NOT NULL,
            influence_score REAL NOT NULL,
            schemas_json TEXT NOT NULL,
            schema_flexibility REAL NOT NULL,
            equilibrium_index REAL NOT NULL,
            last_cognitive_mode TEXT NOT NULL,
            dominant_emotion_label TEXT NOT NULL,
            empathy_level REAL NOT NULL,
            empathized_negative_emotion REAL NOT NULL,
            dopamine_prediction_error REAL NOT NULL,
            moral_reward REAL NOT NULL,
            social_influence_reward REAL NOT NULL,
            semantic_similarity REAL NOT NULL,
            explicit_tom_triggered INTEGER NOT NULL,
            beliefs_json TEXT NOT NULL,
            desires_json TEXT NOT NULL,
            intentions_json TEXT NOT NULL,
            knowledge_json TEXT NOT NULL,
            epsilon REAL NOT NULL,
            zeta REAL NOT NULL,
            coping_potential REAL NOT NULL,
            performance REAL NOT NULL,
            confirmation REAL NOT NULL,
            last_appraisal_json TEXT,
            last_contagion_pad_json TEXT NOT NULL,
            last_contagion_vector_json TEXT NOT NULL,
            appraisal_runtime_json TEXT NOT NULL,
            latent_runtime_json TEXT NOT NULL,
            action_runtime_json TEXT NOT NULL,
            memory_size INTEGER NOT NULL,
            appraisal_count INTEGER NOT NULL
        );

        CREATE TABLE round_history (
            round_index INTEGER PRIMARY KEY
        );

        CREATE TABLE round_results (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_index INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            profile_name TEXT NOT NULL,
            profile_role TEXT NOT NULL,
            profile_ideology TEXT NOT NULL,
            profile_communication_style TEXT NOT NULL,
            state_json TEXT NOT NULL,
            decision_action TEXT NOT NULL,
            decision_content TEXT NOT NULL,
            decision_target_post_id INTEGER,
            decision_target_agent_id INTEGER,
            decision_metadata_json TEXT NOT NULL,
            decision_influence_delta REAL NOT NULL,
            decision_reason TEXT NOT NULL,
            decision_suggested_action TEXT NOT NULL,
            decision_suggested_actions_json TEXT NOT NULL,
            behavior_primary_action TEXT NOT NULL,
            behavior_stimulus_excerpt TEXT NOT NULL,
            behavior_public_behavior_summary TEXT NOT NULL,
            behavior_simulated_public_content TEXT,
            behavior_state_hint_json TEXT NOT NULL,
            behavior_cam_summary_json TEXT NOT NULL,
            behavior_explicit_tom_triggered INTEGER NOT NULL,
            behavior_backend_action TEXT NOT NULL,
            behavior_round_index INTEGER NOT NULL,
            UNIQUE (round_index, agent_id)
        );
        """
    )


def _insert_input_payload(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    meta = dict(payload.get("meta", {}))
    runtime = dict(payload.get("runtime", {}))
    scenario = dict(payload.get("scenario", {}))

    conn.execute(
        """
        INSERT INTO input_meta (
            id, description, num_agents, rounds, seed_posts, seed, debug_run_config_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            str(meta.get("description", "")),
            int(meta.get("num_agents", 0)),
            int(meta.get("rounds", 0)),
            int(meta.get("seed_posts", 0)),
            int(meta.get("seed", 0)),
            _json(meta.get("debugRunConfig")) if "debugRunConfig" in meta else None,
        ),
    )

    conn.execute(
        """
        INSERT INTO input_runtime (
            id, mode, llm_provider, enable_fallback, feed_limit, appraisal_llm_ratio
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            str(runtime.get("mode", "")),
            str(runtime.get("llm_provider", "")),
            _bool(runtime.get("enable_fallback", False)),
            int(runtime.get("feed_limit", 0)),
            float(runtime.get("appraisal_llm_ratio", 0.0)),
        ),
    )

    conn.execute(
        """
        INSERT INTO input_scenario (
            scenario_id, title, description, environment_context_json
        ) VALUES (?, ?, ?, ?)
        """,
        (
            str(scenario.get("scenario_id", "")),
            str(scenario.get("title", "")),
            str(scenario.get("description", "")),
            _json(scenario.get("environment_context", [])),
        ),
    )

    for row in payload.get("agents", []):
        state = dict(row.get("initial_state", {}))
        conn.execute(
            """
            INSERT INTO input_agents (
                agent_id, name, role, ideology, communication_style,
                emotion, stress, expectation, satisfaction, dopamine_level,
                influence_score, schema_flexibility, empathy_level, schemas_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(row["agent_id"]),
                str(row.get("name", "")),
                str(row.get("role", "")),
                str(row.get("ideology", "")),
                str(row.get("communication_style", "")),
                float(state.get("emotion", 0.0)),
                float(state.get("stress", 0.0)),
                float(state.get("expectation", 0.0)),
                float(state.get("satisfaction", 0.0)),
                float(state.get("dopamine_level", 0.0)),
                float(state.get("influence_score", 0.0)),
                float(state.get("schema_flexibility", 0.0)),
                float(state.get("empathy_level", 0.0)),
                _json(state.get("schemas", {})),
            ),
        )

    for row in payload.get("relationships", []):
        conn.execute(
            """
            INSERT INTO input_relationships (source_agent_id, target_agent_id, type)
            VALUES (?, ?, ?)
            """,
            (
                int(row.get("source_agent_id", 0)),
                int(row.get("target_agent_id", 0)),
                str(row.get("type", "")),
            ),
        )

    for row in payload.get("seed_posts", []):
        conn.execute(
            """
            INSERT INTO input_seed_posts (
                author_id, content, emotion, intensity, sentiment, round_index
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(row.get("author_id", 0)),
                str(row.get("content", "")),
                str(row.get("emotion", "")),
                float(row.get("intensity", 0.0)),
                float(row.get("sentiment", 0.0)),
                int(row.get("round_index", 0)),
            ),
        )


def _insert_snapshot(conn: sqlite3.Connection, snapshot: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO snapshot_info (id, round_index, scenario_prompt, export_path, raw_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            1,
            int(snapshot.get("round_index", 0)),
            str(snapshot.get("scenario_prompt", "")),
            snapshot.get("export_path"),
            _json(snapshot),
        ),
    )

    debug = snapshot.get("_debug")
    if isinstance(debug, dict):
        conn.execute(
            """
            INSERT INTO snapshot_debug (
                id, exposed_frontend_params_json, provider_behavior_json,
                why_results_appear_without_api_key, auto_run_on_snapshot,
                history_rounds, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                _json(debug.get("exposedFrontendParams", [])),
                _json(debug.get("providerBehavior", {})),
                str(debug.get("whyResultsAppearWithoutApiKey", "")),
                _bool(debug.get("autoRunOnSnapshot", False)),
                int(debug.get("historyRounds", 0)),
                _json(debug),
            ),
        )

    platform = dict(snapshot.get("platform", {}))
    conn.execute(
        """
        INSERT INTO platform_snapshot (
            id, current_round, scenario_prompt, agent_count,
            agents_json, trace_size, runtime_profile_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            int(platform.get("current_round", 0)),
            str(platform.get("scenario_prompt", "")),
            int(platform.get("agent_count", 0)),
            _json(platform.get("agents", {})),
            int(platform.get("trace_size", 0)),
            _json(platform.get("runtime_profile", {})),
        ),
    )

    for row in platform.get("posts", []):
        conn.execute(
            """
            INSERT INTO platform_posts (
                post_id, author_id, content, emotion, dominant_emotion,
                intensity, sentiment, emotion_probs_json, pad_json,
                emotion_latent_json, like_count, share_count,
                shared_post_id, round_index
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(row["post_id"]),
                int(row.get("author_id", 0)),
                str(row.get("content", "")),
                str(row.get("emotion", "")),
                str(row.get("dominant_emotion", "")),
                float(row.get("intensity", 0.0)),
                float(row.get("sentiment", 0.0)),
                _json(row.get("emotion_probs", {})),
                _json(row.get("pad", [])),
                _json(row.get("emotion_latent", [])),
                int(row.get("like_count", 0)),
                int(row.get("share_count", 0)),
                row.get("shared_post_id"),
                int(row.get("round_index", 0)),
            ),
        )

    for row in platform.get("replies", []):
        conn.execute(
            """
            INSERT INTO platform_replies (
                reply_id, post_id, author_id, content, emotion, dominant_emotion,
                intensity, sentiment, emotion_probs_json, pad_json,
                emotion_latent_json, round_index
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(row["reply_id"]),
                int(row.get("post_id", 0)),
                int(row.get("author_id", 0)),
                str(row.get("content", "")),
                str(row.get("emotion", "")),
                str(row.get("dominant_emotion", "")),
                float(row.get("intensity", 0.0)),
                float(row.get("sentiment", 0.0)),
                _json(row.get("emotion_probs", {})),
                _json(row.get("pad", [])),
                _json(row.get("emotion_latent", [])),
                int(row.get("round_index", 0)),
            ),
        )

    for row in platform.get("likes", []):
        conn.execute(
            """
            INSERT INTO platform_likes (like_id, post_id, agent_id, round_index)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(row["like_id"]),
                int(row.get("post_id", 0)),
                int(row.get("agent_id", 0)),
                int(row.get("round_index", 0)),
            ),
        )

    for row in platform.get("shares", []):
        conn.execute(
            """
            INSERT INTO platform_shares (share_id, post_id, agent_id, round_index)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(row["share_id"]),
                int(row.get("post_id", 0)),
                int(row.get("agent_id", 0)),
                int(row.get("round_index", 0)),
            ),
        )

    for row in platform.get("influence_events", []):
        conn.execute(
            """
            INSERT INTO platform_influence_events (
                round_index, source_agent_id, target_agent_id, delta, reason
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(row.get("round_index", 0)),
                int(row.get("source_agent_id", 0)),
                int(row.get("target_agent_id", 0)),
                float(row.get("delta", 0.0)),
                str(row.get("reason", "")),
            ),
        )

    for index, row in enumerate(platform.get("traces", [])):
        conn.execute(
            """
            INSERT INTO platform_traces (trace_index, type, round_index, raw_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                index,
                str(row.get("type", "")),
                row.get("round_index"),
                _json(row),
            ),
        )

    graph = dict(snapshot.get("agent_graph", {}))
    conn.execute(
        """
        INSERT INTO agent_graph_info (id, num_nodes, num_edges)
        VALUES (?, ?, ?)
        """,
        (
            1,
            int(graph.get("num_nodes", 0)),
            int(graph.get("num_edges", 0)),
        ),
    )
    for edge in graph.get("edges", []):
        if isinstance(edge, list | tuple) and len(edge) == 2:
            conn.execute(
                "INSERT INTO agent_graph_edges (source_agent_id, target_agent_id) VALUES (?, ?)",
                (int(edge[0]), int(edge[1])),
            )

    for row in snapshot.get("agents", []):
        profile = dict(row.get("profile", {}))
        state = dict(row.get("state", {}))
        conn.execute(
            """
            INSERT INTO agent_snapshots (
                agent_id, name, role, ideology, communication_style,
                emotion, emotion_state_json, stress, expectation, satisfaction,
                dopamine_level, performance_prediction, influence_score, schemas_json,
                schema_flexibility, equilibrium_index, last_cognitive_mode,
                dominant_emotion_label, empathy_level, empathized_negative_emotion,
                dopamine_prediction_error, moral_reward, social_influence_reward,
                semantic_similarity, explicit_tom_triggered, beliefs_json,
                desires_json, intentions_json, knowledge_json, epsilon, zeta,
                coping_potential, performance, confirmation, last_appraisal_json,
                last_contagion_pad_json, last_contagion_vector_json,
                appraisal_runtime_json, latent_runtime_json, action_runtime_json,
                memory_size, appraisal_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(profile.get("agent_id", 0)),
                str(profile.get("name", "")),
                str(profile.get("role", "")),
                str(profile.get("ideology", "")),
                str(profile.get("communication_style", "")),
                float(state.get("emotion", 0.0)),
                _json(state.get("emotion_state", {})),
                float(state.get("stress", 0.0)),
                float(state.get("expectation", 0.0)),
                float(state.get("satisfaction", 0.0)),
                float(state.get("dopamine_level", 0.0)),
                float(state.get("performance_prediction", 0.0)),
                float(state.get("influence_score", 0.0)),
                _json(state.get("schemas", {})),
                float(state.get("schema_flexibility", 0.0)),
                float(state.get("equilibrium_index", 0.0)),
                str(state.get("last_cognitive_mode", "")),
                str(state.get("dominant_emotion_label", "")),
                float(state.get("empathy_level", 0.0)),
                float(state.get("empathized_negative_emotion", 0.0)),
                float(state.get("dopamine_prediction_error", 0.0)),
                float(state.get("moral_reward", 0.0)),
                float(state.get("social_influence_reward", 0.0)),
                float(state.get("semantic_similarity", 0.0)),
                _bool(state.get("explicit_tom_triggered", False)),
                _json(state.get("beliefs", {})),
                _json(state.get("desires", {})),
                _json(state.get("intentions", {})),
                _json(state.get("knowledge", {})),
                float(state.get("epsilon", 0.0)),
                float(state.get("zeta", 0.0)),
                float(state.get("coping_potential", 0.0)),
                float(state.get("performance", 0.0)),
                float(state.get("confirmation", 0.0)),
                _json(state.get("last_appraisal")) if state.get("last_appraisal") is not None else None,
                _json(state.get("last_contagion_pad", [])),
                _json(state.get("last_contagion_vector", [])),
                _json(state.get("appraisal_runtime", {})),
                _json(state.get("latent_runtime", {})),
                _json(state.get("action_runtime", {})),
                int(state.get("memory_size", 0)),
                int(state.get("appraisal_count", 0)),
            ),
        )

    for row in snapshot.get("history", []):
        round_index = int(row.get("round_index", 0))
        conn.execute(
            "INSERT INTO round_history (round_index) VALUES (?)",
            (round_index,),
        )
        results = dict(row.get("results", {}))
        for agent_id_key, result in results.items():
            profile = dict(result.get("profile", {}))
            state = dict(result.get("state", {}))
            decision = dict(result.get("decision", {}))
            behavior = dict(result.get("behavior_output", {}))
            conn.execute(
                """
                INSERT INTO round_results (
                    round_index, agent_id, profile_name, profile_role,
                    profile_ideology, profile_communication_style, state_json,
                    decision_action, decision_content, decision_target_post_id,
                    decision_target_agent_id, decision_metadata_json,
                    decision_influence_delta, decision_reason,
                    decision_suggested_action, decision_suggested_actions_json,
                    behavior_primary_action, behavior_stimulus_excerpt,
                    behavior_public_behavior_summary,
                    behavior_simulated_public_content, behavior_state_hint_json,
                    behavior_cam_summary_json,
                    behavior_explicit_tom_triggered, behavior_backend_action,
                    behavior_round_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    round_index,
                    int(profile.get("agent_id", agent_id_key)),
                    str(profile.get("name", "")),
                    str(profile.get("role", "")),
                    str(profile.get("ideology", "")),
                    str(profile.get("communication_style", "")),
                    _json(state),
                    str(decision.get("action", "")),
                    str(decision.get("content", "")),
                    decision.get("target_post_id"),
                    decision.get("target_agent_id"),
                    _json(decision.get("metadata", {})),
                    float(decision.get("influence_delta", 0.0)),
                    str(decision.get("reason", "")),
                    str(decision.get("suggested_action", "")),
                    _json(decision.get("suggested_actions", [])),
                    str(behavior.get("primary_action", "")),
                    str(behavior.get("stimulus_excerpt", "")),
                    str(behavior.get("public_behavior_summary", "")),
                    behavior.get("simulated_public_content"),
                    _json(behavior.get("state_hint", {})),
                    _json(behavior.get("cam_summary", [])),
                    _bool(behavior.get("explicit_tom_triggered", False)),
                    str(behavior.get("backend_action", "")),
                    int(behavior.get("round_index", round_index)),
                ),
            )


def build_database(
    input_path: Path = DEFAULT_INPUT,
    snapshot_path: Path | None = None,
    db_path: Path = DEFAULT_DB,
) -> Path:
    snapshot_path = snapshot_path or _resolve_snapshot_path()
    payload = _load_json(input_path)
    snapshot = _load_json(snapshot_path)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        _reset_schema(conn)
        _insert_input_payload(conn, payload)
        _insert_snapshot(conn, snapshot)
        conn.commit()
    finally:
        conn.close()
    return db_path


if __name__ == "__main__":
    db_path = build_database()
    print(db_path)
