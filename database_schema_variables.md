# 数据库表字段说明

本文档说明 `psychology_backend_frontend.db` 中各表字段的含义。数据库由 `social_platform/database.py` 根据后端输入负载和仿真快照生成，表结构位于 `social_platform/schema/`。

## 通用约定

- `*_json` 字段为 JSON 字符串，读取后可用 JSON parser 转回对象、数组或字典。
- SQLite 中的布尔值使用 `INTEGER` 表示，`1` 表示 true，`0` 表示 false。
- `round_index` 表示仿真轮次。初始种子帖子通常为 `0`，环境每完成一轮会递增。
- `agent_id` 表示仿真中的 agent 编号。
- `post_id`、`reply_id`、`like_id`、`share_id` 表示平台对象或动作事件编号。

## 输入表

### `input_meta`

保存本次输入负载的顶层元信息。

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | `INTEGER` | 单行表主键，固定为 `1`。 |
| `description` | `TEXT` | 输入负载说明文本。 |
| `num_agents` | `INTEGER` | 本次输入中实际包含的 agent 数量。 |
| `rounds` | `INTEGER` | 本次仿真配置的运行轮数。 |
| `seed_posts` | `INTEGER` | 本次输入中实际包含的初始帖子数量。 |
| `seed` | `INTEGER` | 输入生成使用的随机种子。 |
| `debug_run_config_json` | `TEXT` | 调试运行配置 JSON；没有调试配置时为空。 |

### `input_runtime`

保存本次运行时控制参数。

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | `INTEGER` | 单行表主键，固定为 `1`。 |
| `mode` | `TEXT` | 认知运行模式，例如 `fallback` 或 `moe`。 |
| `llm_provider` | `TEXT` | 外部 LLM provider 名称，例如 `ollama` 或 `deepseek`。 |
| `enable_fallback` | `INTEGER` | provider 不可用时是否启用本地 fallback。 |
| `feed_limit` | `INTEGER` | 每个 agent 每轮最多读取的 feed 条数。 |
| `appraisal_llm_ratio` | `REAL` | 进入 LLM appraisal 路径的 agent 比例。 |

### `input_scenario`

保存输入场景。

| 字段 | 类型 | 含义 |
|---|---|---|
| `scenario_id` | `TEXT` | 场景编号。 |
| `title` | `TEXT` | 场景标题。 |
| `description` | `TEXT` | 场景描述。 |
| `environment_context_json` | `TEXT` | 场景背景说明数组。 |

### `input_agents`

保存输入阶段的 agent 档案和初始状态。

| 字段 | 类型 | 含义 |
|---|---|---|
| `agent_id` | `INTEGER` | agent 编号。 |
| `name` | `TEXT` | agent 展示名称。 |
| `role` | `TEXT` | agent 职业或社会角色标签。 |
| `ideology` | `TEXT` | agent 立场标签。 |
| `communication_style` | `TEXT` | agent 沟通风格标签。 |
| `emotion` | `REAL` | 初始标量情绪值。 |
| `stress` | `REAL` | 初始压力水平。 |
| `expectation` | `REAL` | 初始预期水平。 |
| `satisfaction` | `REAL` | 初始满意度。 |
| `dopamine_level` | `REAL` | 初始多巴胺水平。 |
| `influence_score` | `REAL` | 初始影响力。 |
| `schema_flexibility` | `REAL` | 初始图式可塑性。 |
| `empathy_level` | `REAL` | 初始共情水平。 |
| `schemas_json` | `TEXT` | 初始 schema JSON，通常包含 `support_tendency`、`threat_sensitivity`、`self_efficacy`。 |

### `input_relationships`

保存输入关系图。

| 字段 | 类型 | 含义 |
|---|---|---|
| `row_id` | `INTEGER` | 自增行号。 |
| `source_agent_id` | `INTEGER` | 关注关系的发起 agent。 |
| `target_agent_id` | `INTEGER` | 关注关系的目标 agent。 |
| `type` | `TEXT` | 关系类型，当前为 `follow`。 |

### `input_seed_posts`

