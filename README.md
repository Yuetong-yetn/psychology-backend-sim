`Backend` 是项目中的后端仿真层，负责组织环境、平台、agent 认知过程、行为执行与结果导出。

## 1. 目录结构

`Backend` 主要分成三层：

1. `social_platform`
   负责平台状态、帖子、回复、点赞、转发、曝光分发、影响事件与 trace。
2. `social_agent`
   负责 agent 的画像、内部状态、记忆、appraisal、emotion、schema 更新与行为决策。
3. `environment`
   负责把 scenario、platform 与多个 agent 串起来运行多轮仿真。

补充模块：

- `social_platform/storage.py`
  导出仿真结果为 JSON。
- `social_platform/emotion_detector.py`
  本地文本情绪分析器，作为 fallback 使用。
- `social_agent/appraisal_moe.py`
  appraisal 的 MoE 引擎。
- `social_agent/emotion_representation.py`
  情绪高维表示模块。
- `services/volcengine_client.py`
  火山引擎 API client。
- `services/llm_provider.py`
  统一认知 provider，负责调度 experts、调用火山引擎并在失败时自动 fallback。
- `environment/scenario.py`
  场景与环境上下文定义。
- `examples/start.py`
  最小可运行示例。

## 2. 主执行链路

环境调度由 `environment/env.py` 负责，主顺序是：

1. `platform.get_feed_for_agent(agent.agent_id)`
2. `agent.run_round(round_index, scenario_prompt, feed, platform)`
3. `platform.commit_round(round_index, round_results)`
4. `history.append({"round_index": ..., "results": result.to_dict()})`

`SimulatedAgent.run_round()` 的内部顺序是：

1. `receive_information()`
2. `update_state()`
3. `decide_action()`
4. `act()`

`update_state()` 的内部顺序是：

1. `_extract_environment_signal()`
2. `_build_appraisal()`
3. `_update_emotion()`
4. `_update_schema()`
5. `_rebalance()`

## 3. 运行模式

对外只保留两种模式：

- `moe`
  系统默认主路径。认知处理以“专家分解 + 聚合”为核心设计。
- `fallback`
  当外部 provider 不可用、专家输出不可解析、聚合失败或模式被显式关闭时，系统切到本地逻辑继续运行。

## 4. 认知闭环

当前系统的核心闭环是：

```text
emotion_state / emotion
        ↓
moe appraisal
        ↓
emotion update
        ↓
schema update
        ↓
equilibrium
        ↓
behavior
        ↓
platform
        ↓
emotion contagion
        ↓
next-round appraisal
```

平台同时提供情绪信号和曝光信号，因此传播和认知都建立在“可见内容”之上，而不是原始文本的简单平均。

## 5. Emotion 表示

### 5.1 `EmotionState`

`social_agent/agent.py` 中的 `EmotionState` 表示 agent 的多维情绪状态，字段包括：

- `emotion_probs: Dict[str, float]`
  离散情绪分布，各类情绪占比。
- `pad: List[float]`
  三维情绪坐标，顺序是 `[pleasure, arousal, dominance]`。
- `latent: List[float]`
  高维情绪表示，供传播、schema 更新和行为决策读取。
- `dominant_label: str`
  主导离散情绪标签。
- `intensity: float`
  情绪强度。
- `signed_valence: float`
  带符号情绪值，总体情绪偏向正面还是负面。

### 5.2 模式

情绪与 latent 的生成只有两种状态：

- `moe`
  由情绪相关 experts 共同给出结构化语义特征，再映射为固定维度 latent。
- `fallback`
  使用本地 detector 和本地 latent 构造逻辑。

## 6. Appraisal

### 6.1 输入

环境输入会先压缩为一个 `event`，包括：

- `direction`
  当前可见内容整体偏正向还是偏负向。
- `risk`
  当前输入带来的风险或压力水平。
- `novelty`
  当前输入与既有认知结构的偏离程度。
- `consistency`
  当前输入内部是否一致、是否相互冲突。

agent 的当前 schema 包括三个维度：

- `support_tendency`
  agent 默认更支持还是更反对当前议题。
- `threat_sensitivity`
  agent 把外部输入理解为威胁的倾向。
- `self_efficacy`
  agent 认为自己是否有能力应对局面。

此外，appraisal 还会读取：

- `emotion_state`
  当前多维情绪状态。
- `stress`
  当前压力水平。
- `equilibrium`
  当前认知稳定程度。
- `feed_features`
  当前 feed 摘要出的社会传播特征。
- `contagion_features`
  最近传播结果的摘要特征。
- `memory_summary`
  从最近记忆中提取的压缩摘要。

### 6.2 输出

`_build_appraisal()` 返回 `AppraisalRecord`，字段包括：

- `relevance`
  当前事件与 agent 目标的相关程度。
- `valence`
  当前事件整体偏正向还是偏负向。
- `goal_congruence`
  当前事件是否符合 agent 的目标或图式。
- `controllability`
  agent 感到当前情境是否可控。
- `agency`
  agent 对责任归属的判断。
- `certainty`
  agent 对当前判断的确定程度。
- `novelty`
  当前输入的新异程度。
- `coping_potential`
  agent 认为自己能否应对当前情况。
- `dominant_emotion`
  appraisal 对应的主导情绪。
- `emotion_intensity`
  appraisal 对应的情绪强度。
- `cognitive_mode`
  当前认知更新的模式标签。

### 6.3 MoE 结构

appraisal 的主设计是 MoE。当前引擎至少包括：

- `Router / Aggregator`
  负责组合 expert 输出。
- `ThreatExpert`
  处理风险、威胁与负向线索。
- `SupportExpert`
  处理支持、一致性与正向线索。
