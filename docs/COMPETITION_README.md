# AgentProof / 撤离线

三角洲行动撤离任务的多 Agent 协同规划原型。系统通过地图情报、风险评估、
物资规划、干员协同和校验复盘五类 Agent，生成可追溯、可迭代、可恢复的撤离方案。

## 快速启动

Windows 本地运行：

```powershell
cd backend
.\start.ps1
```

浏览器访问 <http://127.0.0.1:8000>。直接打开根目录
`delta-agent-console.html` 时使用离线模拟，不依赖后端。

Docker：

```powershell
docker compose up --build
```

## 当前能力

| 赛题要求 | 当前实现 |
| --- | --- |
| Agent 角色与版本 | SQLite Agent Registry，支持版本注册与启用 |
| 工作流编排 | 注册式工作流版本，包含地图、并行草稿、交叉修正、仲裁和条件门 |
| 动态调度 | 按能力、版本优先级和任务打法选择 Agent |
| 工具集成 | Tool Registry + stdio MCP Server |
| 实时执行 | FastAPI 服务端编排，SSE 推送状态、日志和消息 |
| 结果验证 | 客观负重、撤离条件工具与仲裁 Agent 双重校验 |
| 自我循环 | 第一轮失败，依据仲裁反馈进入下一轮，最多四轮 |
| 可追溯 | 运行事件、Agent 消息、工具调用和轮次结果全部持久化 |
| 快照恢复 | 每轮保存状态，可从失败轮次快照恢复成新运行 |
| 历史回放 | 平台中心查看运行记录并逐事件回放 |
| 工程评测 | 8 个标准场景，自动生成成功率、轮次和耗时报告 |
| 部署 | 本地 PowerShell 与 Docker Compose |

## 目录

```text
delta-agent-console.html       单文件操作界面
backend/app/main.py            FastAPI 路由
backend/app/agents/            五类独立 Agent
backend/app/services/          编排、调度、注册、存储、评测
backend/app/tools/             确定性工具注册表
backend/mcp_server.py          MCP stdio 服务
backend/tests/                 API 与集成测试
docs/                          架构、演示与答辩材料
docker-compose.yml             容器部署
```

## 核心接口

```text
POST /api/runs
GET  /api/runs/{id}/events
GET  /api/runs/{id}/event-log
GET  /api/runs/{id}/snapshots
POST /api/runs/{id}/snapshots/{snapshotId}/restore
GET  /api/runs/{id}/diff
GET  /api/agents
POST /api/agents/{key}/versions
GET  /api/workflows
POST /api/workflows/{key}/versions
GET  /api/tools
POST /api/tools/{name}/invoke
POST /api/evaluations/run
```

Swagger 文档位于 `/docs`。

## 真实模型

```powershell
cd backend
Copy-Item .env.example .env
```

填写 `LLM_API_KEY`。项目默认使用 DeepSeek 的 OpenAI 兼容接口：

```env
LLM_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

后端先运行确定性规则，再把地图事实和结构化草稿作为上下文交给模型改写。
模型异常时可回退到规则结果。

## 验证

```powershell
cd backend
.\run-tests.ps1
.\.venv\Scripts\python.exe scripts\evaluate.py
```

详细材料：

- [系统架构](ARCHITECTURE.md)
- [演示脚本](DEMO_SCRIPT.md)
- [评委问答](JUDGE_QA.md)
