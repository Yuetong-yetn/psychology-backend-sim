# 前端对接

```ts
const BASE_URL = "http://localhost:8000";
```

## 先调这 4 个接口

### `GET /api/debug/options`

前端启动时先调用，拿表单默认值、范围和枚举。

```ts
type CognitiveMode = "fallback" | "moe";
type LlmProvider = "ollama" | "deepseek";

interface DebugRunRequest {
  num_agents: number;
  rounds: number;
  seed_posts: number;
  seed: number;
  feed_limit: number;
  mode: CognitiveMode;
  llm_provider: LlmProvider;
  enable_fallback: boolean;
}

interface DebugRunLimits {
  min_agents: number;
  max_agents: number;
  min_rounds: number;
  max_rounds: number;
  min_seed_posts: number;
  max_seed_posts: number;
  min_feed_limit: number;
  max_feed_limit: number;
  min_seed: number;
  max_seed: number;
}

interface DebugOptionsResponse {
  debug_run_defaults: DebugRunRequest;
  debug_run_limits: DebugRunLimits;
  allowed_modes: CognitiveMode[];
  allowed_providers: LlmProvider[];
  notes: {
    mode: string;
    llm_provider: string;
    enable_fallback: string;
  };
}
```

来源：

- [frontend_settings.py](./config/frontend_settings.py)
- [webapp.py](./webapp.py)

### `POST /api/debug/run-sample/start`

前端提交表单后调这个接口，启动异步任务。

请求体：

```ts
interface DebugRunRequest {
  num_agents: number;
  rounds: number;
  seed_posts: number;
  seed: number;
  feed_limit: number;
  mode: "fallback" | "moe";
  llm_provider: "ollama" | "deepseek";
  enable_fallback: boolean;
}
```

响应体：

```ts
interface DebugRunJob {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  stage: string;
  message: string;
  created_at: number;
  updated_at: number;
  request: DebugRunRequest;
  snapshot: SimulationSnapshot | null;
  error: string | null;
  completed_rounds: number | null;
  total_rounds: number | null;
}
```

来源：

- [webapp.py](./webapp.py)

### `GET /api/debug/run-sample/{job_id}`

拿到 `job_id` 后轮询这个接口，直到 `status === "completed"`。

```ts
type DebugRunJobResponse = DebugRunJob;
```

来源：

- [webapp.py](./webapp.py)

### `GET /api/debug/snapshot`

如果只想拿最近一次结果，直接调这个接口。

```ts
type DebugSnapshotResponse = SimulationSnapshot;
```

来源：

- [webapp.py](./webapp.py)

## 直接这样调用

1. 调 `GET /api/debug/options`
2. 用返回的 `debug_run_defaults` 初始化表单
3. 用户提交后调 `POST /api/debug/run-sample/start`
4. 轮询 `GET /api/debug/run-sample/{job_id}`
5. 当 `status === "completed"` 时，读取 `snapshot`

## 提交给后端的数据

当前默认值对应的请求体是：

```json
{
  "num_agents": 20,
  "rounds": 4,
  "seed_posts": 6,
  "seed": 42,
  "feed_limit": 5,
  "mode": "moe",
  "llm_provider": "ollama",
  "enable_fallback": true
}
```

字段含义：

- `num_agents`：agent 数量
- `rounds`：轮数
- `seed_posts`：初始帖子数
- `seed`：随机种子
- `feed_limit`：每个 agent 每轮可见的 feed 上限
- `mode`：`fallback` 表示 appraisal 全本地，`moe` 表示按当前运行时规则尝试使用外部 provider
- `llm_provider`：外部模型提供方
- `enable_fallback`：外部请求失败时是否回退到本地规则

来源：

- [webapp.py](./webapp.py)
- [generate_backend_input.py](./generate_backend_input.py)

## 后端返回的主结构

```ts
interface SimulationSnapshot {
  round_index: number;
  scenario_prompt: string;
  scenario: Scenario;
  platform: PlatformSnapshot;
  agent_graph: AgentGraphSnapshot;
  agents: AgentSnapshot[];
  history: RoundHistory[];
  export_path?: string | null;
  _debug?: SnapshotDebugMeta;
}
```

来源：

- [env.py](./environment/env.py)
- [webapp.py](./webapp.py)

## 前端优先使用这些字段

### 场景

```ts
interface Scenario {
  scenario_id: string;
  title: string;
  description: string;
  environment_context: string[];
}
```

