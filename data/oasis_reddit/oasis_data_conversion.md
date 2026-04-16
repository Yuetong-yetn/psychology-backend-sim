# OASIS 数据转换说明

本文档说明 `data/oasis_reddit` 数据如何生成 Psychology Backend 输入负载，以及这些字段如何进入仿真、快照和数据库。

## 相关文件

- `data/oasis_reddit/oasis_adapter.py`：OASIS 到后端输入负载的转换脚本。
- `examples/generate_backend_input.py`：生成默认后端输入文件。
- `examples/start.py`：运行仿真并写出快照。
- `data/oasis_reddit/user_data_36.json`：OASIS 用户数据。
- `data/oasis_reddit/counterfactual_36.json`：OASIS 帖子对数据。
- `data/oasis_reddit/oasis_to_backend_mapping.csv`：字段映射表。
- `examples/backend_sample_input.json`：默认输入样例。
- `backend-frontend-interface.md`：快照和数据库对接说明。

## OASIS 原始字段

### `user_data_36.json`

| 字段 | 类型 | 含义 |
|---|---|---|
| `realname` | `string` | 用户真实姓名 |
| `username` | `string` | 平台用户名 |
| `bio` | `string` | 简短自我介绍 |
| `persona` | `string` | 人格画像文本 |
| `age` | `number` | 年龄 |
| `gender` | `string` | 性别 |
| `mbti` | `string` | MBTI 类型 |
| `country` | `string` | 国家 |
| `profession` | `string` | 职业领域 |
| `interested_topics` | `string[]` | 兴趣主题 |

### `counterfactual_36.json`

| 字段 | 类型 | 含义 |
|---|---|---|
| `RS.title` | `string` | 帖子标题 |
| `RS.selftext` | `string` | 帖子正文 |
| `RC_1.body` | `string` | 评论或短文本 |
| `RC_1.group` | `string` | 情绪极性分组，常见值为 `up`、`down`、`control` |

## 运行控制参数

这些参数控制输入生成和仿真运行：

| 字段 | 类型 | 含义 | 用途 |
|---|---|---|---|
| `num_agents` | `number` | agent 数量 | 从 OASIS 用户列表中选取对应数量用户 |
| `rounds` | `number` | 仿真轮数 | 控制环境运行轮次 |
| `seed_posts` | `number` | 初始帖子数量 | 从 OASIS 帖子对中选取对应数量帖子 |
| `seed` | `number` | 随机种子 | 控制抽样顺序和稳定扰动 |
| `feed_limit` | `number` | feed 上限 | 控制每个 agent 每轮可见内容数量 |
| `mode` | `"fallback" \| "moe"` | 认知运行模式 | 控制 appraisal 路径 |
| `llm_provider` | `"ollama" \| "deepseek"` | LLM provider | 控制外部 provider |
| `enable_fallback` | `boolean` | fallback 开关 | 控制 provider 不可用时的本地执行 |
| `appraisal_llm_ratio` | `number` | LLM appraisal 比例 | 控制进入 LLM appraisal 路径的 agent 比例 |

## Backend 输入字段

### 顶层结构

| 字段 | 类型 | 含义 | 来源 |
|---|---|---|---|
| `meta` | `object` | 输入文件元信息 | 运行控制参数和数据来源 |
| `runtime` | `object` | 运行时参数 | 运行控制参数 |
| `scenario` | `object` | 仿真场景 | OASIS 兴趣主题聚合 |
| `agents` | `object[]` | agent 列表 | OASIS 用户画像映射 |
| `relationships` | `object[]` | follow 关系图 | 用户画像相似度推断 |
| `seed_posts` | `object[]` | 初始帖子列表 | OASIS 帖子对映射 |

### `meta`

| 字段 | 类型 | 含义 |
|---|---|---|
| `meta.description` | `string` | 输入文件说明 |
| `meta.num_agents` | `number` | agent 数量 |
| `meta.rounds` | `number` | 仿真轮数 |
| `meta.seed_posts` | `number` | 初始帖子数量 |
| `meta.seed` | `number` | 随机种子 |
| `meta.source_dataset.profiles` | `string` | 用户数据路径 |
| `meta.source_dataset.pairs` | `string` | 帖子对数据路径 |

### `runtime`

| 字段 | 类型 | 含义 |
|---|---|---|
| `runtime.mode` | `string` | 认知运行模式 |
| `runtime.llm_provider` | `string` | LLM provider |
| `runtime.enable_fallback` | `boolean` | fallback 开关 |
| `runtime.feed_limit` | `number` | feed 上限 |
| `runtime.appraisal_llm_ratio` | `number` | LLM appraisal 比例 |

### `scenario`

| 字段 | 类型 | 含义 |
|---|---|---|
| `scenario.scenario_id` | `string` | 场景编号 |
| `scenario.title` | `string` | 场景标题 |
| `scenario.description` | `string` | 场景描述 |
| `scenario.environment_context` | `string[]` | 场景背景说明 |

### `agents`