保存输入阶段注入平台的初始帖子。

| 字段 | 类型 | 含义 |
|---|---|---|
| `row_id` | `INTEGER` | 自增行号。 |
| `author_id` | `INTEGER` | 初始帖子作者 agent 编号。 |
| `content` | `TEXT` | 初始帖子正文。 |
| `emotion` | `TEXT` | 初始帖子情绪标签。 |
| `intensity` | `REAL` | 初始帖子情绪强度。 |
| `sentiment` | `REAL` | 初始帖子情感极性。 |
| `round_index` | `INTEGER` | 初始帖子所属轮次。 |

## 快照表

### `snapshot_info`

保存最终快照的顶层信息。

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | `INTEGER` | 单行表主键，固定为 `1`。 |
| `round_index` | `INTEGER` | 快照对应的最终轮次。 |
| `scenario_prompt` | `TEXT` | 仿真使用的完整场景 prompt。 |
| `export_path` | `TEXT` | JSON 快照导出路径。 |
| `raw_json` | `TEXT` | 完整仿真快照 JSON。 |

### `snapshot_debug`

保存快照级调试信息。

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | `INTEGER` | 单行表主键，固定为 `1`。 |
| `exposed_frontend_params_json` | `TEXT` | 前端或调试界面可展示的运行参数名数组。 |
| `provider_behavior_json` | `TEXT` | provider 行为摘要，包含运行模式、provider 和 fallback 开关。 |
| `simulation_config_json` | `TEXT` | 本次仿真的全局配置摘要。 |
| `agent_runtime_summary_json` | `TEXT` | 每个 agent 的 appraisal、latent、action timing 和 fallback 摘要。 |
| `why_results_appear_without_api_key` | `TEXT` | 无外部 API key 时仍能生成结果的说明。 |
| `auto_run_on_snapshot` | `INTEGER` | 快照读取端是否应自动运行的标记。 |
| `history_rounds` | `INTEGER` | 快照历史中包含的轮次数。 |
| `raw_json` | `TEXT` | 完整 `_debug` 对象 JSON。 |

## 平台表

### `platform_snapshot`

保存平台最终状态摘要。

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | `INTEGER` | 单行表主键，固定为 `1`。 |
| `current_round` | `INTEGER` | 平台当前轮次。 |
| `scenario_prompt` | `TEXT` | 平台持有的场景 prompt。 |
| `agent_count` | `INTEGER` | 平台注册 agent 数量。 |
| `agents_json` | `TEXT` | 平台注册 agent 信息 JSON。 |
| `trace_size` | `INTEGER` | 平台 trace 事件数量。 |
| `runtime_profile_json` | `TEXT` | 平台运行时配置摘要 JSON。 |

### `platform_posts`

保存平台中的帖子，包括初始帖子、agent 创建的帖子和分享生成的帖子。

| 字段 | 类型 | 含义 |
|---|---|---|
| `post_id` | `INTEGER` | 帖子编号。 |
| `author_id` | `INTEGER` | 作者 agent 编号。 |
| `content` | `TEXT` | 帖子正文。 |
| `emotion` | `TEXT` | 帖子情绪标签。 |
| `dominant_emotion` | `TEXT` | 帖子的主导情绪标签。 |
| `intensity` | `REAL` | 情绪强度。 |
| `sentiment` | `REAL` | 情感极性。 |
| `emotion_probs_json` | `TEXT` | 多情绪概率分布 JSON。 |
| `pad_json` | `TEXT` | PAD 情绪向量 JSON，通常表示 pleasure、arousal、dominance。 |
| `emotion_latent_json` | `TEXT` | 情绪 latent 向量 JSON。 |
| `like_count` | `INTEGER` | 当前帖子累计点赞数。 |
| `share_count` | `INTEGER` | 当前帖子累计分享数。 |
| `shared_post_id` | `INTEGER` | 分享生成的帖子指向原帖编号；普通帖子为空。 |
| `round_index` | `INTEGER` | 帖子创建轮次。 |

### `platform_replies`

