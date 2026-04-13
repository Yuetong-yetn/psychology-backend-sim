# Backend Demo

这份 `demo/backend-demo` 是一个轻量启动包装层，用来直接复用当前仓库根目录中的真实后端应用。

它的作用是：

- 提供一个可以单独进入 `demo/backend-demo` 后启动的演示入口
- 复用仓库根目录里的真实 FastAPI `app`
- 复用当前后端的输入生成、运行调度、快照导出和调试接口逻辑

这意味着 demo 本身不维护另一套独立的后端实现，接口行为、返回结构和运行时逻辑都来自仓库根目录中的当前代码。

## 当前结构

```text
demo/backend-demo
├── app
│   ├── __init__.py
│   └── main.py
└── pyproject.toml
```

其中 `demo/backend-demo/app/main.py` 的工作只有一件事：向上定位到仓库根目录，然后导入根目录中的 `webapp.py`，并暴露同一个 FastAPI `app`。

核心入口为：

```python
app = _load_app()
```

## 启动方式

在仓库根目录下执行：

```bash
cd demo/backend-demo
uvicorn app.main:app --reload --port 8000
```

启动后可访问：

- API 文档：`http://localhost:8000/docs`
- 本地页面：`http://localhost:8000/debug/viewer`

## 运行逻辑来源

demo 实际复用的是仓库根目录中的这些文件：

- `webapp.py`
  - 提供 FastAPI 服务和调试接口
- `run_backend_input.py`
  - 从 payload 运行仿真
- `generate_backend_input.py`
  - 生成后端输入 payload
- `services/debug_io.py`
  - 管理默认输入、默认输出和调试快照持久化
- `config/frontend_settings.py`
  - 定义前端可见默认值和请求限制
- `config/backend_settings.py`
  - 定义后端调度和运行时默认参数

## 当前运行时逻辑

当前实现包含以下规则：

- 默认运行参数由 `config/frontend_settings.py` 提供
- `appraisal` 采用按比例路由
- `latent` 完全使用本地 engineered encoder
- 仅有一部分 agents 会进入 LLM appraisal 路径
- 被分配到 LLM 路径的 agent 在外部请求失败时会回退到本地规则路径
- 返回给前端的 agent-focused 数据聚焦于 MoE 路径上的 agents
- platform 状态和 posts 保留所有 agents 的整体影响

当前默认参数包括：

- `num_agents = 20`
- `rounds = 4`
- `seed_posts = 6`
- `feed_limit = 5`
- `mode = "moe"`
- `enable_fallback = true`
- `appraisal_llm_ratio = 0.1`

## 输入与输出

运行时默认会使用仓库根目录中的标准输入输出位置：

- 默认输入：`examples/backend_sample_input.json`
- 默认输出：`outputs/backend_sample_output.json`

`services/debug_io.py` 会负责：

- 在默认输入不存在时自动生成输入文件
- 持久化最新的仿真快照
- 为调试接口构建运行 payload

## 说明

- 如果你看到任何接口返回、字段结构或运行行为，它们都来自仓库根目录中的当前后端代码，而不是 demo 目录内部的另一套实现
- 如果需要核对真实接口契约，请以 `webapp.py`、`run_backend_input.py` 和 `services/debug_io.py` 为准
- 如果需要核对前后端字段约定，请以仓库根目录中的相关文档和当前快照结构为准
