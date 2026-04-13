# Psychology Backend

Psychology Backend is a local simulation backend for social discussion dynamics, emotional change, and platform interaction. It accepts a native JSON payload, runs multi-round agent activity on a social platform, and returns structured simulation snapshots for frontend rendering and downstream analysis.

## What The System Does

- Builds a simulation from `scenario`, `agents`, `relationships`, and `seed_posts`
- Runs multi-agent rounds through the environment scheduler
- Lets agents browse feed items, update internal state, and take platform actions
- Exports a full snapshot with platform state, posts, agent state, history, and runtime metadata
- Provides a FastAPI service for running simulations and returning structured frontend data

## Runtime Model

The current runtime uses two different cognition paths:

- `appraisal`
  - Appraisal is the event evaluation step that estimates relevance, valence, controllability, certainty, coping potential, and related decision signals.
  - A backend ratio controls which agents use the external LLM appraisal path.
  - The remaining agents use the local rule-based appraisal path directly.
  - If an LLM appraisal request fails and fallback is enabled, that agent continues with the local appraisal path.

- `latent`
  - Latent encoding is fully local.
  - The system generates the latent emotion representation with the engineered local encoder.
  - `latent_runtime` is recorded as `mode = "local_only"` and `source = "engineered_latent"`.

## Default Runtime Configuration

The sample runtime uses these defaults:

- `num_agents = 20`
- `rounds = 4`
- `seed_posts = 6`
- `seed = 42`
- `feed_limit = 5`
- `mode = "moe"`
- `llm_provider = "ollama"`
- `enable_fallback = true`

Backend scheduling defaults:

- `llm_semaphore = 64`
- `llm_worker_threads = 64`
- `appraisal_llm_ratio = 0.1`

With the current settings, 10% of agents are routed to the LLM appraisal path and the rest are routed to the local appraisal path.

## Providers

The backend supports these external providers:

- `deepseek`
- `ollama`

Provider selection is controlled by runtime input and environment variables. The provider layer records runtime metadata in each agent snapshot, including provider name, model, source, fallback usage, and fallback reason.

Current provider client behavior:

- DeepSeek uses `requests.Session()` and a default `max_tokens = 800`
- Ollama uses `requests.Session()` and a default `max_tokens = 800`
- DeepSeek is treated as enabled when an API key is available unless explicitly disabled
- Ollama is treated as enabled when `base_url` and `model_name` are available unless explicitly disabled

## Input Structure

The generated backend input payload contains:

- `meta`
- `runtime`
- `scenario`
- `agents`
- `relationships`
- `seed_posts`

The generated `runtime` section includes:

- `mode`
- `llm_provider`
- `enable_fallback`
- `feed_limit`
- `appraisal_llm_ratio`

## Snapshot Structure

A simulation snapshot includes:

- scenario information
- platform state and posts
- agent graph and per-agent snapshots
- history across rounds
- runtime metadata for appraisal and latent processing

Important per-agent runtime fields:

- `appraisal_runtime`
- `latent_runtime`
- `last_cognitive_mode`
- `memory`
- `beliefs / desires / intentions`
- `emotion_state`

When an agent is routed to the local appraisal path by ratio, the snapshot records:

- `appraisal_runtime.mode = "fallback"`
- `appraisal_runtime.provider = "local"`
- `appraisal_runtime.fallback_reason = "ratio_routed_to_local"`

## Frontend Return Shape

The simulation result returned to the frontend follows these presentation rules:

- Returned text content is in English
- The returned agent-facing data focuses on agents on the LLM appraisal path
- Agents routed directly to the local appraisal path are not included in the agent-focused frontend view
- Their effects still remain in the returned platform state and post timeline
- Raw returned data is separated into:
  - `Posts JSON`
  - `LLM Agents JSON`

The main debug endpoints are:

- `GET /`
- `GET /docs`
- `GET /api/debug/options`
- `GET /api/debug/status`
- `POST /api/debug/run-sample`
- `POST /api/debug/run-sample/start`
- `GET /api/debug/run-sample/{job_id}`
- `GET /api/debug/snapshot`

## Main Modules

- `environment/`
  - Environment lifecycle, round scheduling, async orchestration, export
- `social_agent/`
  - Agent state, appraisal, emotion update, decision logic, memory, schema dynamics
- `social_platform/`
  - Posts, feed construction, interactions, platform trace
- `services/`
  - Provider clients, appraisal routing, fallback handling
- `config/`
  - Frontend-exposed defaults and backend internal defaults

## Key Files

- `generate_backend_input.py`
  - Builds a native backend input payload for local runs
- `run_backend_input.py`
  - Runs a simulation directly from payload input
- `webapp.py`
  - Exposes the FastAPI service and simulation endpoints
- `config/frontend_settings.py`
  - Defines request defaults, limits, and allowed values
- `config/backend_settings.py`
  - Defines backend generation and scheduler defaults

## Quick Start

```bash
python generate_backend_input.py
python run_backend_input.py -i examples/backend_sample_input.json
uvicorn webapp:app --reload --port 8000
```

Open:

- API docs: `http://localhost:8000/docs`
- Frontend page: `http://localhost:8000/debug/viewer`

## Environment Variables

Common environment variables:

```bash
COGNITIVE_MODE=moe
LLM_PROVIDER_NAME=ollama
LLM_ENABLE_FALLBACK=1
LLM_PROVIDER_USE_CACHE=1
BACKEND_CHECKPOINT_DIR=./checkpoints

DEEPSEEK_API_KEY=xxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_MAX_TOKENS=800

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
OLLAMA_MAX_TOKENS=800
```

## Notes For Integration

- `mode = "moe"` means the runtime may use an external provider for LLM-routed appraisal agents
- `mode = "fallback"` means appraisal stays local for all agents
- `enable_fallback = true` allows LLM-routed appraisal agents to continue with local logic if the provider fails
- `/api/debug/snapshot` returns the latest stored snapshot
- `outputs/` contains exported simulation snapshots

## Architecture Reference

Development-facing conventions and module responsibilities are documented in [agent.md](./agent.md).
