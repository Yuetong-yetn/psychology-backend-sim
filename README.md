# Psychology Backend

Psychology Backend 是一个由 JSON 负载和命令行脚本驱动的本地社会心理仿真后端。项目入口脚本为 `examples/start.py`，输入生成脚本为 `examples/generate_backend_input.py`。

## 功能概览

- 使用 `scenario`、`agents`、`relationships` 和 `seed_posts` 构建仿真输入。
- 通过环境调度器运行多 agent 多轮交互。
- 让 agent 浏览平台 feed、执行 appraisal、更新心理状态并提交平台动作。
- 导出包含场景、平台、agent、关系图、轮次历史和运行元数据的 JSON 快照。
- 将输入负载和最终快照写入 SQLite 数据库，便于前端展示和分析脚本读取。

## 快速运行

```bash
python examples/generate_backend_input.py
python examples/start.py -i examples/backend_sample_input.json
```

`examples/start.py` 会读取输入 JSON，执行仿真，并写出以下产物：

- `outputs/backend_sample_output.json`
- `outputs/simulation_snapshot.json`
- `psychology_backend_frontend.db`

自定义输出路径：

```bash
python examples/start.py -i examples/backend_sample_input.json -o outputs/custom_snapshot.json --db outputs/custom_run.db
```

## 输入负载

后端输入 JSON 包含以下顶层字段：

- `meta`：输入文件说明、仿真规模、随机种子和数据来源。
- `runtime`：运行模式、LLM provider、fallback、feed 上限和 appraisal 路由比例。
- `scenario`：仿真场景。
- `agents`：agent 档案和初始状态。
- `relationships`：agent 之间的 follow 关系。
- `seed_posts`：初始平台帖子。

`runtime` 常用字段：

- `mode`
- `llm_provider`
- `enable_fallback`
- `feed_limit`
- `appraisal_llm_ratio`

## 输出快照

一次仿真快照包含：

- `scenario` 和 `scenario_prompt`
- `platform` 状态、帖子、互动和 trace
- `agent_graph` 关系图
- `agents` 当前状态快照
- `history` 各轮结果
- `_debug` 运行配置和 agent 运行摘要
- `export_path` 快照导出路径

`agents[].state` 面向默认展示，包含核心心理状态和轻量 appraisal 摘要。`agents[].state._debug` 面向调试和研究，包含 appraisal、latent、action timing、信念向量和内部计算量。

## 数据库

`psychology_backend_frontend.db` 由 `social_platform/database.py` 写入，schema 位于 `social_platform/schema/`。数据库包含输入表、平台表、agent 表、历史表和调试表。

常用表：

- `input_meta`
- `input_runtime`
- `input_agents`
- `input_relationships`
- `input_seed_posts`
- `snapshot_info`
- `snapshot_debug`
- `platform_posts`
- `agent_snapshots`
- `round_results`

`agent_snapshots.state_debug_json` 存储 agent 调试字段，`round_results.state_delta_json` 存储每轮回放所需的轻量状态。

## 关键文件

- `examples/generate_backend_input.py`：生成后端输入负载。
- `examples/start.py`：从输入负载运行仿真，写出 JSON 快照和 SQLite 数据库。
- `data/oasis_reddit/oasis_adapter.py`：将 OASIS Reddit 数据转换成后端输入负载。
- `services/debug_io.py`：管理默认输入输出路径、样例 payload 和快照调试元数据。
- `config/frontend_settings.py`：定义样例生成和调试负载使用的默认值。
- `config/backend_settings.py`：定义后端运行、IO 和调度默认值。
- `environment/env.py`：管理仿真生命周期、轮次调度、并发执行和导出。
- `social_agent/agent.py`：定义 agent 档案、状态、appraisal、决策和快照。
- `social_platform/database.py`：写入 SQLite 数据库。

## 环境变量

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

## 参考文档

- [agent.md](./agent.md)
- [backend-frontend-interface.md](./backend-frontend-interface.md)
- [data/oasis_reddit/oasis_data_conversion.md](./data/oasis_reddit/oasis_data_conversion.md)
