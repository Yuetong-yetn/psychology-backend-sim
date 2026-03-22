# Agent 层说明

`Backend/social_agent/agent.py` 是 agent 认知过程的核心实现文件。它负责接收环境输入、构建 appraisal、更新 emotion 与 schema、计算 equilibrium，并输出平台行为。

## 1. 角色

`SimulatedAgent` 的职责包括：

1. 接收环境输入与 feed
2. 更新内部状态
3. 进行行为决策
4. 在平台上执行动作

主流程是：

```text
receive_information()
-> update_state()
-> decide_action()
-> act()
```

`update_state()` 的内部顺序是：

```text
_extract_environment_signal()
-> _build_appraisal()
-> _update_emotion()
-> _update_schema()
-> _rebalance()
```

## 2. 核心数据结构

### 2.1 `EmotionState`

`EmotionState` 描述 agent 的多维情绪状态，字段包括：

- `emotion_probs`
  离散情绪分布。
- `pad`
  情绪在 `[pleasure, arousal, dominance]` 三维上的坐标。
- `latent`
  高维情绪编码，供内部计算读取。
- `dominant_label`
  当前主导情绪标签。
- `intensity`
  当前情绪强度。
- `signed_valence`
  当前情绪的带符号值。

### 2.2 `AgentState`

`AgentState` 保存 agent 的动态状态，主要包括：

- `emotion`
  当前情绪的标量投影，便于兼容式读取。
- `emotion_state`
  当前多维情绪状态对象。
- `stress`
  当前心理压力水平。
- `expectation`
  对后续局势的主观预期。
- `influence_score`
  agent 在平台中的影响力近似值。
- `schemas`
  当前内部认知图式集合。
- `schema_flexibility`
  图式被调整的容易程度。
- `equilibrium`
  当前认知系统的稳定程度。
- `last_cognitive_mode`
  最近一次认知更新的模式标签。
- `dominant_emotion_label`
  最近一轮的主导离散情绪。
- `last_appraisal`
  最近一轮结构化 appraisal 结果。
- `appraisal_history`
  多轮 appraisal 的历史记录。
- `last_contagion_pad`
  最近一轮传播后的 PAD 聚合结果。
- `last_contagion_vector`
  最近一轮传播后的高维聚合向量。
- `appraisal_runtime`
  本轮 appraisal 的运行元信息。
- `latent_runtime`
  本轮 latent 生成的运行元信息。
- `memory`
  当前保存的短时记忆内容。

### 2.3 `AppraisalRecord`

`AppraisalRecord` 表示单轮 appraisal 的结构化结果，字段包括：

- `relevance`
  事件与 agent 当前目标的相关程度。
- `valence`
  事件整体偏正向还是负向。
- `goal_congruence`
  事件是否符合 agent 的目标或图式。
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

## 3. 当前模式

agent 对外只保留两种模式：

- `moe`
  主模式。认知处理采用“专家分解 + 聚合”的结构。
- `fallback`
  当外部 provider 不可用、专家输出不可解析或聚合失败时，使用本地逻辑继续运行。

初始化参数围绕这两个状态展开：

- `mode`
  当前运行模式，`moe` 或 `fallback`。
- `llm_provider`
  当前选择的 provider 名称。
- `enable_fallback`
  当外部 provider 失败时是否自动回退。

## 4. 输入加工

### 4.1 `receive_information()`

这一阶段会：

- 读取 `scenario_prompt`
- 读取当前 feed
- 写入 `memory`
- 计算一轮情绪传播

feed item 中可被读取的情绪与曝光字段包括：

- `sentiment`
  带符号情绪值，用于聚合与传播。
- `pad`
  情绪在 pleasure / arousal / dominance 三维上的坐标。
- `emotion_latent`
  高维情绪表示，用于后续计算。
- `exposure_score`
  内容在当前 feed 中的曝光强度。
- `exposure_features`
  组成曝光分数的各项特征。

### 4.2 `_extract_environment_signal()`

该函数把当前环境压缩成 `event`：

- `direction`
  当前可见内容整体偏正向还是偏负向。
- `risk`
  当前输入带来的风险或压力水平。
- `novelty`
  当前输入与既有认知结构的偏离程度。
- `consistency`
  当前输入内部是否一致。

这个 `event` 会作为 appraisal 的直接输入。

## 5. Appraisal

### 5.1 输入源

`_build_appraisal()` 会综合读取：

- `event`
  环境输入压缩后的轻量表示。
- `schemas`
  当前内部图式集合。
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

### 5.2 MoE 结构

appraisal 由 `AppraisalRouter` 负责。

`moe` 模式下，系统会组织多个 experts 共同参与判断：

- `ThreatExpert`
  处理风险、威胁与负向线索。
- `SupportExpert`
  处理支持、一致性与正向线索。
- `CopingExpert`
  处理控制感与应对能力线索。
