# Psychology Backend

Psychology Backend 是一个面向“社会议题传播-情绪演化-平台交互行为”场景的仿真后端，用于生成可分析、可导出的多智能体社会心理仿真快照。

它当前围绕一条完整的异步仿真链路展开：
- `scenario`：定义议题标题、描述与环境上下文
- `agents`：定义考察对象的静态画像与初始心理状态
- `platform`：模拟信息流、发帖、回复、点赞、转发与影响传播
- `environment`：负责多轮调度、并发执行、平台提交与结果导出

系统当前采用“认知模式 + 外部 provider + 本地 fallback”的三层运行结构，并输出 `snapshot` JSON 供调试页、脚本或后续分析直接消费。当前版本重点落在以下工程能力上：
- 异步环境调度（`asyncio`）与多 agent 并发轮次执行
- 社会平台交互闭环（post / reply / like / share / influence）
- 情绪、appraisal、latent 表示与 contagion 的联动更新
- 调试接口与浏览页联动（示例输入、运行样例、读取最新快照）

## 项目结构与能力概览

当前项目提供一条“可生成输入、可运行、可导出、可可视化检查”的后端实验链路：

1. 项目骨架与基础运行链路
- 建立 `environment`、`social_agent`、`social_platform`、`services`、`scripts`、`examples`、`outputs` 等目录。
- 提供 `run_backend_input.py` 作为后端原生输入的主运行入口。
- 提供 `examples/start.py` 作为最小异步运行示例。

2. 后端原生输入格式打通
- 新增 `generate_backend_input.py`，支持按参数生成示例 payload。
- 输入结构覆盖 `meta`、`runtime`、`scenario`、`agents`、`relationships`、`seed_posts`。
- `run_backend_input.py` 可直接读取该 payload 并完成一次完整仿真。

3. 环境与平台执行链路闭环
- `SimulationEnv` 负责 `areset -> astep/arun -> export -> snapshot -> aclose` 生命周期。
- `Platform` 负责注册 agent、平台动作分发、信息流排序与行为日志记录。
- `SimulationStorage` 负责把快照导出到 `outputs/` 下的 JSON 文件。

4. agent 心理与行为模型
- `social_agent/agent.py` 实现了 profile、state、memory、appraisal、emotion state、decision、round result 等核心结构。
- 单轮过程包含 observation、appraisal、emotion contagion、schema 更新与行为决策。
- 输出中保留了较完整的心理状态、记忆、runtime metadata 与行为结果，便于分析。

5. 认知模式与 provider 接口接入
- `services/llm_provider.py` 提供统一 Cognitive MoE dispatcher。
- 上层通过 `mode` 决定认知运行方式，下层通过 `provider` 选择外部模型后端。
- 当前支持 `ollama` 与 `deepseek` 两类 provider，并带有本地 fallback。
- 增加缓存、provider metadata、异常降级与无外部服务可用时的本地回退路径。

6. 调试 API 与页面
- `webapp.py` 提供 `FastAPI` 调试服务。
- 支持 `/api/debug/status`、`/api/debug/run-sample`、`/api/debug/snapshot` 与 `/debug/viewer`。
- 默认会自动生成示例输入，并在没有输出时补跑一轮示例仿真。

## 核心设计要点

- 后端原生输入
  - 支持从 JSON payload 直接构建场景、关系与种子帖子。
- 多 agent 异步并发
  - `SimulationEnv` 内部通过 `asyncio.gather` 并发执行每轮 agent 决策。
- 情绪表征
  - 平台内容与 agent 状态都保留 `emotion_probs`、`pad`、`emotion_latent` 等结构。
- 外部 provider 与 fallback
  - provider 可用时走外部调用，不可用时自动 fallback，保证仿真不中断。
- 调试闭环
  - 既支持命令行运行，也支持浏览器查看最新快照与样例结果。

## 当前核心能力

- 仿真输入
  - 支持 `scenario`、`agents`、`relationships`、`seed_posts` 的完整 payload

- 认知模式
  - `mode=moe`：启用 MoE-first 认知路径，优先尝试外部 provider
  - `mode=fallback`：强制本地回退，不依赖外部 provider

- 外部 provider
  - `ollama`
  - `deepseek`

- fallback
  - provider 不可用或调用失败时，退回本地 engineered / rule-based 路径

- 平台交互
  - 发帖、回复、点赞、转发、浏览 feed、记录影响事件

- 导出
  - 输出当前 round、scenario、platform snapshot、agent graph、agent snapshot、history

## 接口

- `GET /`
- `GET /debug/viewer`
- `GET /api/debug/status`
- `POST /api/debug/run-sample`
- `GET /api/debug/snapshot`

### `POST /api/debug/run-sample`

说明：
- 服务会优先读取 `examples/backend_sample_input.json`
- 如果示例输入不存在，会自动调用 `build_payload(num_agents=8, rounds=4, seed_posts=6, seed=42)` 生成
- 运行完成后，会把结果写入 `outputs/backend_sample_output.json`

### `GET /api/debug/status`

返回信息包括：
- `docs_url`
- `viewer_url`
- `default_input_path`
- `latest_output_path`

## 默认样例规模

当前默认调试样例如下：
- `num_agents = 8`
- `rounds = 4`
- `seed_posts = 6`
- `seed = 42`
- `feed_limit = 5`

