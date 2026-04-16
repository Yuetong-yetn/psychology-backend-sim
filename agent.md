# Agent 运行说明

本文档描述 Psychology Backend 的当前运行逻辑和模块职责。

## 项目角色

后端用于模拟 agents 在多轮社交平台环境中如何读取内容、评估情境、更新心理状态并采取平台动作。

主循环为：

```text
browse feed -> appraisal -> emotion/schema update -> decision -> platform action -> platform state update
```

## 模块职责

- `environment/`：仿真生命周期、轮次调度、并发执行、快照导出和关闭流程。
- `social_agent/`：agent 档案、状态、appraisal、情绪表示、记忆、schema 更新和动作选择。
- `social_platform/`：posts、comments、feed、平台动作执行、trace 和 SQLite 持久化。
- `services/`：LLM provider 客户端、provider 路由、fallback 行为和快照元数据。
- `config/`：输入生成默认值、运行默认值、IO 路径和调度参数。
- `examples/`：命令行运行入口和样例输入。

## 轮次流程

每一轮中，agent 执行以下步骤：

1. 读取当前 scenario 和个性化 feed。
2. 将平台输入整理成紧凑事件表示。
3. 执行 appraisal。
4. 更新情绪、schemas、stress、equilibrium 和 memory 相关状态。
5. 构建 beliefs、desires 和 intentions。
6. 选择动作并提交到平台。

`SimulatedAgent.run_round()` 是单个 agent 的轮次入口。`SimulationEnv.astep()` 负责一轮环境调度，`SimulationEnv.arun()` 负责多轮运行。

## Appraisal

Appraisal 将当前情境转换为结构化认知信号。核心字段包括：

- `relevance`
- `valence`
- `goal_conduciveness`
- `controllability`
- `certainty`
- `novelty`
- `coping_potential`
- `agency`
- `dominant_emotion`
- `emotion_intensity`
- `cognitive_mode`

运行时使用 `runtime.appraisal_llm_ratio` 控制进入 LLM appraisal 路径的 agent 比例。未进入 LLM 路径的 agent 使用本地 appraisal。进入 LLM 路径的 agent 在 provider 不可用且启用 fallback 时使用本地 appraisal。

默认配置位于 `config/backend_settings.py`：

- `EnvironmentDefaults.appraisal_llm_ratio = 0.1`

## Appraisal 运行元数据

每个 agent 在 `state.appraisal_runtime` 中记录 appraisal 执行元数据：

- `mode`
- `provider`
- `model`
- `source`
- `fallback_used`
- `fallback_reason`

比例路由到本地 appraisal 的 agent 会记录：

- `mode = "fallback"`
- `provider = "local"`
- `fallback_reason = "ratio_routed_to_local"`

## LLM Appraisal Payload

LLM appraisal payload 使用紧凑字段：

- `event.direction`
- `event.risk`
- `event.novelty`
- `event.consistency`
- `event.unpredictability`
- `event.semantic_similarity`
- `event.empathized_negative_emotion`
- `schemas.support_tendency`
- `schemas.threat_sensitivity`
- `schemas.self_efficacy`
- `emotion_state.signed_valence`
- `emotion_state.pad`
- `emotion_state.intensity`
- `state.stress`
- `state.equilibrium`
- `social_context.feed_direction`
- `social_context.exposure_pressure`
- `social_context.consensus`
- `social_context.contagion_sentiment`
- `social_context.contagion_arousal`
- `social_context.memory_valence_bias`
- `prior`

## Latent

Latent 编码在本地执行。情绪表示模块使用工程化编码器生成 latent 向量，并在 `state.latent_runtime` 中记录：

- `mode = "local_only"`
- `provider = "local"`
- `source = "engineered_latent"`
- `fallback_used = false`

## Agent 状态

`AgentState` 存储仿真、检查和导出所需字段。主要状态组包括：

- `emotion_state`
- `stress`
- `expectation`
- `satisfaction`
- `dopamine_level`
- `influence_score`
- `schemas`
- `schema_flexibility`
- `equilibrium_index`
- `empathy_level`
- `memory`
- `last_appraisal`
- `appraisal_history`
- `beliefs`
- `desires`
- `intentions`
- `appraisal_runtime`
- `latent_runtime`

导出快照中的 `agents[].state.last_appraisal` 使用轻量 `AppraisalSummary`。完整 `AppraisalRecord` 用于运行时计算和历史维护。

## 平台动作

平台支持的动作包括：

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

动作执行涉及四个层面：

- platform execution
- feed visibility
- trace output
- snapshot export

## 环境调度

环境并发运行 agents，并在调度层协调每轮完成。默认调度参数：

- `llm_semaphore = 64`
- `llm_worker_threads = 64`

Provider 相关工作使用专用线程池执行。

## Provider

Provider 层支持：

- `deepseek`
- `ollama`

DeepSeek 和 Ollama 客户端使用 `requests.Session()`，默认 `max_tokens = 800`。Provider 可用性由环境变量、endpoint、model 和运行配置共同决定。

## 快照和入口

常用运行命令：

```bash
python examples/generate_backend_input.py
python examples/start.py -i examples/backend_sample_input.json
```

生成和运行使用以下运行时参数：

- `mode`
- `llm_provider`
- `enable_fallback`
- `feed_limit`
- `appraisal_llm_ratio`

## 开发约定

- 快照字段与实际运行时状态保持一致。
- 认知路由信息写入 provider 和 fallback 元数据。
- 默认展示读取 `agents[].state` 主字段。
- 调试和研究读取 `agents[].state._debug` 与 `snapshot._debug.agent_runtime_summary`。
- 新增运行时参数时，同步更新 backend settings、payload generation、run entrypoint 和 snapshot metadata。