- `SocialAmplificationExpert`
  处理曝光压力与群体传播线索。

部分 expert 可以由火山引擎 LLM 提供结构化结果，但最终输出仍由本地聚合层统一整理。

`fallback` 模式下，系统直接使用本地 appraisal 逻辑。

### 5.3 输出

`_build_appraisal()` 的返回值始终是 `AppraisalRecord`。

## 6. Emotion 更新

`_update_emotion()` 会：

- 根据 appraisal 更新 `state.emotion`
- 更新 `stress`
- 更新 `expectation`
- 生成新的 `EmotionState`

这个阶段会调用情绪表示模块来构造新的高维 latent。

## 7. Emotion Latent

高维情绪表示由 `EmotionRepresentationModule` 负责。

`moe` 模式下：

- 可以由多个 emotion-related experts 共同给出结构化语义特征
- 这些结构化特征会在本地映射成固定维度 latent

`fallback` 模式下：

- 使用本地 detector 与本地 latent 构造逻辑

编码输入可包括：

- `emotion_probs`
  离散情绪分布。
- `pad`
  低维情绪坐标。
- `sentiment`
  带符号情绪值。
- `intensity`
  情绪强度。
- `appraisal summary`
  当前 appraisal 的低维摘要。
- `contagion summary`
  当前传播结果的低维摘要。
- `schema summary`
  当前 schema 的低维摘要。
- 可选文本上下文
  当前输入文本的补充语义信息。

## 8. 情绪传播

`_apply_emotion_contagion()` 会按 `exposure_score` 加权聚合 feed 中他人的：

- `sentiment`
- `pad`
- `latent`

聚合结果保存在：

- `last_contagion_pad`
  最近一轮传播后的 PAD 聚合结果。
- `last_contagion_vector`
  最近一轮传播后的高维聚合向量。

这些结果会影响：

- `state.emotion`
- `state.emotion_state`
- `schemas["threat_sensitivity"]`
- `schemas["self_efficacy"]`

## 9. Schema 更新

schema 包括三个维度：

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

## 10. Equilibrium

`_rebalance()` 根据以下信息计算当前稳定程度：

- `controllability`
  对当前情境可控性的判断。
- `coping_potential`
  对当前应对能力的判断。
- `certainty`
  对当前判断的确定程度。
- `goal_congruence`
  当前事件是否符合目标。
- `stress`
  当前压力水平。
- `self_efficacy`
  当前自我效能水平。
- 当前情绪强度

结果写入：

- `equilibrium`
- `last_cognitive_mode`

## 11. 行为决策

`decide_action()` 当前输出五类动作：

- `browse_feed`
  继续浏览 feed。
- `reply_post`
  回复某条帖子。
- `create_post`
  发布新帖子。
- `like_post`
  点赞某条帖子。
- `share_post`
  转发某条帖子。

决策会读取：

- appraisal
- `emotion_state.pad`
- `emotion_state.intensity`
- `emotion_state.latent`
- stress
- equilibrium
- schemas

## 12. 平台动作

`act()` 负责把 agent 的内部决策映射到平台接口：

- `platform.create_post(...)`
- `platform.reply_post(...)`
- `platform.like_post(...)`
- `platform.share_post(...)`
- `platform.apply_influence(...)`
- `platform.record_idle(...)`

发帖、回复和转发时，agent 会把当前情绪状态投影成平台可写入的结构：

- `emotion_probs`
  离散情绪分布。
- `dominant_emotion`
  主导情绪标签。
- `intensity`
  情绪强度。
- `sentiment`
  带符号情绪值。
- `pad`
  低维情绪坐标。
- `emotion_latent`
  高维情绪表示。

## 13. 运行元信息

agent state 中有两个与运行模式相关的字段：

- `appraisal_runtime`
  appraisal 模块的运行元信息。
- `latent_runtime`
  latent 模块的运行元信息。

这些字段统一记录：

- `mode`
  当前实际运行的模式。
- `provider`
  当前使用的 provider。
- `model`
  当前使用的模型名称。
- `source`
  当前结果来自哪类 expert / 本地路径。
- `fallback_used`
  是否发生了回退。
- `fallback_reason`
  本次回退的原因。

## 14. 导出

`AgentRoundResult.to_dict()` 和 `SimulatedAgent.snapshot()` 会导出：

- `emotion_state`
  当前多维情绪状态快照。
- `last_appraisal`
  最近一次 appraisal 结果。
- `appraisal_history`
  多轮 appraisal 历史。
- `last_contagion_pad`
  最近传播后的 PAD 聚合结果。
- `last_contagion_vector`
  最近传播后的高维聚合结果。
- `appraisal_runtime`
  appraisal 运行路径的说明信息。
- `latent_runtime`
  latent 运行路径的说明信息。
- `memory`
  当前记忆窗口中的内容。

所有字段都保持 JSON 可序列化。
