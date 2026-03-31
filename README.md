<div align="center">

# Aegis Ops Agent

An intelligent operations assistant for Kubernetes clusters, integrated with Feishu Bot.

面向 Kubernetes 集群的智能运维助手，支持与飞书机器人集成。

[简体中文](#chinese-overview) | [English](#english-overview)

</div>

---

# Aegis Ops Agent

## 1. Project Overview

Aegis is an intelligent operations assistant designed to help SRE and operations engineers analyze Kubernetes cluster issues by consuming observability data in a read-only manner.

Aegis 部署在你的 Kubernetes 集群中，通过只读方式接入：

- Prometheus（指标）
- Loki + Promtail（日志）
- Jaeger（分布式调用链）
- Alertmanager（告警 Webhook，可选）
- 飞书机器人（作为 Chat 前端）

核心目标：

- 当 Alertmanager 产生告警时，Agent 自动在飞书告警群内 @ 运维同学，汇总关键告警信息。
- 当运维在群内 @ 机器人并描述故障现象时，Agent 自动调用 Prometheus / Loki / Jaeger 工具完成一次运维分析，并在群内给出按概率排序的根因候选列表及后续排查建议。
- Agent 始终以只读身份工作，**绝不执行任何变更操作**。

## 🚀 核心特性

### 1. 🤖 LangGraph 驱动的有状态 Agent 架构 (最新大一统架构)
Aegis 基于 **LangGraph** 实现了业内领先的 **双模式动态切换** 架构，并且已经完成了前后端大一统的重构，整个项目现在由单纯的 **React (前端)** + **FastAPI/Python (唯一后端)** 构成，抛弃了原来冗余的 Go 后端中间层。

- **原生有状态 & 持久化**：所有的分析计划、工具执行结果、聊天历史甚至模型思考过程，都会被 LangGraph 的 Checkpointer 自动拦截，并由 Python 后端直接结构化地持久化至 SQLite 数据库中。
- **ReAct 与 Plan-and-Execute 动态切换**：对于简单的查询指令，直接走 ReAct 节点快速出结果；对于复杂的故障排查，先走 Plan 节点生成全局执行计划。
- **高危操作的人工确认机制 (Human-in-the-loop)**：当执行删除、重启、修改等高危步骤时，图的执行状态会自动挂起并中断，等待运维人员（通过前端页面或飞书）确认后才继续执行。
- **极简架构 & 高性能**：因为剔除了 Go 中间层，前端的打字机流式输出 (Streaming) 现在直接通过 `FastAPI` 从 LangGraph 获取 NDJSON 数据，彻底告别了流式转发过程中的截断、乱序与 JSON 解析报错等问题。

### 2. 📱 现代化 Web 控制台 & 飞书机器人双端联动
- 提供精美的 React 界面，支持结构化的聊天记录回溯。
- 原生接入飞书机器人，不仅可以异步推送任务状态，运维人员还可以直接在飞书对话框内进行审批授权。

---

## 🛠️ 快速开始

### 项目结构

```text
Aegis/
├── backend/          # 基于 FastAPI 和 LangGraph 的后端核心引擎 (原 services/ops-service)
├── frontend/         # 基于 React 的智能运维平台前端 (原 opspilot-plus/frontend)
├── k8s/              # Kubernetes 部署相关的 yaml 文件
└── docs/             # 架构文档和设计文档
```

backend 内部关键模块：

- `app/interface/api.py`：FastAPI 入口、前端静态资源代理、HTTP 接口、飞书/Alertmanager 集成
- `app/interface/feishu_ws_client.py`：飞书长连接事件网关
- `app/api/routers/`：RESTful API 路由（包括 Auth, Admin, Agent, Tools 等）
- `app/db/`：基于 SQLModel 的 SQLite 数据库模型与会话管理
- `app/agent/executor.py`：LangChain AgentExecutor 与系统 Prompt
- `app/tools/`：Prometheus/Loki/Jaeger 等只读工具
- `app/models/`：Ops 请求 / 响应及根因候选数据结构
- `config/config.py`：配置（通过环境变量/K8s ConfigMap/Secret 注入）

## 4. API Overview

详细说明见 [`docs/api.md`](docs/api.md)，这里给出主要接口一览：

| 服务        | 方法 | 路径                     | 说明                                      |
|-------------|------|--------------------------|-------------------------------------------|
| backend     | GET  | `/healthz`               | 健康检查                                  |
| backend     | POST | `/api/auth/login`        | 用户登录                                  |
| backend     | POST | `/api/agent/chat/stream` | 前端流式运维对话（NDJSON）                |
| backend     | POST | `/api/ops/analyze`       | 内部/测试同步运维分析                     |
| backend     | POST | `/alertmanager/webhook`  | Alertmanager Webhook 回调入口             |

## 5. Deployment Guide (Kubernetes)

1. 创建命名空间与基础配置：

   ```bash
   kubectl apply -f k8s/namespace.yaml
   kubectl apply -f k8s/configmap.yaml
   kubectl apply -f k8s/secret.yaml
   ```

   在应用前，你需要根据实际环境修改：

   - `k8s/configmap.yaml` 中的 `LOKI_BASE_URL`、`PROMETHEUS_BASE_URL`、`JAEGER_BASE_URL`
   - `k8s/configmap.yaml` 中的 `FEISHU_DEFAULT_CHAT_ID`
   - `k8s/secret.yaml` 中的 `DOUBAO_API_KEY`、`FEISHU_APP_ID`、`FEISHU_APP_SECRET` 等密钥

2. 部署 Aegis 后端服务 (包含了预编译的前端静态资源)：

   ```bash
   kubectl apply -f k8s/ops-service.yaml
   ```

3. 根据需要暴露 HTTP 接口：

   - 通常仅需在集群内访问 `/alertmanager/webhook`（由 Alertmanager 调用）；
   - 运维平台前端界面可以通过 Ingress 或 NodePort 暴露。

## 6. Feishu Integration Guide (Overview)

详细步骤见 [`docs/prd.md`](docs/prd.md) 与 [`docs/user-manual.md`](docs/user-manual.md)，这里给出概要流程：

- 在飞书开放平台创建企业自建应用，获取 `app_id` 与 `app_secret`
- 在应用后台开启"长连接事件订阅"能力，并订阅：
  - 机器人收到消息 `im.message.receive_v1`
- 在 K8s Secret 中配置 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`
- backend 在启动时使用 `lark-oapi` 建立与飞书的长连接，自动接收群聊消息并触发运维分析
- 将应用添加到对应飞书群组，获取群组 `chat_id` 并填入 `FEISHU_DEFAULT_CHAT_ID`

## 7. Local Development and Debugging

Aegis 是一个标准的现代全栈应用：

**启动后端：**
```bash
cd backend
pip install -r requirements.txt
export LOKI_BASE_URL="http://localhost:3100"
export PROMETHEUS_BASE_URL="http://localhost:9090"
export JAEGER_BASE_URL="http://localhost:16686"
export DOUBAO_API_KEY="your-llm-api-key"

python main.py
# 服务将运行在 http://localhost:8000
```

**启动前端：**
```bash
cd frontend
npm install
npm run dev
# 前端界面将运行在 http://localhost:5173，并代理 API 请求到 8000 端口
```

更多细节请参考：

- [`docs/api.md`](docs/api.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/prd.md`](docs/prd.md)
- [`docs/user-manual.md`](docs/user-manual.md)