保存平台中的回复动作结果。

| 字段 | 类型 | 含义 |
|---|---|---|
| `reply_id` | `INTEGER` | 回复编号。 |
| `post_id` | `INTEGER` | 被回复的帖子编号。 |
| `author_id` | `INTEGER` | 回复作者 agent 编号。 |
| `content` | `TEXT` | 回复正文。 |
| `emotion` | `TEXT` | 回复情绪标签。 |
| `dominant_emotion` | `TEXT` | 回复主导情绪标签。 |
| `intensity` | `REAL` | 回复情绪强度。 |
| `sentiment` | `REAL` | 回复情感极性。 |
| `emotion_probs_json` | `TEXT` | 回复多情绪概率分布 JSON。 |
| `pad_json` | `TEXT` | 回复 PAD 情绪向量 JSON。 |
| `emotion_latent_json` | `TEXT` | 回复情绪 latent 向量 JSON。 |
| `round_index` | `INTEGER` | 回复创建轮次。 |

### `platform_likes`

保存点赞事件。

| 字段 | 类型 | 含义 |
|---|---|---|
| `like_id` | `INTEGER` | 点赞事件编号。 |
| `post_id` | `INTEGER` | 被点赞的帖子编号。 |
| `agent_id` | `INTEGER` | 执行点赞的 agent 编号。 |
| `round_index` | `INTEGER` | 点赞发生轮次。 |

### `platform_shares`

保存分享事件。

| 字段 | 类型 | 含义 |
|---|---|---|
| `share_id` | `INTEGER` | 分享事件编号。 |
| `post_id` | `INTEGER` | 被分享的原帖编号。 |
| `agent_id` | `INTEGER` | 执行分享的 agent 编号。 |
| `round_index` | `INTEGER` | 分享发生轮次。 |

### `platform_influence_events`

保存平台动作造成的 agent 间影响事件。

| 字段 | 类型 | 含义 |
|---|---|---|
| `row_id` | `INTEGER` | 自增行号。 |
| `round_index` | `INTEGER` | 影响发生轮次。 |
| `source_agent_id` | `INTEGER` | 影响来源 agent。 |
| `target_agent_id` | `INTEGER` | 被影响 agent。 |
| `delta` | `REAL` | 影响量，正负号表示影响方向。 |
| `reason` | `TEXT` | 影响原因说明。 |

### `platform_traces`

保存平台事件追踪日志。

| 字段 | 类型 | 含义 |
|---|---|---|
| `trace_index` | `INTEGER` | trace 序号。 |
| `type` | `TEXT` | trace 事件类型，例如 `create_post`、`like_post`、`reply_post`、`share_post`、`apply_influence`、`commit_round`。 |
| `round_index` | `INTEGER` | trace 所属轮次；部分注册类事件可为空。 |
| `raw_json` | `TEXT` | 完整 trace 事件 JSON。 |

## Agent 图表

### `agent_graph_info`

保存最终 agent 关系图摘要。

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | `INTEGER` | 单行表主键，固定为 `1`。 |
| `num_nodes` | `INTEGER` | 关系图中的 agent 节点数量。 |
| `num_edges` | `INTEGER` | 关系图中的边数量。 |

### `agent_graph_edges`

保存最终 agent 关系图中的边。

| 字段 | 类型 | 含义 |
|---|---|---|
| `row_id` | `INTEGER` | 自增行号。 |
| `source_agent_id` | `INTEGER` | 边的起点 agent。 |
| `target_agent_id` | `INTEGER` | 边的终点 agent。 |

## Agent 快照表

### `agent_snapshots`

保存仿真结束时每个 agent 的最终快照。

