# Agent

`social_agent/agent.py` 是后端中承载 `E-CAM-T` 的核心模块，负责从观察输入到行为输出的完整心理处理链。

## 主链

`SimulatedAgent.run_round()`：

```text
receive_information
-> update_state
-> decide_action
-> build_behavior_output
-> act
```

`update_state()`：

```text
extract_environment_signal
-> build_appraisal
-> update_cam_memory
-> update_ecam_t_state
-> update_emotion
-> update_schema
-> rebalance
-> update_beliefs_and_intentions
```

这条链路对应五层结构：

1. 感知输入层
2. 认知评价层
3. 预测与确认层
4. 心理状态持久层
5. 决策执行层

## AgentState

`AgentState` 中与 E-CAM-T 对齐的核心成员包括：

### 输入与中间信号

- `epsilon`
- `zeta`
- `coping_potential`
- `performance`
- `confirmation`
- `semantic_similarity`
- `empathized_negative_emotion`

### 持久心理状态

- `expectation`
- `satisfaction`
- `dopamine_level`
- `dopamine_prediction_error`
- `performance_prediction`
- `belief_embeddings`
- `equilibrium_index`
- `schemata_graph`
- `beliefs`
- `desires`
- `intentions`
- `knowledge`

### 决策与奖励

- `moral_reward`
- `social_influence_reward`
- `explicit_tom_triggered`

## CAM

CAM 通过 `social_agent/cam_memory.py` 提供图结构：

- `CAMNode`
  记录事件内容、embedding、时间步、情感效价与 cluster 归属。
- `CAMMemoryGraph`
  记录节点、边与 cluster。
- `CAMCluster`
  保存 cluster summary 与 centroid。

CAM 更新过程包括：

1. 使用 `semantic_weight * cos_sim + (1 - semantic_weight) * gaussian_time_decay` 计算事件相似度。
2. 若不存在高于阈值的邻居，则创建新节点并执行 `Accommodation`。
3. 若存在匹配邻居，则新节点与匹配节点连边并执行 `Assimilation`。
4. 若单个节点连接多个原本不连通的语义簇，则复制该节点，实现“一事多议”。
5. 按连通分量更新 cluster。
6. 根据 cluster 内的近期事件生成层级摘要。

`schemata_graph` 会直接进入导出快照。

## Appraisal

Appraisal 由 `AppraisalRouter` 与 `MoE experts` 驱动，输出字段包括：

- `relevance`
- `valence`
- `goal_conduciveness`
- `controllability`
- `certainty`
- `coping_potential`
- `unpredictability`
- `goal_relevance_signal`
- `performance`
- `confirmation`

这些字段作为中间信号流入 ECT、CAM 与 ToM/BDI。

## ECT 与多巴胺链

`_update_ecam_t_state()` 负责将 appraisal 与事件信号转换为长期状态。

### ECT

更新公式为：

```text
confirmation = performance - expectation
satisfaction = satisfaction + eta * confirmation
expectation = (1 - alpha_E) * expectation + alpha_E * performance
```

### 共情利他与多巴胺

更新公式为：

```text
firing_rate = performance - empathized_negative_emotion * empathy_level * k + positive_goal_bonus
dopamine_prediction_error = firing_rate - performance_prediction
performance_prediction = performance_prediction + lambda * dopamine_prediction_error
dopamine_level = dopamine_level + gamma * dopamine_prediction_error + goal_gain * zeta
moral_reward = performance + empathy_level * altruistic_drive
```

其中：

- `empathized_negative_emotion` 来自可见 `feed` 中他人负向情绪的加权估计
- 他人负向情绪增强时，`dopamine_prediction_error` 会下降
- 该信号会提高 `support_others` 意图与回复倾向

## LG-ToM 与显式 ToM

`_update_beliefs_and_intentions()` 构造轻量 ToM/BDI：

- `beliefs`
  环境效价、社会压力、目标一致、他人是否需要支持、社会影响奖励等。
- `desires`
  从 persona 初始化的稳定偏好。
- `intentions`
  `observe / participate / amplify / withdraw / support_others`

### 显式 ToM 触发

满足以下任一条件时，`explicit_tom_triggered = true`：

- `epsilon > tau_unpredictability`
- 观察到的 `feed` 分歧度较高

触发后，agent 会优先提高观察和澄清倾向。

### Social Influence Reward

`social_influence_reward` 的近似实现为：

1. 用帖子文本 `embedding` 近似对方当前外显信念。
2. 用 `belief_embeddings` 构造发送信息后的条件信念。
3. 用两者余弦差异作为影响奖励。

该奖励提升 `create_post`、`share_post`、`reply_post` 的分值。

## 决策层

`decide_action()` 由三类信号共同约束：

- appraisal / emotion / schema 分数
- `moral_reward`
- `social_influence_reward`

决策同时考虑：

- 是否需要先观察
- 是否需要支持其他 agent
- 当前表达是否值得为了改变他人信念而发生

## 输出

agent 产生两层输出。

### 平台执行动作

- `browse_feed`
- `create_post`
- `reply_post`
- `like_post`
- `share_post`

### 心理解释层输出

- `suggested_action`
- `suggested_actions`
- `behavior_output`

`suggested_actions` 按 OASIS 风格规则组织。

`behavior_output` 包括：

- `primary_action`
- `stimulus_excerpt`
- `public_behavior_summary`
- `simulated_public_content`
- `state_hint`
- `cam_summary`
- `explicit_tom_triggered`
- `backend_action`
- `round_index`

访问：

- API 文档: `http://localhost:8000/docs`
- 调试页: `http://localhost:8000/debug/viewer`

## API Provider

agent 的认知生成与情绪 latent 生成通过 `CognitiveMoEProvider` 调用外部 provider，支持：

- `ollama`
- `deepseek`

provider 选择入口：

```bash
LLM_PROVIDER_NAME=ollama
```

或：

```bash
LLM_PROVIDER_NAME=deepseek
```

URL 填写位置：

- Ollama: `OLLAMA_BASE_URL`
- DeepSeek: `DEEPSEEK_BASE_URL`

常用相关环境变量：

```bash
OLLAMA_ENABLED=1
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b-instruct

DEEPSEEK_ENABLED=1
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_MODEL=deepseek-chat
```