这组参数主要用于快速验证输入构造、平台行为与调试页面联动，而不是大规模压测配置。

## 快速启动

```bash
# 生成示例输入
python generate_backend_input.py

# 直接运行一次仿真
python run_backend_input.py -i examples/backend_sample_input.json

# 启动调试服务
uvicorn webapp:app --reload --port 8000
```
访问：
- API 文档：http://localhost:8000/docs
- 调试页：http://localhost:8000/debug/viewer

## 关键环境变量

当前代码会读取以下环境变量：

```bash
COGNITIVE_MODE=moe
LLM_PROVIDER_NAME=ollama
LLM_ENABLE_FALLBACK=1
LLM_PROVIDER_USE_CACHE=1
BACKEND_CHECKPOINT_DIR=./checkpoints

# 按 provider 选择性配置
DEEPSEEK_API_KEY=xxxx
OLLAMA_BASE_URL=http://localhost:11434
```

说明：
- `COGNITIVE_MODE` 控制认知模式，而不是直接指定模型。
- `COGNITIVE_MODE=fallback` 时会跳过外部调用，直接使用本地 fallback。
- `LLM_PROVIDER_NAME` 用于指定外部 provider，当前支持 `ollama` 与 `deepseek`。
- 如果 provider 不可用且 `LLM_ENABLE_FALLBACK=1`，系统会自动退回本地逻辑。
- 若配置 `BACKEND_CHECKPOINT_DIR`，provider cache 会写入其中的 `llm_cache/`。

## 数据与脚本

- `examples/backend_sample_input.json`：示例后端输入
- `outputs/`：导出的仿真快照目录
- `generate_backend_input.py`：按参数生成后端原生输入
- `run_backend_input.py`：从输入 payload 执行完整仿真
- `examples/start.py`：最小异步运行示例
- `scripts/build_training_dataset.py`：构建训练数据
- `scripts/build_llm_teacher_labels.py`：构建 teacher labels
- `scripts/train_appraisal_moe.py`：训练 appraisal MoE
- `scripts/train_emotion_encoder.py`：训练 emotion encoder
- `scripts/eval_learned_modules.py`：评估已学习模块

常用命令：

```bash
python generate_backend_input.py --agents 12 --rounds 6 --seed-posts 8 --seed 42
python run_backend_input.py -i examples/backend_sample_input.json
python examples/start.py
```

## 调试与排查

如果调试页打开但没有最新结果：
- 先访问 `POST /api/debug/run-sample` 触发一次样例运行。
- 再访问 `GET /api/debug/snapshot` 或刷新 `/debug/viewer`。

如果外部 provider 没有真正参与：
- 检查 `LLM_PROVIDER_NAME` 是否设置正确。
- 检查对应 provider 的可用性，例如 `DEEPSEEK_API_KEY` 或本地 `Ollama` 服务。
- 检查是否把 `COGNITIVE_MODE` 设成了 `fallback`。

如果怀疑缓存影响结果：
- 检查 `BACKEND_CHECKPOINT_DIR/llm_cache/` 是否存在缓存文件。
- 关闭 `LLM_PROVIDER_USE_CACHE` 或更换输入 payload 再次运行。

如果对 `MoE` 和 `LLM` 的关系有疑问：
- 当前项目里，`MoE` 指的是上层认知分解与调度方式。
- `LLM provider` 指的是该认知路径可选使用的外部执行后端。
- 二者不是同一个概念，但在 `mode=moe` 下通常会一起出现，因此文档中会同时提到。

## 架构说明

详细开发约束与模块职责见 `agent.md`。


## 调试接口说明

当前调试接口为：
- `GET /api/debug/status`
- `GET /api/debug/options`
- `POST /api/debug/run-sample`
- `GET /api/debug/snapshot`

接口说明：
- `GET /api/debug/options` 用于给前端返回可选超参数、默认值、范围和枚举选项。
- `GET /api/debug/snapshot` 只读取最新快照。
- 如果当前没有快照，`GET /api/debug/snapshot` 会返回 404，并提示先调用 `POST /api/debug/run-sample`。
- `POST /api/debug/run-sample` 支持前端传入调试参数。

## 前端可选超参数

调试 API 和调试页当前提供的参数包括：
- `num_agents`
- `rounds`
- `seed_posts`
- `seed`
- `feed_limit`
- `mode`
- `llm_provider`
- `enable_fallback`

其中：
- `mode` 控制认知路径是 `moe` 还是 `fallback`
- `llm_provider` 控制外部 provider 类型，当前支持 `ollama` 和 `deepseek`
- `enable_fallback` 控制当外部 provider 不可用时是否允许自动回退到本地逻辑

## 后端固定参数配置

`config/` 目录用于区分“前端可选参数”和“后端内部固定参数”：

- `config/frontend_settings.py`
  - 定义前端暴露参数的默认值、范围和可选项
- `config/backend_settings.py`
  - 定义当前后端内部固定参数，例如：
  - agent 生成分布与 topic/persona 池
  - 关系生成概率
  - 环境并发参数
  - agent 动力学常数
  - 输入输出默认文件名

当前代码已经接入这些配置文件，后续如果要调研究参数，优先修改 `config/backend_settings.py`；如果要调前端可选项与范围，优先修改 `config/frontend_settings.py`。
