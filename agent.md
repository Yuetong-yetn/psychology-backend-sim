# AGENT.md

This document describes the current implementation logic of the Psychology Backend codebase.

## Project Role

The backend simulates how agents react to social content over multiple rounds. Each agent reads platform content, evaluates the current situation, updates internal state, and emits platform actions that affect the shared environment.

The main interaction loop is:

`browse feed -> appraisal -> emotion and schema update -> decision -> platform action -> platform state update`

## Module Responsibilities

- `environment/`
  - Owns simulation lifecycle, round scheduling, concurrency, export, and shutdown
- `social_agent/`
  - Owns agent profile, state, appraisal, emotion representation, memory, schema updates, and action selection
- `social_platform/`
  - Owns posts, comments, feed retrieval, action execution, and platform traces
- `services/`
  - Owns provider clients, LLM routing, local fallback behavior, and provider metadata
- `config/`
  - Owns request defaults and backend internal parameters

## Current Round Flow

For each round, an agent performs these steps:

1. Read the current scenario and visible feed
2. Build a compact event representation from platform inputs
3. Run appraisal
4. Update emotion, schemas, stress, equilibrium, and memory-linked state
5. Build beliefs, desires, and intentions
6. Select an action and submit it to the platform

`SimulatedAgent.run_round()` is the main round entrypoint.

## Appraisal Logic

Appraisal is the primary event interpretation step. It transforms the current situation into structured cognitive signals such as:

- relevance
- valence
- goal conduciveness
- controllability
- certainty
- coping potential
- agency-related outputs

Current routing logic:

- A backend ratio determines which agents use the LLM appraisal path
- The remaining agents use the local appraisal path directly
- LLM-routed agents keep local fallback behavior when external requests fail

The ratio is configured in `config/backend_settings.py`:

- `EnvironmentDefaults.appraisal_llm_ratio = 0.1`

This means the current implementation routes 10% of agents to the LLM appraisal path.

### Appraisal Runtime Metadata

Each agent records appraisal execution metadata in `state.appraisal_runtime`, including:

- `mode`
- `provider`
- `model`
- `source`
- `fallback_used`
- `fallback_reason`

Agents routed directly to local appraisal by ratio record:

- `mode = "fallback"`
- `provider = "local"`
- `fallback_reason = "ratio_routed_to_local"`

## Appraisal Payload

The current LLM appraisal payload is compact and uses only the fields required for event judgment.

It includes:

- `event`
  - `direction`
  - `risk`
  - `novelty`
  - `consistency`
  - `unpredictability`
  - `semantic_similarity`
  - `empathized_negative_emotion`
- `schemas`
  - `support_tendency`
  - `threat_sensitivity`
  - `self_efficacy`
- `emotion_state`
  - `signed_valence`
  - `pad`
  - `intensity`
- `state`
  - `stress`
  - `equilibrium`
- `social_context`
  - `feed_direction`
  - `exposure_pressure`
  - `consensus`
  - `contagion_sentiment`
  - `contagion_arousal`
  - `memory_valence_bias`
- `prior`

## Latent Logic

Latent encoding is fully local in the current implementation.

The emotion representation module generates the latent vector with the engineered local encoder and records:

- `mode = "local_only"`
- `provider = "local"`
- `source = "engineered_latent"`
- `fallback_used = false`

`latent_runtime` is stored in every agent snapshot for inspection.

## Agent State Conventions

`AgentState` stores the fields required for simulation, inspection, and export.

Important state groups include:

- `emotion_state`
  - emotion probabilities, PAD values, latent vector, dominant label
- `stress`
- `equilibrium`
- `schemas`
- `schema_flexibility`
- `memory`
- `last_appraisal`
- `appraisal_history`
- `beliefs`
- `desires`
- `intentions`
- `appraisal_runtime`
- `latent_runtime`

Derived values should be computed from primary state when possible instead of adding mirror fields.

## Platform Actions

The platform currently supports actions such as:

- `create_post`
- `create_comment`
- `repost`
- `quote_post`
- `like_post`
- `follow`
- `search_posts`
- `unfollow`
- `mute`
- `do_nothing`

When action logic changes, the following surfaces should stay aligned:

- platform execution
- feed visibility
- trace output
- snapshot export

## Environment Scheduling

The environment runs agents concurrently and coordinates round completion at the scheduler layer.

Current scheduler defaults:

- `llm_semaphore = 64`
- `llm_worker_threads = 64`

The environment uses a dedicated thread pool for provider-bound work so LLM calls do not depend on the default event-loop executor.

## Provider Layer

The provider layer supports:

- `deepseek`
- `ollama`

Current behavior:

- DeepSeek uses `requests.Session()` and a default `max_tokens = 800`
- Ollama uses `requests.Session()` and a default `max_tokens = 800`
- DeepSeek availability is inferred from API-key presence unless explicitly overridden
- Ollama availability is inferred from configured endpoint and model unless explicitly overridden

Provider failures do not interrupt the whole simulation when fallback is enabled for the routed LLM path.

## Frontend Data Contract

The returned snapshot is structured for frontend consumption with these rules:

- English-only labels and status text
- request defaults driven by `config/frontend_settings.py`
- agent-focused data filtered to LLM-path agents only
- raw returned JSON split into:
  - `Posts JSON`
  - `LLM Agents JSON`

Agents routed to local appraisal by ratio remain part of platform state and post outcomes, but they are excluded from the agent-focused frontend data.

## Debug API Contract

The main debug routes are:

- `GET /api/debug/options`
- `GET /api/debug/status`
- `POST /api/debug/run-sample`
- `POST /api/debug/run-sample/start`
- `GET /api/debug/run-sample/{job_id}`
- `GET /api/debug/snapshot`

The generated runtime payload includes:

- `mode`
- `llm_provider`
- `enable_fallback`
- `feed_limit`
- `appraisal_llm_ratio`

## Development Rules For This Codebase

- Keep exported snapshot fields aligned with actual runtime logic
- Record provider and fallback metadata whenever cognition routing changes
- Prefer primary state plus derived computation over duplicated state fields
- Keep frontend data assumptions aligned with snapshot structure
- When adding new runtime parameters, wire them through:
  - backend settings
  - payload generation
  - run entrypoints
  - snapshot metadata if the parameter affects interpretation
