# Backend 数据说明

## 1. 目的

本文档只做一件事：把当前 `Backend` 涉及的数据变量梳理成单一说明源。

原则：

- 同一个变量只解释一次
- 前端请求、Backend 输入、前端输出分开写
- OASIS 原始字段与 Backend 字段的映射关系明确写出
- 数学公式、超参数、阈值集中放在最后，不在字段说明里重复

相关文件：

- 转换脚本：[oasis_adapter.py](/d:/Design/Psychology/Backend/oasis_adapter.py)
- OASIS 用户数据：[user_data_36.json](/d:/Design/Psychology/Backend/data/oasis_reddit/user_data_36.json)
- OASIS 帖子对数据：[counterfactual_36.json](/d:/Design/Psychology/Backend/data/oasis_reddit/counterfactual_36.json)
- 字段映射表：[oasis_to_backend_mapping.csv](/d:/Design/Psychology/Backend/data/oasis_reddit/oasis_to_backend_mapping.csv)
- 默认转换结果：[backend_sample_input.json](/d:/Design/Psychology/Backend/examples/backend_sample_input.json)
- 接口说明：[backend-frontend-interface.md](/d:/Design/Psychology/Backend/backend-frontend-interface.md)

## 2. OASIS 原始数据字段

### 2.1 用户数据 `user_data_36.json`

| OASIS 字段 | 类型 | 中文解释 |
|---|---|---|
| `realname` | `string` | 用户真实姓名 |
| `username` | `string` | 平台用户名 |
| `bio` | `string` | 简短自我介绍 |
| `persona` | `string` | 长文本人格画像 |
| `age` | `number` | 年龄 |
| `gender` | `string` | 性别 |
| `mbti` | `string` | MBTI 类型 |
| `country` | `string` | 国家 |
| `profession` | `string` | 职业领域 |
| `interested_topics` | `string[]` | 兴趣主题列表 |

### 2.2 帖子对数据 `counterfactual_36.json`

| OASIS 字段 | 类型 | 中文解释 |
|---|---|---|
| `RS.title` | `string` | 原始帖子标题 |
| `RS.selftext` | `string` | 原始帖子正文 |
| `RC_1.body` | `string` | 评论或短文本 |
| `RC_1.group` | `string` | 极性类别，通常为 `up/down/control` |

## 3. 前端传给 Backend 的请求参数

这些字段属于“仿真控制参数”，不是 OASIS 原始字段。

| 前端字段 | 类型 | 解释 | 作用 |
|---|---|---|---|
| `num_agents` | `number` | 本次仿真使用的 agent 数量 | 从 OASIS 用户列表头部截取前 `num_agents` 个用户 |
| `rounds` | `number` | 仿真轮数 | 控制环境运行多少轮 |
| `seed_posts` | `number` | 初始种子帖数量 | 从 OASIS 帖子对中抽样前 `seed_posts` 条 |
| `seed` | `number` | 随机种子 | 控制抽样顺序与稳定扰动 |
| `feed_limit` | `number` | 每个 agent 每轮最多可见的 feed 数量 | 运行时参数 |
| `mode` | `"fallback" \| "moe"` | 认知运行模式 | 控制 appraisal 走本地或尝试外部 LLM |
| `llm_provider` | `"ollama" \| "deepseek"` | LLM 提供方 | 仅运行时使用 |
| `enable_fallback` | `boolean` | 外部失败时是否回退本地逻辑 | 仅运行时使用 |

## 4. Backend 输入字段

这里说明的是 `Backend` 实际消费的输入 JSON。字段只解释一次。

### 4.1 顶层字段

| Backend 字段 | 类型 | 中文解释 | 映射来源 |
|---|---|---|---|
| `meta` | `object` | 输入文件的元信息 | 前端参数 + 固定说明 |
| `runtime` | `object` | 运行时参数 | 前端请求参数 |
| `scenario` | `object` | 仿真场景 | OASIS 兴趣主题聚合 |
| `agents` | `object[]` | agent 列表 | OASIS 用户画像映射 |
| `relationships` | `object[]` | follow 关系图 | 由 OASIS 用户画像推断 |
| `seed_posts` | `object[]` | 初始帖子列表 | OASIS 帖子对映射 |

### 4.2 `meta`

| Backend 字段 | 类型 | 中文解释 | 映射来源 |
|---|---|---|---|
| `meta.description` | `string` | 当前输入文件的说明文本 | 固定文本 |
| `meta.num_agents` | `number` | 实际使用的 agent 数量 | `min(num_agents, OASIS用户数)` |
| `meta.rounds` | `number` | 仿真轮数 | 前端 `rounds` |
| `meta.seed_posts` | `number` | 实际生成的种子帖数量 | `min(seed_posts, OASIS帖子对数)` |
| `meta.seed` | `number` | 随机种子 | 前端 `seed` |
| `meta.source_dataset.profiles` | `string` | 用户数据文件路径 | 复制后的 `user_data_36.json` |
| `meta.source_dataset.pairs` | `string` | 帖子对文件路径 | 复制后的 `counterfactual_36.json` |