来源：

- [generate_backend_input.py](./generate_backend_input.py)

### 平台帖子

```ts
interface PlatformSnapshot {
  current_round: number;
  scenario_prompt: string;
  agent_count: number;
  agents: Record<string, string>;
  posts: PlatformPost[];
  replies: PlatformReply[];
  likes: PlatformLike[];
  shares: PlatformShare[];
  influence_events: PlatformInfluenceEvent[];
  traces: PlatformTrace[];
  trace_size: number;
  runtime_profile: Record<string, RuntimeMetric>;
}

interface PlatformPost {
  post_id: number;
  author_id: number;
  content: string;
  emotion: string;
  dominant_emotion: string;
  intensity: number;
  sentiment: number;
  emotion_probs: Record<string, number>;
  pad: number[];
  emotion_latent: number[];
  like_count: number;
  share_count: number;
  shared_post_id: number | null;
  round_index: number;
}

interface PlatformReply {
  reply_id: number;
  post_id: number;
  author_id: number;
  content: string;
  emotion: string;
  dominant_emotion: string;
  intensity: number;
  sentiment: number;
  emotion_probs: Record<string, number>;
  pad: number[];
  emotion_latent: number[];
  round_index: number;
}

interface PlatformLike {
  like_id: number;
  post_id: number;
  agent_id: number;
  round_index: number;
}

interface PlatformShare {
  share_id: number;
  post_id: number;
  agent_id: number;
  round_index: number;
}

interface PlatformInfluenceEvent {
  round_index: number;
  source_agent_id: number;
  target_agent_id: number;
  delta: number;
  reason: string;
}
```

来源：

- [platform.py](./social_platform/platform.py)

### Agent

```ts
interface AgentSnapshot {
  profile: AgentProfile;
  state: AgentStateSnapshot;
}

interface AgentProfile {
  agent_id: number;
  name: string;
  role: string;
  ideology: string;
  communication_style: string;
}

interface AgentStateSnapshot {
  emotion: number;
  emotion_state: EmotionState;
  stress: number;
  expectation: number;
  satisfaction: number;
  dopamine_level: number;
  performance_prediction: number;
  influence_score: number;
  schemas: AgentSchemas;
  schema_flexibility: number;
  equilibrium_index: number;
  last_cognitive_mode: string;
  dominant_emotion_label: string;
  empathy_level: number;
  empathized_negative_emotion: number;
  dopamine_prediction_error: number;
  moral_reward: number;
  social_influence_reward: number;
  semantic_similarity: number;
  explicit_tom_triggered: boolean;
  beliefs: Record<string, number>;
  desires: Record<string, number>;
  intentions: Record<string, number>;
  knowledge: Record<string, unknown>;
  epsilon: number;
  zeta: number;
  coping_potential: number;
  performance: number;
  confirmation: number;
  last_appraisal: AppraisalRecord | null;
  last_contagion_pad: number[];
  last_contagion_vector: number[];
  appraisal_runtime: RuntimeSourceMeta;
  latent_runtime: RuntimeSourceMeta;
  action_runtime: Record<string, RuntimeMetric>;
  memory_size: number;
  appraisal_count: number;
}

interface AgentSchemas {
  support_tendency: number;
  threat_sensitivity: number;
  self_efficacy: number;
}

interface EmotionState {
  emotion_probs: Record<string, number>;
  pad: number[];
  latent: number[];
  dominant_label: string;
  intensity: number;
  signed_valence: number;
}

interface MemoryItem {
  round_index: number;
  source: string;
  content: string;
  valence: number;
}

interface AppraisalRecord {
  relevance: number;
  valence: number;
  goal_conduciveness: number;
  controllability: number;
  agency: string;
  certainty: number;
  novelty: number;
  coping_potential: number;
  unpredictability: number;
  goal_relevance_signal: number;
  performance: number;
  confirmation: number;
  dominant_emotion: string;
  emotion_intensity: number;
  cognitive_mode: string;
}

interface RuntimeSourceMeta {
  mode: string;
  provider: string | null;
  model: string | null;
  source: string | null;
  fallback_used: boolean;
  fallback_reason: string | null;
}

interface RuntimeMetric {
  count: number;
  total_ms: number;
  avg_ms: number;
}
```

来源：

- [agent.py](./social_agent/agent.py)

### 图和逐轮历史

