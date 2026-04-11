# AGENT.md - Psychology Backend 开发约定

## 项目定位

Psychology Backend 是一个面向社会议题传播与群体心理仿真的后端工程。
核心职责是在给定场景、agent 画像、关系网络与种子内容的前提下，模拟多轮平台互动、情绪演化与行为决策，并导出可分析的仿真快照。

agent 之间没有显式对话协议，主要通过平台内容与曝光链路间接影响彼此：

`浏览 feed -> appraisal -> 情绪/图式更新 -> 平台行为 -> 影响其他 agent`

## 架构分层

- `environment/`：环境生命周期、轮次调度、快照导出
- `social_agent/`：agent 心理状态、appraisal、行为决策
- `social_platform/`：平台状态、feed、动作分发、trace
- `services/`：MoE / provider 调用与 fallback
- `config/`：前后端参数配置

## 关键文件

- `social_agent/agent.py`：agent 主体，定义 profile、state、appraisal、decision、round result
- `social_agent/agent_action.py`：把 agent 决策映射为平台动作
- `social_agent/agent_environment.py`：将 scenario 和 feed 组织成观察文本
- `social_platform/platform.py`：平台数据结构与交互入口
- `environment/env.py`：多轮仿真调度
- `run_backend_input.py`：从 JSON payload 直接运行仿真
- `viewer.html`：调试结果查看器

## 单轮执行顺序

单个 agent 的一轮执行遵循以下顺序：

1. 读取当前 `feed` 与 `scenario_prompt`
2. 将外部输入压缩为环境事件信号
3. 进行 appraisal 融合
4. 更新情绪状态、schema、CAM memory、equilibrium
5. 形成 beliefs / intentions
6. 产出决策并投影为平台动作

`agent.py` 的主入口是 `SimulatedAgent.run_round()`。

## AgentState 约定

`AgentState` 现在按“主状态 + 派生字段”组织。

### 主状态字段

- `emotion`：兼容旧输入/输出的标量情绪效价
- `emotion_state`：规范的多维情绪状态，包含 `emotion_probs / pad / latent / dominant_label`
- `stress`：当前压力水平
- `expectation`：对本轮表现的滚动预期
- `satisfaction`：跨轮累计的主观结果评价
- `dopamine_level`：奖励驱动基线
- `performance_prediction`：用于预测误差更新的表现预测
- `influence_score`：平台影响力
- `schemas`：支持倾向、威胁敏感、自我效能等图式
- `schema_flexibility`：顺应新信息的倾向
- `equilibrium`：当前整合后的心理稳态
- `equilibrium_index`：更快的稳态扰动指标
- `last_cognitive_mode`：最近一次主要认知模式
- `empathy_level`：共情倾向
- `empathized_negative_emotion`：对外部负面情绪的当前共情吸收
- `dopamine_prediction_error`：最近一轮奖励预测误差
- `moral_reward`：亲社会/规范一致带来的内部奖励
- `social_influence_reward`：预期社会影响收益
- `semantic_similarity`：当前事件与 CAM memory 的语义相似度
- `explicit_tom_triggered`：是否触发显式 ToM 式观察
- `beliefs / desires / intentions`：认知产物
- `knowledge`：结构化情境知识与 CAM 摘要
- `epsilon`：不可预测性 / surprise 信号
- `zeta`：有符号目标相关性信号
- `last_appraisal`：最近一轮 appraisal
- `appraisal_history`：短窗口 appraisal 历史
- `last_contagion_pad / last_contagion_vector`：最近一轮情绪传染缓存
- `appraisal_runtime / latent_runtime`：模块运行元数据
- `memory`：最近记忆窗口
- `schemata_graph`：CAM memory graph

### 已移除的冗余状态字段

以下字段不再作为独立变量存储，而是改为即时推导：

- `dominant_emotion_label`
  由 `emotion_state.dominant_label` 推导
- `coping_potential`
  由 `last_appraisal.coping_potential` 推导
- `performance`
  由 `last_appraisal.performance` 推导
- `confirmation`
  由 `last_appraisal.confirmation` 推导
- `belief_embeddings`
  改为按需从 `schemata_graph.global_embedding()` 获取
- `e_t`
  当前事件向量不再作为冗余状态缓存
- `m_t`
  记忆向量不再作为冗余状态缓存

这条约定的目标是：

- 一个心理量只保留一个主来源
- 快照中允许导出派生值
- 但派生值不再写回 `AgentState` 形成镜像字段

## 输出与调试

当前 agent 导出重点包括：

- `emotion_state`
- `appraisal_history`
- `beliefs / desires / intentions`
- `memory`
- `appraisal_runtime`
- `latent_runtime`

因此新增逻辑时，优先保证：

- 状态可解释
- 快照可追踪
- 导出字段与真实运行逻辑一致

## 平台动作约定

当前主要平台动作包括：

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

注意：

- agent 内部 `decision.action` 与平台建议动作 `suggested_action` 是两层语义
- 新增平台动作时，要同步评估 trace、feed 可见性、snapshot 导出是否受影响

## Provider / Fallback 约定

- `mode='moe'`：优先走 MoE 路径，可调用外部 provider
- `mode='fallback'`：直接走本地逻辑
- `llm_provider='ollama|deepseek'`：仅指定外部 provider 类型，不改变上层 mode

新增 provider 或 expert 时，需要保证：

- 输入输出保持 JSON 友好
- provider 失败时不阻断主仿真流程
- 运行来源、fallback 状态等元信息可被记录

## 开发要求

- 新增心理变量时，必须同步考虑初始化、单轮更新、导出结构与调试可读性
- 如果一个值能够稳定从另一个主状态字段推导出来，优先做派生字段，不要再加镜像状态
- 修改 `AgentState` 后，必须同步更新 `agent.py` 的注释与本文件文档
- 新增导出字段后，要确认 `viewer.html` 与调试接口不会因缺字段报错