### 4.3 `runtime`

| Backend 字段 | 类型 | 中文解释 | 映射来源 |
|---|---|---|---|
| `runtime.mode` | `string` | 运行模式 | 前端 `mode` |
| `runtime.llm_provider` | `string` | LLM 提供方 | 前端 `llm_provider` |
| `runtime.enable_fallback` | `boolean` | 是否启用回退 | 前端 `enable_fallback` |
| `runtime.feed_limit` | `number` | feed 上限 | 前端 `feed_limit` |
| `runtime.appraisal_llm_ratio` | `number` | 使用 LLM appraisal 的 agent 比例 | Backend 固定默认值 `0.1` |

### 4.4 `scenario`

| Backend 字段 | 类型 | 中文解释 | 映射来源 |
|---|---|---|---|
| `scenario.scenario_id` | `string` | 场景编号 | 由 `seed` 生成，如 `oasis_reddit_42` |
| `scenario.title` | `string` | 场景标题 | 所选用户兴趣主题频次最高项 |
| `scenario.description` | `string` | 场景描述 | 所选用户兴趣主题前 3 项 |
| `scenario.environment_context` | `string[]` | 场景背景说明 | 固定模板 |

### 4.5 `agents`

#### 4.5.1 `agents[].profile`

| Backend 字段 | 类型 | 中文解释 | 映射来源 |
|---|---|---|---|
| `agents[].agent_id` | `number` | 当前仿真中的 agent 编号 | 按截取后的用户顺序从 `0` 开始编号 |
| `agents[].name` | `string` | agent 展示名称 | 优先 `username`，为空时回退 `realname` |
| `agents[].role` | `string` | 职业标签 | `profession` 规范化后得到 |
| `agents[].ideology` | `string` | 立场标签 | `bio + persona + interested_topics` 推断 |
| `agents[].communication_style` | `string` | 沟通风格标签 | `bio + persona + mbti` 推断 |

#### 4.5.2 `agents[].initial_state`

| Backend 字段 | 类型 | 中文解释 | 映射来源 |
|---|---|---|---|
| `agents[].initial_state.emotion` | `number` | 初始情绪方向，正值偏积极，负值偏消极 | 稳定扰动生成 |
| `agents[].initial_state.stress` | `number` | 初始压力水平 | `mbti + interested_topics + seed` 推断 |
| `agents[].initial_state.expectation` | `number` | 初始预期水平 | `mbti + self_efficacy + seed` 推断 |
| `agents[].initial_state.satisfaction` | `number` | 初始满意度 | 稳定扰动生成 |
| `agents[].initial_state.dopamine_level` | `number` | 初始多巴胺水平 | `mbti + seed` 推断 |
| `agents[].initial_state.influence_score` | `number` | 初始影响力 | `age + mbti + seed` 推断 |
| `agents[].initial_state.schema_flexibility` | `number` | 图式可塑性 | `mbti` 推断 |
| `agents[].initial_state.empathy_level` | `number` | 共情水平 | `mbti + profession + seed` 推断 |
| `agents[].initial_state.schemas.support_tendency` | `number` | 支持倾向 | `mbti + interested_topics` 推断 |
| `agents[].initial_state.schemas.threat_sensitivity` | `number` | 威胁敏感度 | `mbti + interested_topics` 推断 |
| `agents[].initial_state.schemas.self_efficacy` | `number` | 自我效能 | `mbti + profession` 推断 |

### 4.6 `relationships`

| Backend 字段 | 类型 | 中文解释 | 映射来源 |
|---|---|---|---|
| `relationships[].source_agent_id` | `number` | 发起关注的一方 | 当前 agent 编号 |
| `relationships[].target_agent_id` | `number` | 被关注的一方 | 当前 agent 编号 |
| `relationships[].type` | `string` | 关系类型 | 当前固定为 `follow` |

说明：

- OASIS 原始 Reddit JSON 没有现成 follow 图
- `relationships` 是推断结果，不是直接复制结果

### 4.7 `seed_posts`

| Backend 字段 | 类型 | 中文解释 | 映射来源 |
|---|---|---|---|
| `seed_posts[].author_id` | `number` | 种子帖作者的 agent 编号 | 按帖子顺序轮转分配 |
| `seed_posts[].content` | `string` | 帖子正文 | 优先 `RS.selftext`，为空时回退 `RC_1.body` |
| `seed_posts[].emotion` | `string` | 帖子主情绪标签 | `RC_1.group` 离散映射 |
| `seed_posts[].intensity` | `number` | 情绪强度 | `RC_1.group` 离散映射 |
| `seed_posts[].sentiment` | `number` | 情感极性 | `RC_1.group` 离散映射 |
| `seed_posts[].round_index` | `number` | 所属轮次 | 固定为 `0` |

