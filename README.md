# Backend

本目录实现社交网络沙盒仿真的后端系统，核心处理链路为：

`Observation -> Appraisal -> CAM -> ECT/DA -> Emotion/Schema -> ToM/BDI -> Decision/Output`

## 架构

后端由三层组成：

- `social_platform`
  负责帖子、回复、点赞、转发、曝光与影响事件。
- `social_agent`
  负责心理状态、Appraisal、CAM 记忆、ECT 满意度、多巴胺代理、ToM/BDI 与行为决策。
- `environment`
  负责场景、平台和多 agent 的多轮仿真调度。

## E-CAM-T 主链

`SimulatedAgent.run_round()` 的执行顺序为：

```text
receive_information
-> update_state
-> decide_action
-> build_behavior_output
-> act
```

`update_state()` 的处理顺序为：

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

## 变量命名

系统采用 `E-CAM-T参数与变量设计.md` 中的核心命名。

输入与中间信号：

- `epsilon`
- `zeta`
- `coping_potential`
- `performance`
- `confirmation`
- `semantic_similarity`
- `empathized_negative_emotion`

持久状态：

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

决策相关：

- `moral_reward`
- `social_influence_reward`
- `explicit_tom_triggered`
- `suggested_action`
- `suggested_actions`
- `behavior_output`

## 规则与机制

### CAM 记忆

`social_agent/cam_memory.py` 提供 `CAMMemoryGraph`，包含：

- 事件节点 `CAMNode`
- 边连接与邻居搜索
- 语义相似度与时间高斯衰减的加权相似度
- `Accommodation`
- `Assimilation`
- bridge node 复制
- cluster 重算
- cluster summary 与 centroid 更新

状态导出包含 `schemata_graph`。

### 共情与利他驱动

系统显式计算：

- `empathized_negative_emotion`
- `dopamine_prediction_error`
- `moral_reward`

处理逻辑为：

- 从可见 `feed` 中提取他人负向情绪强度
- 负向共情压低 `firing_rate`
- `dopamine_prediction_error = firing_rate - performance_prediction`
- 多巴胺下降时提高 `support_others` 与回复倾向

### ECT 满意度链

ECT 更新公式为：

```text
confirmation = performance - expectation
satisfaction = satisfaction + eta * confirmation
expectation = (1 - alpha_E) * expectation + alpha_E * performance
```

当 `satisfaction` 较低且 `epsilon` 较高时，系统会给出 `Behavioral_Shift` 风格的 OASIS 建议动作，例如 `unfollow`、`mute`、`do_nothing`。

### LG-ToM 社交影响奖励

系统通过轻量信念变化近似构造 `social_influence_reward`：

- 用可见帖子内容 `embedding` 近似对方当前外显信念
- 用 `belief_embeddings` 近似发送信息后的条件信念
- 用两者余弦差异构造奖励

该奖励影响 `create_post`、`share_post`、`reply_post` 的分值与解释输出。

## 输入结构

agent 输入由两部分构成：

- `scenario_prompt`
- `feed`

`feed item` 的关键字段包括：

- `content`
- `sentiment`
- `pad`
- `emotion_latent`
- `exposure_score`
- `intensity`
- `author_id`

系统会将这些输入压缩为单轮事件信号，包括：

- `direction`
- `risk`
- `novelty`
- `consistency`
- `observation_text`
- `event_embedding`
- `semantic_similarity`
- `unpredictability`
- `empathized_negative_emotion`

## API 配置

认知相关 API 通过 `services/llm_provider.py` 统一调度，支持两种 provider：

- `ollama`
- `deepseek`

通过环境变量选择：

```bash
LLM_PROVIDER_NAME=ollama
```

或：

```bash
LLM_PROVIDER_NAME=deepseek
```

### Ollama

填写位置：

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`

示例：

```bash
OLLAMA_ENABLED=1
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b-instruct
```

### DeepSeek

填写位置：

- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`

示例：

```bash
DEEPSEEK_ENABLED=1
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_MODEL=deepseek-chat
```

如果未配置外部 API，系统会按 `enable_fallback` 设置回退到本地规则。

## 输出结构

平台执行动作包括：

- `browse_feed`
- `create_post`
- `reply_post`
- `like_post`
- `share_post`
- `apply_influence`
- `do_nothing`

心理解释层输出包括：

- `suggested_action`
- `suggested_actions`
- `behavior_output`

`suggested_actions` 按 OASIS 风格候选动作组织，例如：

- 退缩类：`unfollow` `mute` `do_nothing` `dislike_post`
- 高一致高应对类：`create_post` `create_comment` `repost` `quote_post`
- 高突发观察类：`refresh` `search_posts` `search_user` `trend`

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

## 关键文件

- `social_agent/agent.py`
  E-CAM-T 主链与 agent 决策。
- `social_agent/cam_memory.py`
  CAM 图记忆实现。
- `social_agent/appraisal_moe.py`
  appraisal MoE。
- `social_platform/platform.py`
  平台动作与日志。
- `agent.md`
  agent 层详细说明。

## 运行

最小示例：

```bash
python d:\Design\Psychology\Backend\examples\start.py
```

生成后端原生虚拟输入数据：

```bash
python d:\Design\Psychology\Backend\generate_backend_input.py -o examples/backend_sample_input.json
```

从输入 JSON 直接运行后端：

```bash
python d:\Design\Psychology\Backend\run_backend_input.py -i examples/backend_sample_input.json -o outputs/backend_sample_output.json
```

访问：

- API 文档: `http://localhost:8000/docs`
- 调试页: `http://localhost:8000/debug/viewer`