- `CopingExpert`
  处理控制感和应对能力线索。
- `SocialAmplificationExpert`
  处理曝光压力和群体传播线索。

某些 experts 可以由火山引擎 LLM 提供结构化结果，但系统最终仍由本地聚合层完成统一输出。

## 7. 平台与文本情绪识别

平台层由 `social_platform/platform.py` 管理。

平台中的帖子和回复会写入：

- `emotion`
  直观的情绪标签。
- `dominant_emotion`
  当前帖子或回复的主导情绪。
- `intensity`
  当前文本或状态表达出的情绪强度。
- `sentiment`
  带符号情绪值，用于聚合与传播。
- `emotion_probs`
  各类离散情绪的分布情况。
- `pad`
  当前情绪在 pleasure / arousal / dominance 三维上的坐标。
- `emotion_latent`
  供内部计算使用的高维情绪表示。
- `like_count`
  当前帖子收到的点赞数量。
- `share_count`
  当前帖子被转发的次数。
- `shared_post_id`
  若当前帖子由转发生成，则指向原始帖子 id。

平台写入情绪字段时遵循两层策略：

- 优先使用 `moe` provider 做情绪语义分析
- 若失败，则调用本地 detector 作为 `fallback`

## 8. Exposure Scoring

`Platform.get_feed_for_agent()` 会为每条 feed item 计算：

- `exposure_score`
  内容在当前 feed 中的曝光强度。
- `exposure_features`
  组成曝光分数的各项特征。

当前 `exposure_features` 包括：

- `recency`
  内容距离当前轮次有多近。
- `emotion_salience`
  内容情绪有多显著。
- `engagement`
  内容当前获得的互动强度。
- `share_boost`
  转发内容获得的额外放大权重。
- `novelty_hint`
  内容值得继续分发的新颖性提示。
- `self_author_penalty`
  对 agent 自己发的内容做的降权项。

这些字段直接影响情绪传播和后续认知加工。

## 9. 情绪传播与 Schema 更新

### 9.1 情绪传播

`_apply_emotion_contagion()` 会按 `exposure_score` 加权聚合可见内容的：

- `sentiment`
  带符号情绪值。
- `pad`
  低维情绪坐标。
- `latent`
  高维情绪表示。

传播结果保存在：

- `last_contagion_pad`
  最近一轮群体情绪传播后的 PAD 聚合结果。
- `last_contagion_vector`
  最近一轮群体情绪传播后的高维聚合向量。

### 9.2 Schema 更新

schema 维度包括：

- `support_tendency`
  对当前议题偏支持还是偏反对。
- `threat_sensitivity`
  把外界理解为威胁的倾向。
- `self_efficacy`
  认为自己有能力应对情境的程度。

`_update_schema()` 会综合读取：

- appraisal vector
- `emotion_state.pad`
- `emotion_state.latent`
- `last_contagion_pad`
- `last_contagion_vector`

## 10. 行为决策

系统输出五类动作：

- `browse_feed`
  继续浏览内容，不立即执行更强动作。
- `reply_post`
  对某条帖子直接回复。
- `create_post`
  主动发布新帖子。
- `like_post`
  对目标帖子点赞。
- `share_post`
  转发或放大某条帖子。

决策会综合读取：

- appraisal
- `emotion_state.pad`
- `emotion_state.intensity`
- `emotion_state.latent`
- stress
- equilibrium
- schemas

## 11. Provider 层

`services/llm_provider.py` 对上层暴露统一接口：

- `generate_appraisal(...)`
  生成结构化 appraisal 结果。
- `analyze_emotion(...)`
  分析文本或内部状态对应的情绪语义。
- `build_latent(...)`
  生成供内部使用的高维情绪表示。

当前统一调度层是：

- `CognitiveMoEProvider`
  负责调度 experts、必要时调用火山引擎、聚合结果并处理 fallback。

provider 统一导出以下元信息：

- `mode`
  当前实际运行的模式，`moe` 或 `fallback`。
- `provider`
  当前使用的 provider 名称。
- `model`
  当前使用的模型名称。
- `source`
  当前结果来自哪类 expert / 本地路径。
- `fallback_used`
  是否发生了回退。
- `fallback_reason`
  本次回退的原因。

## 12. 运行元信息与导出

`AgentState` 中包含：

- `appraisal_runtime`
  记录本轮 appraisal 实际使用了哪种运行路径。
- `latent_runtime`
  记录本轮 latent 实际使用了哪种运行路径。

导出链路包括：

- `AgentRoundResult.to_dict()`
- `SimulatedAgent.snapshot()`
- `SimulationEnv.snapshot()`
- `SimulationStorage.save_json()`

所有新增字段都保持为 JSON 可序列化类型。

## 13. 配置

当前对外只保留三类核心配置：

- `mode: "moe" | "fallback"`
  指定系统主路径。
- `llm_provider: str`
  当前选择的 provider 名称，默认 `volcengine`。
- `enable_fallback: bool`
  当外部 provider 不可用时是否自动使用本地逻辑。

火山引擎相关环境变量包括：

- `VOLCENGINE_ENABLED`
  是否启用火山引擎 provider。
- `VOLCENGINE_API_KEY`
  火山引擎 API 密钥。
- `VOLCENGINE_BASE_URL`
  火山引擎请求地址。
- `VOLCENGINE_MODEL`
  调用的火山引擎模型名称。
- `VOLCENGINE_TIMEOUT`
  单次请求的超时时间。
- `VOLCENGINE_RETRY`
  请求失败后的重试次数。

## 14. 常用命令

最小示例：

```bash
python d:\Design\Psychology\Backend\examples\start.py
```