## 5. 前端最终读取的输出字段

### 5.1 `SimulationSnapshot`

| 输出字段 | 类型 | 中文解释 |
|---|---|---|
| `round_index` | `number` | 当前快照对应的轮次 |
| `scenario_prompt` | `string` | 当前场景 prompt 文本 |
| `scenario` | `object` | 场景对象 |
| `platform` | `object` | 平台整体状态 |
| `agent_graph` | `object` | agent 关系图快照 |
| `agents` | `object[]` | agent 快照列表 |
| `history` | `object[]` | 每轮历史记录 |
| `export_path` | `string \| null` | 导出文件路径 |
| `_debug` | `object` | 调试信息 |

### 5.2 `platform.posts[]`

| 输出字段 | 类型 | 中文解释 |
|---|---|---|
| `post_id` | `number` | 帖子编号 |
| `author_id` | `number` | 作者 agent 编号 |
| `content` | `string` | 帖子内容 |
| `emotion` | `string` | 平台记录的情绪标签 |
| `dominant_emotion` | `string` | 主导情绪 |
| `intensity` | `number` | 情绪强度 |
| `sentiment` | `number` | 情感极性 |
| `emotion_probs` | `Record<string, number>` | 多情绪概率分布 |
| `pad` | `number[]` | Pleasure/Arousal/Dominance 三维情绪投影 |
| `emotion_latent` | `number[]` | 情绪潜变量向量 |
| `like_count` | `number` | 点赞数 |
| `share_count` | `number` | 转发数 |
| `shared_post_id` | `number \| null` | 若为转发帖则指向原帖 |
| `round_index` | `number` | 所属轮次 |

### 5.3 `agents[].profile`

| 输出字段 | 类型 | 中文解释 |
|---|---|---|
| `agent_id` | `number` | agent 编号 |
| `name` | `string` | 展示名称 |
| `role` | `string` | 职业标签 |
| `ideology` | `string` | 立场标签 |
| `communication_style` | `string` | 沟通风格标签 |

### 5.4 `agents[].state`

| 输出字段 | 类型 | 中文解释 |
|---|---|---|
| `emotion` | `number` | 当前标量情绪值 |
| `emotion_state` | `object` | 多维情绪状态 |
| `stress` | `number` | 当前压力 |
| `expectation` | `number` | 当前预期 |
| `satisfaction` | `number` | 当前满意度 |
| `dopamine_level` | `number` | 当前多巴胺水平 |
| `performance_prediction` | `number` | 表现预测值 |
| `influence_score` | `number` | 当前影响力 |
| `schemas` | `object` | 当前认知 schema |
| `schema_flexibility` | `number` | 图式可塑性 |
| `equilibrium_index` | `number` | 稳态指数 |
| `last_cognitive_mode` | `string` | 上一轮认知模式 |
| `dominant_emotion_label` | `string` | 当前主导情绪标签 |
| `empathy_level` | `number` | 当前共情水平 |
| `empathized_negative_emotion` | `number` | 被感染到的负面情绪强度 |
| `dopamine_prediction_error` | `number` | 多巴胺预测误差 |
| `moral_reward` | `number` | 道德奖励 |
| `social_influence_reward` | `number` | 社会影响奖励 |
| `semantic_similarity` | `number` | 语义相似度 |
| `explicit_tom_triggered` | `boolean` | 是否触发显式心智理论 |
| `beliefs` | `Record<string, number>` | 信念向量 |
| `desires` | `Record<string, number>` | 欲望向量 |
| `intentions` | `Record<string, number>` | 意图向量 |
| `knowledge` | `Record<string, unknown>` | 当前知识摘要 |
| `epsilon` | `number` | 不可预测性指标 |
| `zeta` | `number` | 目标相关信号 |
| `coping_potential` | `number` | 应对潜力 |
| `performance` | `number` | 当前表现值 |
| `confirmation` | `number` | 确认度 |
| `last_appraisal` | `object \| null` | 最近一次 appraisal 结果 |
| `last_contagion_pad` | `number[]` | 最近情绪感染的 PAD 向量 |
| `last_contagion_vector` | `number[]` | 最近情绪感染的潜向量 |
| `appraisal_runtime` | `object` | appraisal 来源元信息 |
| `latent_runtime` | `object` | latent 来源元信息 |
| `action_runtime` | `Record<string, object>` | 各动作耗时 |
| `memory_size` | `number` | 记忆条目数 |
| `appraisal_count` | `number` | appraisal 次数 |

