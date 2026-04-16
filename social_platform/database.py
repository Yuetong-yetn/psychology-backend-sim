from __future__ import annotations

import json
import os
import os.path as osp
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List

SCHEMA_DIR = "social_platform/schema"
DB_NAME = "psychology_backend_frontend.db"

SCHEMA_FILES = [
    "input_meta.sql",
    "input_runtime.sql",
    "input_scenario.sql",
    "input_agents.sql",
    "input_relationships.sql",
    "input_seed_posts.sql",
    "snapshot_info.sql",
    "snapshot_debug.sql",
    "platform_snapshot.sql",
    "platform_posts.sql",
    "platform_replies.sql",
    "platform_likes.sql",
    "platform_shares.sql",
    "platform_influence_events.sql",
    "platform_traces.sql",
    "agent_graph_info.sql",
    "agent_graph_edges.sql",
    "agent_snapshots.sql",
    "round_history.sql",
    "round_results.sql",
]

TABLE_NAMES = {
    "input_meta",
    "input_runtime",
    "input_scenario",
    "input_agents",
    "input_relationships",
    "input_seed_posts",
    "snapshot_info",
    "snapshot_debug",
    "platform_snapshot",
    "platform_posts",
    "platform_replies",
    "platform_likes",
    "platform_shares",
    "platform_influence_events",
    "platform_traces",
    "agent_graph_info",
    "agent_graph_edges",
    "agent_snapshots",
    "round_history",
    "round_results",
}

DROP_TABLES_IN_ORDER = [
    "round_results",
    "round_history",
    "agent_snapshots",
    "agent_graph_edges",
    "agent_graph_info",
    "platform_traces",
    "platform_influence_events",
    "platform_shares",
    "platform_likes",
    "platform_replies",
    "platform_posts",
    "platform_snapshot",
    "snapshot_debug",
    "snapshot_info",
    "input_seed_posts",
    "input_relationships",
    "input_agents",
    "input_scenario",
    "input_runtime",
    "input_meta",
]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _bool(value: Any) -> int:
    return 1 if bool(value) else 0


def get_db_path() -> str:
    env_db_path = os.environ.get("PSYCHOLOGY_DB_PATH")
    if env_db_path:
        return env_db_path

    curr_file_path = osp.abspath(__file__)
    backend_dir = osp.dirname(osp.dirname(curr_file_path))
    return osp.join(backend_dir, DB_NAME)


def get_schema_dir_path() -> str:
    curr_file_path = osp.abspath(__file__)
    backend_dir = osp.dirname(osp.dirname(curr_file_path))
    return osp.join(backend_dir, SCHEMA_DIR)


def _iter_schema_paths(schema_dir: str | None = None) -> Iterable[Path]:
    resolved_dir = Path(schema_dir or get_schema_dir_path())
    for schema_name in SCHEMA_FILES:
        yield resolved_dir / schema_name


def _execute_schema_scripts(conn: sqlite3.Connection, schema_dir: str | None = None) -> None:
    for schema_path in _iter_schema_paths(schema_dir):
        with schema_path.open("r", encoding="utf-8") as sql_file:
            conn.executescript(sql_file.read())


def create_db(db_path: str | None = None) -> tuple[sqlite3.Connection, sqlite3.Cursor]:
    target_path = Path(db_path or get_db_path())
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target_path)
    cursor = conn.cursor()
    try:
        _execute_schema_scripts(conn)
        conn.commit()
    except sqlite3.Error:
        conn.close()
        raise
    return conn, cursor


def reset_db(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF;")
    for table_name in DROP_TABLES_IN_ORDER:
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
    conn.commit()


def fetch_table_from_db(cursor: sqlite3.Cursor, table_name: str) -> List[Dict[str, Any]]:
    cursor.execute(f"SELECT * FROM {table_name}")
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def print_db_tables_summary(db_path: str | None = None) -> None:
    conn = sqlite3.connect(db_path or get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    for (table_name,) in cursor.fetchall():
        if table_name not in TABLE_NAMES:
            continue
        print(f"Table: {table_name}")
        cursor.execute(f"PRAGMA table_info({table_name})")
        print("- Columns:", [column[1] for column in cursor.fetchall()])
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 3;")
        for row in cursor.fetchall():
            print(row)
        print()
    conn.close()


def insert_input_payload(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
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


def insert_snapshot(conn: sqlite3.Connection, snapshot: dict[str, Any]) -> None:
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
                simulation_config_json, agent_runtime_summary_json,
                why_results_appear_without_api_key, auto_run_on_snapshot,
                history_rounds, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                _json(debug.get("exposedFrontendParams", [])),
                _json(debug.get("providerBehavior", {})),
                _json(debug.get("simulation_config", {})),
                _json(debug.get("agent_runtime_summary", {})),
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
        if isinstance(edge, (list, tuple)) and len(edge) == 2:
            conn.execute(
                "INSERT INTO agent_graph_edges (source_agent_id, target_agent_id) VALUES (?, ?)",
                (int(edge[0]), int(edge[1])),
            )

    for row in snapshot.get("agents", []):
        profile = dict(row.get("profile", {}))
        state = dict(row.get("state", {}))
        debug_state = dict(state.get("_debug", {}))
        # Deprecated flattened debug columns are intentionally not written as
        # active table columns. Restore them from state_debug_json if needed.
        conn.execute(
            """
            INSERT INTO agent_snapshots (
                agent_id, name, role, ideology, communication_style,
                emotion, emotion_state_json, stress, expectation, satisfaction,
                dopamine_level, influence_score, schemas_json,
                schema_flexibility, equilibrium_index, empathy_level,
                last_appraisal_json, memory_size, state_debug_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                float(state.get("influence_score", 0.0)),
                _json(state.get("schemas", {})),
                float(state.get("schema_flexibility", 0.0)),
                float(state.get("equilibrium_index", 0.0)),
                float(state.get("empathy_level", 0.0)),
                _json(state.get("last_appraisal")) if state.get("last_appraisal") is not None else None,
                int(state.get("memory_size", 0)),
                _json(debug_state),
            ),
        )

    for row in snapshot.get("history", []):
        round_index = int(row.get("round_index", 0))
        conn.execute("INSERT INTO round_history (round_index) VALUES (?)", (round_index,))
        results = dict(row.get("results", {}))
        for agent_id_key, result in results.items():
            profile = dict(result.get("profile", {}))
            state_delta = dict(result.get("state_delta", result.get("state", {})))
            decision = dict(result.get("decision", {}))
            behavior = dict(result.get("behavior_output", {}))
            conn.execute(
                """
                INSERT INTO round_results (
                    round_index, agent_id, profile_name, profile_role,
                    profile_ideology, profile_communication_style, state_delta_json,
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
                    _json(state_delta),
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
    *,
    payload: dict[str, Any],
    snapshot: dict[str, Any],
    db_path: str | Path | None = None,
) -> Path:
    target_path = Path(db_path or get_db_path())
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn, _ = create_db(str(target_path))
    try:
        reset_db(conn)
        _execute_schema_scripts(conn)
        insert_input_payload(conn, payload)
        insert_snapshot(conn, snapshot)
        conn.commit()
    finally:
        conn.close()
    return target_path


if __name__ == "__main__":
    conn, _ = create_db()
    conn.close()
    print_db_tables_summary()