```ts
interface AgentGraphSnapshot {
  num_nodes: number;
  num_edges: number;
  edges: AgentGraphEdge[];
}

type AgentGraphEdge = [number, number];

interface RoundHistory {
  round_index: number;
  results: Record<string, AgentRoundResult>;
}

interface AgentRoundResult {
  profile: AgentProfile;
  state: AgentStateSnapshot;
  decision: AgentDecision;
  behavior_output: BehaviorOutput;
}

interface AgentDecision {
  action: string;
  content: string;
  target_post_id: number | null;
  target_agent_id: number | null;
  metadata: Record<string, unknown>;
  influence_delta: number;
  reason: string;
  suggested_action: string;
  suggested_actions: string[];
}

interface BehaviorOutput {
  primary_action: string;
  stimulus_excerpt: string;
  public_behavior_summary: string;
  simulated_public_content: string;
  state_hint: Record<string, number>;
  cam_summary: string[];
  explicit_tom_triggered: boolean;
  backend_action: string;
  round_index: number;
}
```

来源：

- [env.py](./environment/env.py)
- [agent_graph.py](./social_agent/agent_graph.py)
- [agent.py](./social_agent/agent.py)

### `_debug`

```ts
interface SnapshotDebugMeta {
  exposedFrontendParams: string[];
  providerBehavior: {
    mode: string | null;
    llm_provider: string | null;
    enable_fallback: boolean | null;
  };
  whyResultsAppearWithoutApiKey: string;
  autoRunOnSnapshot: boolean;
  historyRounds: number;
}
```

来源：

- [webapp.py](./webapp.py)

## 前端渲染时建议直接取这两块

```ts
const postsJson = snapshot.platform.posts;

const llmAgentsJson = snapshot.agents.filter((agent) => {
  const runtime = agent.state.appraisal_runtime || {};
  const fallbackReason = String(runtime.fallback_reason || "").toLowerCase();

  return (
    fallbackReason !== "ratio_routed_to_local" &&
    fallbackReason !== "mode_forced_fallback"
  );
});
```

这条规则表示：

- 按比例直接走本地 appraisal 的 agent 不显示
- 全局 `mode = "fallback"` 下被强制本地执行的 agent 不显示
- 原本应走 MoE 路径、但外部请求失败后 fallback 到本地的 agent 仍然显示

## `traces` 按这种方式处理

先判断 `type`，再读字段，不要直接假设所有 trace 字段都一样。

当前代码里实际会出现的 `type` 至少包括：

- `register_agent`
- `create_post`
- `reply_post`
- `like_post`
- `share_post`
- `apply_influence`
- `do_nothing`
- `commit_round`

```ts
type PlatformTrace = Record<string, unknown> & {
  type: string;
  round_index?: number;
};
```

来源：

- [platform.py](./social_platform/platform.py)

## `history.results.state` 和 `snapshot.agents[].state` 不要混用

`snapshot.agents[].state` 当前稳定可用的是：

- 基础状态字段
- `appraisal_runtime`
- `latent_runtime`
- `action_runtime`
- `memory_size`
- `appraisal_count`

只有在 `history.results[agentId].state` 里，当前样例和代码中还会带：

- `appraisal_history`
- `memory`

如果前端只是做主界面展示，优先用：

- `snapshot.platform`
- `snapshot.agents`

如果前端要做逐轮回放，再读取：

- `snapshot.history`

## 可直接使用的请求代码

```ts
export async function getOptions() {
  const res = await fetch(`${BASE_URL}/api/debug/options`);
  if (!res.ok) {
    throw new Error(`获取 options 失败: ${res.status}`);
  }
  return (await res.json()) as DebugOptionsResponse;
}

export async function startSimulation(payload: DebugRunRequest) {
  const res = await fetch(`${BASE_URL}/api/debug/run-sample/start`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`启动仿真失败: ${res.status}`);
  }

  return (await res.json()) as DebugRunJob;
}

export async function getJob(jobId: string) {
  const res = await fetch(`${BASE_URL}/api/debug/run-sample/${jobId}`);
  if (!res.ok) {
    throw new Error(`获取任务失败: ${res.status}`);
  }
  return (await res.json()) as DebugRunJob;
}

export async function getLatestSnapshot() {
  const res = await fetch(`${BASE_URL}/api/debug/snapshot`);
  if (!res.ok) {
    throw new Error(`获取快照失败: ${res.status}`);
  }
  return (await res.json()) as SimulationSnapshot;
}
```
