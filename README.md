# Psychology Backend

Psychology Backend 是一个用于社会讨论动态、情绪变化和平台交互的本地仿真后端。它接收原生 JSON 负载，在社交平台上运行多轮 agent 活动，并返回结构化的仿真快照，用于前端渲染和下游分析。

## 系统功能

- 从 `scenario`、`agents`、`relationships` 和 `seed_posts` 构建仿真
- 通过环境调度器运行多 agent 轮次
- 让 agent 浏览 feed 内容、更新内部状态并执行平台动作
- 导出包含平台状态、帖子、agent 状态、历史和运行时元数据的完整快照
- 提供用于运行仿真并返回结构化前端数据的 FastAPI 服务

## 运行时模型

当前运行时使用两条不同的认知路径：

- `appraisal`
  - Appraisal 是事件评估步骤，用于估计相关性、效价、可控性、确定性、应对潜力以及相关决策信号。
  - 后端比例参数控制哪些 agents 使用外部 LLM appraisal 路径。
  - 其余 agents 直接使用本地基于规则的 appraisal 路径。
  - 如果 LLM appraisal 请求失败且启用了 fallback，该 agent 会继续使用本地 appraisal 路径。

- `latent`
  - Latent 编码完全在本地执行。
  - 系统使用工程化的本地编码器生成 latent 情绪表示。
  - `latent_runtime` 记录为 `mode = "local_only"` 和 `source = "engineered_latent"`。

## 默认运行时配置

示例运行时使用以下默认值：

- `num_agents = 20`
- `rounds = 4`
- `seed_posts = 6`
- `seed = 42`
- `feed_limit = 5`
- `mode = "moe"`
- `llm_provider = "ollama"`
- `enable_fallback = true`

后端调度默认值：

- `llm_semaphore = 64`
- `llm_worker_threads = 64`
- `appraisal_llm_ratio = 0.1`

在当前设置下，10% 的 agents 会被路由到 LLM appraisal 路径，其余 agents 会被路由到本地 appraisal 路径。

## Providers

后端支持以下外部 providers：

- `deepseek`
- `ollama`

Provider 的选择由运行时输入和环境变量控制。Provider 层会在每个 agent 快照中记录运行时元数据，包括 provider 名称、模型、来源、fallback 使用情况和 fallback 原因。

当前 provider 客户端行为：

- DeepSeek 使用 `requests.Session()`，默认 `max_tokens = 800`
- Ollama 使用 `requests.Session()`，默认 `max_tokens = 800`
- 除非被显式禁用，只要存在 API key，DeepSeek 就被视为已启用
- 除非被显式禁用，只要 `base_url` 和 `model_name` 可用，Ollama 就被视为已启用

## 输入结构

生成的后端输入负载包含：

- `meta`
- `runtime`
- `scenario`
- `agents`
- `relationships`
- `seed_posts`

生成的 `runtime` 部分包含：

- `mode`
- `llm_provider`
- `enable_fallback`
- `feed_limit`
- `appraisal_llm_ratio`

## 快照结构

一个仿真快照包含：

- scenario 信息
- platform 状态和 posts
- agent 图和每个 agent 的快照
- 各轮历史
- appraisal 和 latent 处理的运行时元数据

重要的每 agent 运行时字段：

- `appraisal_runtime`
- `latent_runtime`
- `last_cognitive_mode`
- `memory`
- `beliefs / desires / intentions`
- `emotion_state`

当一个 agent 因比例配置被路由到本地 appraisal 路径时，快照会记录：

- `appraisal_runtime.mode = "fallback"`
- `appraisal_runtime.provider = "local"`
- `appraisal_runtime.fallback_reason = "ratio_routed_to_local"`

## 前端返回结构

返回给前端的仿真结果遵循以下展示规则：

- 返回的文本内容为英文
- 返回的面向 agent 的数据聚焦于位于 LLM appraisal 路径上的 agents
- 被直接路由到本地 appraisal 路径的 agents 不会包含在面向 agent 的前端视图中
- 它们的影响仍然保留在返回的 platform 状态和 post 时间线中
- 原始返回数据分为：
  - `Posts JSON`
  - `LLM Agents JSON`

主要调试端点为：

- `GET /`
- `GET /docs`
- `GET /api/debug/options`
- `GET /api/debug/status`
- `POST /api/debug/run-sample`
- `POST /api/debug/run-sample/start`
- `GET /api/debug/run-sample/{job_id}`
- `GET /api/debug/snapshot`

## 主要模块

- `environment/`
  - 环境生命周期、轮次调度、异步编排、导出
- `social_agent/`
  - Agent 状态、appraisal、情绪更新、决策逻辑、记忆、schema 动态
- `social_platform/`
  - Posts、feed 构建、交互、平台追踪
- `services/`
  - Provider 客户端、appraisal 路由、fallback 处理
- `config/`
  - 前端暴露的默认值和后端内部默认值

## 关键文件

- `generate_backend_input.py`
  - 为本地运行构建原生后端输入负载
- `run_backend_input.py`
  - 直接从负载输入运行仿真
- `webapp.py`
  - 暴露 FastAPI 服务和仿真端点
- `services/debug_io.py`
  - 统一管理示例输入/输出路径和调试快照持久化，使运行时数据不依赖内置 viewer 页面
  - 负责默认输入文件生成、默认输出文件写入，以及调试运行 payload 和快照附加元数据的统一构建
- `config/frontend_settings.py`
  - 定义请求默认值、限制和允许值
- `config/backend_settings.py`
  - 定义后端生成和调度器默认值

## 快速开始

```bash
python generate_backend_input.py
python run_backend_input.py -i examples/backend_sample_input.json
uvicorn webapp:app --reload --port 8000
```

当默认示例输入缺失时，`run_backend_input.py` 会自动创建 `examples/backend_sample_input.json`，并且即使从未使用内置调试 viewer 页面，也会将最新的默认快照写入 `outputs/backend_sample_output.json`。

打开：

- API 文档：`http://localhost:8000/docs`
- 本地 viewer：`http://localhost:8000/debug/viewer`

## 环境变量

常用环境变量：

```bash
COGNITIVE_MODE=moe
LLM_PROVIDER_NAME=ollama
LLM_ENABLE_FALLBACK=1
LLM_PROVIDER_USE_CACHE=1
BACKEND_CHECKPOINT_DIR=./checkpoints

DEEPSEEK_API_KEY=xxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_MAX_TOKENS=800

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
OLLAMA_MAX_TOKENS=800
```

## 集成说明

- `mode = "moe"` 表示运行时可能会为被路由到 LLM 的 appraisal agents 使用外部 provider
- `mode = "fallback"` 表示所有 agents 的 appraisal 都保持为本地执行
- `enable_fallback = true` 允许被路由到 LLM 的 appraisal agents 在 provider 失败时继续使用本地逻辑
- `/api/debug/snapshot` 返回最近一次存储的快照
- `outputs/` 包含导出的仿真快照

## 架构参考

面向开发的约定和模块职责记录在 [agent.md](./agent.md) 中。