## 6. 数学公式与阈值

这里只列公式和阈值，不重复解释变量含义。

### 6.1 基础函数

\[
\mathrm{clip}(x;l,h)=\max(l,\min(h,x))
\]

\[
\mathrm{signed}(x;L)=\max(-L,\min(L,x))
\]

\[
\mathrm{stable\_range}(a,b)=a+(b-a)\cdot u,\quad u\in[0,1]
\]

其中 `u` 来自基于 SHA-256 的稳定哈希。

### 6.2 MBTI 数值化

\[
\mathrm{extroversion}=
\begin{cases}
0.64,& \text{MBTI[0]=E}\\
0.42,& \text{otherwise}
\end{cases}
\]

\[
\mathrm{intuition}=
\begin{cases}
0.64,& \text{MBTI[1]=N}\\
0.44,& \text{otherwise}
\end{cases}
\]

\[
\mathrm{feeling}=
\begin{cases}
0.68,& \text{MBTI[2]=F}\\
0.40,& \text{otherwise}
\end{cases}
\]

\[
\mathrm{judging}=
\begin{cases}
0.62,& \text{MBTI[3]=J}\\
0.46,& \text{otherwise}
\end{cases}
\]

### 6.3 中间量

\[
\mathrm{empathy}=0.40+0.35\cdot \mathrm{feeling}+I_{\text{care profession}}\cdot 0.08
\]

\[
\mathrm{efficacy}=0.34+0.24\cdot \mathrm{judging}+I_{\text{tech profession}}\cdot 0.08
\]

\[
\mathrm{support}=0.30+0.30\cdot \mathrm{feeling}+I_{\text{social topic}}\cdot 0.08
\]

\[
\mathrm{threat}=0.24+0.18\cdot \mathrm{judging}+I_{\text{risk topic}}\cdot 0.12
\]

### 6.4 初始状态公式

\[
\mathrm{emotion}=\mathrm{signed}(\mathrm{stable\_range}(-0.16,0.16))
\]

\[
\mathrm{stress}=\mathrm{clip}(0.15+0.12\cdot(1-\mathrm{intuition})+0.22\cdot \mathrm{threat}+\mathrm{stable\_range}(0,0.08))
\]

\[
\mathrm{expectation}=\mathrm{clip}(0.42+0.12\cdot \mathrm{extroversion}+0.16\cdot \mathrm{efficacy}+\mathrm{stable\_range}(-0.03,0.03))
\]

\[
\mathrm{satisfaction}=\mathrm{signed}(\mathrm{stable\_range}(-0.06,0.10))
\]

\[
\mathrm{dopamine\_level}=\mathrm{clip}(0.38+0.14\cdot \mathrm{extroversion}+\mathrm{stable\_range}(0,0.12))
\]

\[
\mathrm{influence\_score}=\mathrm{clip}(0.24+\frac{\min(\mathrm{age},55)}{100}+0.14\cdot \mathrm{extroversion}+\mathrm{stable\_range}(0,0.12))
\]

\[
\mathrm{schema\_flexibility}=\mathrm{clip}(0.30+0.24\cdot \mathrm{intuition}+I_{\text{P}}\cdot 0.10)
\]

\[
\mathrm{empathy\_level}=\mathrm{clip}(\mathrm{empathy}+\mathrm{stable\_range}(0,0.06))
\]

### 6.5 关系图评分

\[
\mathrm{score}=0.55\cdot \mathrm{shared\_topics}
+0.18\cdot I_{\text{same country}}
+0.10\cdot I_{\text{same MBTI prefix}}
+0.12\cdot I_{\text{same profession}}
+\epsilon
\]

其中：

\[
\epsilon \in [0,0.05]
\]

### 6.6 帖子情绪映射

- `up -> (confidence, 0.58, 0.64)`
- `down -> (anger, -0.56, 0.70)`
- `control/other -> (calm, 0.04, 0.30)`

### 6.7 硬阈值与范围

| 参数 | 值 |
|---|---:|
| `max_agents` | `36` |
| `relationship score threshold` | `0.60` |
| `top relationship candidates` | `2` |
| `minimum fallback relationship count` | `1` |
| `age cap` | `55` |
| `emotion range` | `[-0.16, 0.16]` |
| `stress noise` | `[0.00, 0.08]` |
| `expectation noise` | `[-0.03, 0.03]` |
| `satisfaction range` | `[-0.06, 0.10]` |
| `dopamine noise` | `[0.00, 0.12]` |
| `influence noise` | `[0.00, 0.12]` |
| `empathy noise` | `[0.00, 0.06]` |
| `relationship noise` | `[0.00, 0.05]` |
| `global clip` | `[0, 1]` |
| `global signed clip` | `[-1, 1]` |