| 字段 | 类型 | 含义 | 来源 |
|---|---|---|---|
| `agents[].agent_id` | `number` | agent 编号 | 选中用户顺序 |
| `agents[].name` | `string` | 展示名称 | `username` 或 `realname` |
| `agents[].role` | `string` | 职业标签 | `profession` |
| `agents[].ideology` | `string` | 立场标签 | `bio`、`persona`、`interested_topics` |
| `agents[].communication_style` | `string` | 沟通风格 | `bio`、`persona`、`mbti` |
| `agents[].initial_state.emotion` | `number` | 初始情绪方向 | 稳定扰动 |
| `agents[].initial_state.stress` | `number` | 初始压力 | `mbti`、`interested_topics`、`seed` |
| `agents[].initial_state.expectation` | `number` | 初始预期 | `mbti`、自我效能、`seed` |
| `agents[].initial_state.satisfaction` | `number` | 初始满意度 | 稳定扰动 |
| `agents[].initial_state.dopamine_level` | `number` | 初始多巴胺水平 | `mbti`、`seed` |
| `agents[].initial_state.influence_score` | `number` | 初始影响力 | `age`、`mbti`、`seed` |
| `agents[].initial_state.schema_flexibility` | `number` | 图式可塑性 | `mbti` |
| `agents[].initial_state.empathy_level` | `number` | 共情水平 | `mbti`、`profession`、`seed` |
| `agents[].initial_state.schemas.support_tendency` | `number` | 支持倾向 | `mbti`、`interested_topics` |
| `agents[].initial_state.schemas.threat_sensitivity` | `number` | 威胁敏感度 | `mbti`、`interested_topics` |
| `agents[].initial_state.schemas.self_efficacy` | `number` | 自我效能 | `mbti`、`profession` |

### `relationships`

| 字段 | 类型 | 含义 |
|---|---|---|
| `relationships[].source_agent_id` | `number` | 发起关注的 agent |
| `relationships[].target_agent_id` | `number` | 被关注的 agent |
| `relationships[].type` | `string` | 关系类型，值为 `follow` |

### `seed_posts`

| 字段 | 类型 | 含义 | 来源 |
|---|---|---|---|
| `seed_posts[].author_id` | `number` | 帖子作者 agent 编号 | 按帖子顺序分配 |
| `seed_posts[].content` | `string` | 帖子正文 | `RS.selftext` 或 `RC_1.body` |
| `seed_posts[].emotion` | `string` | 情绪标签 | `RC_1.group` |
| `seed_posts[].intensity` | `number` | 情绪强度 | `RC_1.group` |
| `seed_posts[].sentiment` | `number` | 情感极性 | `RC_1.group` |
| `seed_posts[].round_index` | `number` | 所属轮次 | `0` |

## 输出字段

### `SimulationSnapshot`

| 字段 | 类型 | 含义 |
|---|---|---|
| `round_index` | `number` | 快照轮次 |
| `scenario_prompt` | `string` | 场景 prompt |
| `scenario` | `object` | 场景对象 |
| `platform` | `object` | 平台状态 |
| `agent_graph` | `object` | agent 关系图 |
| `agents` | `object[]` | agent 快照 |
| `history` | `object[]` | 轮次历史 |
| `export_path` | `string \| null` | 导出路径 |
| `_debug` | `object` | 运行调试信息 |

### `platform.posts[]`

| 字段 | 类型 | 含义 |
|---|---|---|
| `post_id` | `number` | 帖子编号 |
| `author_id` | `number` | 作者 agent 编号 |
| `content` | `string` | 帖子内容 |
| `emotion` | `string` | 平台情绪标签 |
| `dominant_emotion` | `string` | 主导情绪 |
| `intensity` | `number` | 情绪强度 |
| `sentiment` | `number` | 情感极性 |
| `emotion_probs` | `Record<string, number>` | 情绪概率分布 |
| `pad` | `number[]` | PAD 情绪投影 |
| `emotion_latent` | `number[]` | 情绪 latent 向量 |
| `like_count` | `number` | 点赞数 |
| `share_count` | `number` | 转发数 |
| `shared_post_id` | `number \| null` | 被转发帖子编号 |
| `round_index` | `number` | 所属轮次 |

### `agents[].state`

| 字段 | 类型 | 含义 |
|---|---|---|
| `emotion` | `number` | 标量情绪值 |
| `emotion_state` | `object` | 多维情绪状态 |
| `stress` | `number` | 压力 |
| `expectation` | `number` | 预期 |
| `satisfaction` | `number` | 满意度 |
| `dopamine_level` | `number` | 多巴胺水平 |
| `influence_score` | `number` | 影响力 |
| `schemas` | `object` | 认知 schema |
| `schema_flexibility` | `number` | 图式可塑性 |
| `equilibrium_index` | `number` | 稳态指数 |
| `empathy_level` | `number` | 共情水平 |
| `last_appraisal` | `object \| null` | 最近一次 appraisal 摘要 |
| `memory_size` | `number` | 记忆条目数 |
| `_debug` | `object` | 调试字段 |

## 数学公式与阈值

### 基础函数

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

### MBTI 数值化

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

### 中间量

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

### 初始状态

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

### 关系图评分

\[
\mathrm{score}=0.55\cdot \mathrm{shared\_topics}
+0.18\cdot I_{\text{same country}}
+0.10\cdot I_{\text{same MBTI prefix}}
+0.12\cdot I_{\text{same profession}}
+\epsilon
\]

\[
\epsilon \in [0,0.05]
\]

### 帖子情绪映射

- `up -> (confidence, 0.58, 0.64)`
- `down -> (anger, -0.56, 0.70)`
- `control/other -> (calm, 0.04, 0.30)`

### 固定阈值

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