| 字段 | 类型 | 含义 |
|---|---|---|
| `agent_id` | `INTEGER` | agent 编号。 |
| `name` | `TEXT` | agent 展示名称。 |
| `role` | `TEXT` | agent 职业或社会角色标签。 |
| `ideology` | `TEXT` | agent 立场标签。 |
| `communication_style` | `TEXT` | agent 沟通风格标签。 |
| `emotion` | `REAL` | 最终标量情绪值。 |
| `emotion_state_json` | `TEXT` | 最终多维情绪状态 JSON，包含情绪概率、PAD、latent、主导情绪和强度等。 |
| `stress` | `REAL` | 最终压力水平。 |
| `expectation` | `REAL` | 最终预期水平。 |
| `satisfaction` | `REAL` | 最终满意度。 |
| `dopamine_level` | `REAL` | 最终多巴胺水平。 |
| `influence_score` | `REAL` | 最终影响力。 |
| `schemas_json` | `TEXT` | 最终 schema JSON。 |
| `schema_flexibility` | `REAL` | 最终图式可塑性。 |
| `equilibrium_index` | `REAL` | 最终心理稳态指数。 |
| `empathy_level` | `REAL` | 最终共情水平。 |
| `last_appraisal_json` | `TEXT` | 最近一次 appraisal 摘要 JSON。 |
| `memory_size` | `INTEGER` | agent 记忆条目数量。 |
| `state_debug_json` | `TEXT` | agent 调试状态 JSON，包含 appraisal runtime、latent runtime、action timing、beliefs、desires、intentions 和内部计算量。 |

## 轮次历史表

### `round_history`

保存仿真历史中存在的轮次。

| 字段 | 类型 | 含义 |
|---|---|---|
| `round_index` | `INTEGER` | 轮次编号。 |

### `round_results`

保存每轮每个 agent 的决策和轻量状态变化。

| 字段 | 类型 | 含义 |
|---|---|---|
| `row_id` | `INTEGER` | 自增行号。 |
| `round_index` | `INTEGER` | 轮次编号。 |
| `agent_id` | `INTEGER` | agent 编号。 |
| `profile_name` | `TEXT` | 本轮结果中的 agent 名称。 |
| `profile_role` | `TEXT` | 本轮结果中的 agent 角色标签。 |
| `profile_ideology` | `TEXT` | 本轮结果中的 agent 立场标签。 |
| `profile_communication_style` | `TEXT` | 本轮结果中的 agent 沟通风格。 |
| `state_delta_json` | `TEXT` | 本轮轻量状态 JSON，包含回放需要的心理状态字段。 |
| `decision_action` | `TEXT` | agent 本轮选择的动作，例如 `create_post`、`like_post`、`reply_post`、`share_post`、`browse_feed`。 |
| `decision_content` | `TEXT` | 决策生成的文本内容或动作说明。 |
| `decision_target_post_id` | `INTEGER` | 决策目标帖子编号；无目标帖子时为空。 |
| `decision_target_agent_id` | `INTEGER` | 决策目标 agent 编号；无目标 agent 时为空。 |
| `decision_metadata_json` | `TEXT` | 决策附加元数据 JSON。 |
| `decision_influence_delta` | `REAL` | 决策预期造成的影响量。 |
| `decision_reason` | `TEXT` | 决策原因说明。 |
| `decision_suggested_action` | `TEXT` | appraisal 或策略层给出的首选动作建议。 |
| `decision_suggested_actions_json` | `TEXT` | 动作建议列表 JSON。 |
| `behavior_primary_action` | `TEXT` | 行为输出中的主动作类别。 |
| `behavior_stimulus_excerpt` | `TEXT` | 触发本轮行为的 feed 或场景摘要。 |
| `behavior_public_behavior_summary` | `TEXT` | 面向外部展示的行为摘要。 |
| `behavior_simulated_public_content` | `TEXT` | 本轮模拟生成的公开内容；没有公开文本时为空。 |
| `behavior_state_hint_json` | `TEXT` | 行为相关状态提示 JSON。 |
| `behavior_cam_summary_json` | `TEXT` | CAM 或记忆摘要 JSON。 |
| `behavior_explicit_tom_triggered` | `INTEGER` | 本轮是否触发显式 Theory of Mind 相关逻辑。 |
| `behavior_backend_action` | `TEXT` | 后端实际派发的平台动作名称。 |
| `behavior_round_index` | `INTEGER` | 行为输出记录的轮次编号。 |

