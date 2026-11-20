# API 使用示例

以下命令默认后端运行在 `http://127.0.0.1:8000`。

## 启动一次运行

```powershell
$body = @{
  input = @{
    map = "零号大坝"
    squadSize = 3
    tactic = "稳健搜打"
    operators = @("红狼", "蜂医", "露娜")
    weight = 31.5
  }
  maxRounds = 4
  workflowKey = "extraction-default"
} | ConvertTo-Json -Depth 5

$run = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/runs" `
  -ContentType "application/json" `
  -Body $body

$run.id
```

## 查询运行与快照

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/runs/$($run.id)"
Invoke-RestMethod "http://127.0.0.1:8000/api/runs/$($run.id)/event-log"
Invoke-RestMethod "http://127.0.0.1:8000/api/runs/$($run.id)/snapshots"
```

## 对比前两轮

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/api/runs/$($run.id)/diff?fromRound=1&toRound=2"
```

## 从失败快照恢复

```powershell
$snapshots = Invoke-RestMethod `
  "http://127.0.0.1:8000/api/runs/$($run.id)/snapshots"
$snapshotId = $snapshots.items[0].id

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/runs/$($run.id)/snapshots/$snapshotId/restore"
```

恢复操作会创建新的运行分支，原运行不会被覆盖。

## 注册 Agent 新版本

```powershell
$agentVersion = @{
  prompt = "你是风险评估 Agent。必须读取地图风险节点、物资草稿和干员接力方案，输出严格 JSON。"
  capabilities = @("risk_analysis", "route_validation", "conflict_detection")
  tools = @("route_risk_probe")
  priority = 95
  enabled = $true
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/agents/risk/versions" `
  -ContentType "application/json" `
  -Body $agentVersion
```

新版本满足能力要求且优先级更高时，后续运行由调度器自动选择。

## 注册工作流新版本

```powershell
$workflowVersion = @{
  enabled = $true
  definition = @{
    maxRounds = 4
    stages = @(
      @{ id = "map-intel"; type = "agent"; role = "map" }
      @{ id = "parallel-drafts"; type = "parallel"; roles = @("risk", "supply", "operator"); phase = "draft" }
      @{ id = "peer-refine"; type = "parallel"; roles = @("risk", "supply", "operator"); phase = "refine" }
      @{ id = "audit"; type = "agent"; role = "audit" }
      @{ id = "decision-gate"; type = "condition"; field = "audit.pass"; onFalse = "next-round" }
    )
    scheduler = @{
      policy = "capability-load-priority"
      maxParallel = 3
    }
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/workflows/extraction-default/versions" `
  -ContentType "application/json" `
  -Body $workflowVersion
```

## 调用确定性工具

```powershell
$toolBody = @{
  arguments = @{
    weight = 31.5
    capacity = 38
  }
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/tools/loadout_validate/invoke" `
  -ContentType "application/json" `
  -Body $toolBody
```

## 运行标准评测

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/evaluations/run"
Invoke-RestMethod "http://127.0.0.1:8000/api/evaluations/latest"
```
