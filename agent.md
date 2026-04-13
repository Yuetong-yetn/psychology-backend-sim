# AGENT.md

本文档描述 Psychology Backend 代码库的当前实现逻辑。

## 项目角色

后端用于模拟 agents 在多轮过程中如何对社交内容作出反应。每个 agent 读取平台内容、评估当前情境、更新内部状态，并发出会影响共享环境的平台动作。

主要交互循环为：

`browse feed -> appraisal -> emotion and schema update -> decision -> platform action -> platform state update`

## 模块职责

- `environment/`
  - 负责仿真生命周期、轮次调度、并发、导出和关闭
- `social_agent/`
  - 负责 agent 档案、状态、appraisal、情绪表示、记忆、schema 更新和动作选择
- `social_platform/`
  - 负责 posts、comments、feed 获取、动作执行和平台追踪
- `services/`
  - 负责 provider 客户端、LLM 路由、本地 fallback 行为和 provider 元数据
- `config/`
  - 负责请求默认值和后端内部参数

## 当前轮次流程

在每一轮中，一个 agent 会执行以下步骤：

1. 读取当前 scenario 和可见 feed
2. 从平台输入构建紧凑的事件表示
3. 运行 appraisal
4. 更新情绪、schemas、stress、equilibrium 和与 memory 关联的状态
5. 构建 beliefs、desires 和 intentions
6. 选择一个动作并提交到平台

`SimulatedAgent.run_round()` 是主要的轮次入口。

## Appraisal 逻辑

Appraisal 是主要的事件解释步骤。它会将当前情境转换为结构化的认知信号，例如：

- relevance
- valence
- goal conduciveness
- controllability
- certainty
- coping potential
- agency-related outputs

当前路由逻辑：

- 后端比例参数决定哪些 agents 使用 LLM appraisal 路径
- 其余 agents 直接使用本地 appraisal 路径
- 被路由到 LLM 的 agents 在外部请求失败时保留本地 fallback 行为

该比例在 `config/backend_settings.py` 中配置：

- `EnvironmentDefaults.appraisal_llm_ratio = 0.1`

这意味着当前实现会将 10% 的 agents 路由到 LLM appraisal 路径。

### Appraisal 运行时元数据

每个 agent 都会在 `state.appraisal_runtime` 中记录 appraisal 执行元数据，包括：

- `mode`
- `provider`
- `model`
- `source`
- `fallback_used`
- `fallback_reason`

因比例配置而直接被路由到本地 appraisal 的 agents 会记录：

- `mode = "fallback"`
- `provider = "local"`
- `fallback_reason = "ratio_routed_to_local"`

## Appraisal Payload

当前的 LLM appraisal payload 是紧凑的，只使用事件判断所需的字段。

它包含：

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

## Latent 逻辑

在当前实现中，latent 编码完全在本地执行。

情绪表示模块使用工程化的本地编码器生成 latent 向量，并记录：

- `mode = "local_only"`
- `provider = "local"`
- `source = "engineered_latent"`
- `fallback_used = false`

每个 agent 快照中都会存储 `latent_runtime` 以供检查。

## Agent 状态约定

`AgentState` 存储仿真、检查和导出所需的字段。

重要的状态组包括：

- `emotion_state`
  - 情绪概率、PAD 值、latent 向量、dominant label
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

在可能的情况下，应从主状态计算派生值，而不是添加镜像字段。

## 平台动作

平台当前支持的动作包括：

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

当动作逻辑变化时，以下层面应保持一致：

- platform execution
- feed visibility
- trace output
- snapshot export

## 环境调度

环境会并发运行 agents，并在调度层协调每轮完成。

当前调度器默认值：

- `llm_semaphore = 64`
- `llm_worker_threads = 64`

环境为 provider 相关工作使用专用线程池，因此 LLM 调用不依赖默认的 event-loop executor。

## Provider 层

Provider 层支持：

- `deepseek`
- `ollama`

当前行为：

- DeepSeek 使用 `requests.Session()`，默认 `max_tokens = 800`
- Ollama 使用 `requests.Session()`，默认 `max_tokens = 800`
- 除非被显式覆盖，DeepSeek 的可用性根据 API key 是否存在推断
- 除非被显式覆盖，Ollama 的可用性根据配置的 endpoint 和 model 推断

当为被路由到 LLM 的路径启用了 fallback 时，provider 失败不会中断整个仿真。

## 前端数据契约

返回的快照按以下规则组织，以供前端消费：

- 仅使用英文标签和状态文本
- 请求默认值由 `config/frontend_settings.py` 驱动
- 面向 agent 的数据只过滤保留 LLM 路径 agents
- 原始返回 JSON 分为：
  - `Posts JSON`
  - `LLM Agents JSON`

因比例配置而被路由到本地 appraisal 的 agents 仍然是 platform 状态和 post 结果的一部分，但它们会被排除在面向 agent 的前端数据之外。

## 调试 API 契约

主要调试路由为：

- `GET /api/debug/options`
- `GET /api/debug/status`
- `POST /api/debug/run-sample`
- `POST /api/debug/run-sample/start`
- `GET /api/debug/run-sample/{job_id}`
- `GET /api/debug/snapshot`

生成的运行时负载包含：

- `mode`
- `llm_provider`
- `enable_fallback`
- `feed_limit`
- `appraisal_llm_ratio`

## 本代码库的开发规则

- 保持导出的快照字段与实际运行时逻辑一致
- 每当认知路由发生变化时，记录 provider 和 fallback 元数据
- 优先使用主状态加派生计算，而不是重复的状态字段
- 保持前端数据假设与快照结构一致
- 当添加新的运行时参数时，要将其贯通到：
  - backend settings
  - payload generation
  - run entrypoints
  - 如果该参数影响解释，则还要接入 snapshot metadata