---

## English Overview

### 1. What Is Aegis Ops Agent

Aegis is an intelligent operations assistant designed to help SRE and operations engineers analyze Kubernetes cluster issues by consuming observability data in a read-only manner.

The agent runs inside your cluster and consumes observability data in a read-only way:

- Prometheus for metrics
- Loki + Promtail for logs
- Jaeger for distributed traces
- Alertmanager webhooks (optional)
- Feishu Bot as chat front-end

Typical workflow:

- Alertmanager fires alerts and sends them to Aegis via webhook.
- Aegis posts a summarized alert notification to a Feishu chat and mentions on-call engineers.
- When engineers mention the bot and describe an incident, Aegis runs an ops analysis flow by calling Prometheus/Loki/Jaeger tools and replies with ranked root-cause candidates and next actions.

The agent is strictly **read-only**. It never performs any write or mutation to your cluster.

### 2. Key Features

- **LangGraph Dual-Mode Architecture**: Seamlessly switches between ReAct and Plan-and-Execute modes for complex, multi-step incident resolution.
- **High-Risk Operation Interruption**: Automatically pauses execution and waits for human confirmation in Feishu before executing potentially dangerous actions (e.g., restart, delete).
- **Observability Data Correlation**: Automatically queries and correlates Prometheus (metrics), Loki (logs), and Jaeger (traces).
- **Deep Feishu Integration**:
  - Forwards Alertmanager Webhooks to group chats and mentions on-call engineers.
  - Supports asynchronous interaction and state persistence (via SQLite Checkpointer).
- **Kubernetes-Native Deployment**: Supports exposing HTTP interfaces via NodePort/Ingress.
- **Multi-Model Support**:
  - Local models: Qwen, GLM-4.7-Flash, DeepSeek-R1.
  - Cloud model: Doubao.
  - Users can specify the model directly in Feishu: `@AegisBot qwen/glm/deepseek/doubao question`.

### 3. Deployment

See Chinese sections above and detailed documents:

- [`docs/api.md`](docs/api.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/prd.md`](docs/prd.md)
- [`docs/user-manual.md`](docs/user-manual.md)

The English version focuses on high-level concepts; operational documents are currently in Chinese.
