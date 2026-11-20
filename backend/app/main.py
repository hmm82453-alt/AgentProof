from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from app.agents.audit import AuditAgent
from app.agents.map_intel import MapIntelAgent
from app.agents.operator import OperatorAgent
from app.agents.risk import RiskAgent
from app.agents.supply import SupplyAgent
from app.config import settings
from app.data.maps import GAME_MODES, MAP_LIBRARY, MAP_VERIFICATION
from app.data.operators import OPERATOR_PROFILES, get_catalog_metadata
from app.schemas import (
    AgentRequest,
    AgentVersionCreate,
    CreateRunRequest,
    HealthResponse,
    MissionInput,
    ToolInvokeRequest,
    WorkflowVersionCreate,
)
from app.services.events import event_broker
from app.services.evaluation import evaluation_service
from app.services.llm import LLMError, llm_client
from app.services.orchestrator import run_orchestrator
from app.services.registry import agent_registry, workflow_registry
from app.services.scheduler import dynamic_scheduler
from app.services.storage import run_repository
from app.tools.registry import tool_registry


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Delta Exfil Multi-Agent API",
    version="0.2.0",
    description="Five independently callable tactical planning agents.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

FRONTEND_PATH = Path(__file__).resolve().parents[2] / "delta-agent-console.html"

map_agent = MapIntelAgent()
risk_agent = RiskAgent()
supply_agent = SupplyAgent()
operator_agent = OperatorAgent()
audit_agent = AuditAgent()

TERMINAL_RUN_STATUSES = {"completed", "rejected", "failed", "cancelled"}


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    logger.error("Agent request failed: %s", exc)
    return JSONResponse(
        status_code=502,
        content={
            "error": "agent_llm_failed",
            "message": str(exc),
            "path": request.url.path,
        },
    )


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        provider="llm" if llm_client.configured else "mock",
        model=settings.llm_model if llm_client.configured else None,
        fallback_to_mock=settings.llm_fallback_to_mock,
    )


@app.get("/api/maps")
async def maps() -> dict[str, Any]:
    return {
        "count": len(MAP_LIBRARY),
        "gameModes": list(GAME_MODES.values()),
        "dataVersion": "2026-11-16-public-guides",
        "items": {
            name: {
                "entry": profile["entry"],
                "route": profile["route"],
                "resources": profile["resources"],
                "exfils": MAP_VERIFICATION[name]["knownExfils"],
                "verificationStatus": MAP_VERIFICATION[name]["status"],
                "sources": MAP_VERIFICATION[name]["sources"],
                "reportedTotalExits": MAP_VERIFICATION[name]["reportedTotalExits"],
            }
            for name, profile in MAP_LIBRARY.items()
        },
    }


@app.get("/api/operators")
async def operators() -> dict[str, Any]:
    return {
        "count": len(OPERATOR_PROFILES),
        "catalog": get_catalog_metadata(),
        "items": OPERATOR_PROFILES,
    }


@app.get("/api/agents")
async def list_agents() -> dict[str, Any]:
    agents = agent_registry.list_agents()
    return {"count": len(agents), "items": agents}


@app.get("/api/agents/{agent_key}")
async def get_agent(agent_key: str) -> dict[str, Any]:
    try:
        return agent_registry.get_agent(agent_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent not found") from exc


@app.post("/api/agents/{agent_key}/versions", status_code=201)
async def register_agent_version(
    agent_key: str,
    payload: AgentVersionCreate,
) -> dict[str, Any]:
    try:
        return agent_registry.register_version(agent_key, **payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent not found") from exc


@app.get("/api/workflows")
async def list_workflows() -> dict[str, Any]:
    workflows = workflow_registry.list_workflows()
    return {"count": len(workflows), "items": workflows}


@app.get("/api/workflows/{workflow_key}")
async def get_workflow(workflow_key: str) -> dict[str, Any]:
    try:
        return workflow_registry.get_workflow(workflow_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc


@app.post("/api/workflows/{workflow_key}/versions", status_code=201)
async def register_workflow_version(
    workflow_key: str,
    payload: WorkflowVersionCreate,
) -> dict[str, Any]:
    try:
        return workflow_registry.register_version(
            workflow_key,
            payload.definition,
            enabled=payload.enabled,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc


@app.get("/api/tools")
async def list_tools() -> dict[str, Any]:
    tools = tool_registry.list_tools()
    return {"count": len(tools), "items": tools}


@app.post("/api/tools/{tool_name}/invoke")
async def invoke_tool(
    tool_name: str,
    payload: ToolInvokeRequest,
) -> dict[str, Any]:
    try:
        return await tool_registry.invoke(tool_name, payload.arguments)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="tool not found") from exc


@app.post("/api/evaluations/run")
async def run_evaluation() -> dict[str, Any]:
    return await evaluation_service.run()


@app.get("/api/evaluations/latest")
async def latest_evaluation() -> dict[str, Any]:
    try:
        return evaluation_service.latest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="evaluation report not found") from exc


@app.post("/api/runs", status_code=202)
async def create_run(payload: CreateRunRequest) -> dict[str, Any]:
    try:
        workflow = workflow_registry.get_workflow(payload.workflowKey)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc
    definition = workflow["active"]["definition"]
    max_rounds = min(payload.maxRounds, int(definition.get("maxRounds", 4)))
    roles = ["map", "risk", "supply", "operator", "audit"]
    schedule = dynamic_scheduler.schedule(
        roles,
        tactic=payload.input.tactic,
        workflow_definition=definition,
    )
    run = run_repository.create_run(
        payload.input.model_dump(),
        max_rounds,
        workflow_key=workflow["key"],
        workflow_version=workflow["active"]["version"],
        agent_manifest=schedule["selected"],
    )
    run_orchestrator.start(
        run["id"],
        payload.input,
        max_rounds,
        workflow=definition,
        schedule=schedule,
    )
    return run


@app.get("/api/runs")
async def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    runs = run_repository.list_runs(limit)
    return {"count": len(runs), "items": runs}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    try:
        return run_repository.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@app.get("/api/runs/{run_id}/event-log")
async def get_run_event_log(
    run_id: str,
    after: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    try:
        run_repository.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    events = run_repository.get_events(run_id, after_id=after)
    return {"count": len(events), "items": events}


@app.get("/api/runs/{run_id}/snapshots")
async def get_run_snapshots(run_id: str) -> dict[str, Any]:
    try:
        run_repository.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    snapshots = run_repository.list_snapshots(run_id)
    return {"count": len(snapshots), "items": snapshots}


@app.get("/api/runs/{run_id}/snapshots/{snapshot_id}")
async def get_snapshot(run_id: str, snapshot_id: str) -> dict[str, Any]:
    try:
        return run_repository.get_snapshot(run_id, snapshot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="snapshot not found") from exc


@app.post("/api/runs/{run_id}/snapshots/{snapshot_id}/restore", status_code=202)
async def restore_snapshot(run_id: str, snapshot_id: str) -> dict[str, Any]:
    try:
        source = run_repository.get_run(run_id)
        snapshot = run_repository.get_snapshot(run_id, snapshot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run or snapshot not found") from exc

    if snapshot["round"] >= source["maxRounds"]:
        raise HTTPException(
            status_code=409,
            detail="cannot resume after the final round",
        )

    workflow_key = source["workflow"]["key"]
    try:
        workflow = workflow_registry.get_workflow(workflow_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc
    definition = workflow["active"]["definition"]
    mission = MissionInput.model_validate(source["input"])
    schedule = dynamic_scheduler.schedule(
        ["map", "risk", "supply", "operator", "audit"],
        tactic=mission.tactic,
        workflow_definition=definition,
    )
    restored = run_repository.create_run(
        source["input"],
        source["maxRounds"],
        workflow_key=workflow_key,
        workflow_version=workflow["active"]["version"],
        agent_manifest=schedule["selected"],
    )
    run_orchestrator.start(
        restored["id"],
        mission,
        source["maxRounds"],
        workflow=definition,
        schedule=schedule,
        resume_context=snapshot["state"],
        start_round=snapshot["round"] + 1,
    )
    return {
        **restored,
        "restoredFrom": {
            "runId": run_id,
            "snapshotId": snapshot_id,
            "round": snapshot["round"],
        },
    }


@app.get("/api/runs/{run_id}/diff")
async def diff_run_rounds(
    run_id: str,
    fromRound: int = Query(ge=1),
    toRound: int = Query(ge=1),
) -> dict[str, Any]:
    try:
        run_repository.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    snapshots = {
        item["round"]: item["state"]
        for item in run_repository.list_snapshots(run_id)
    }
    if fromRound not in snapshots or toRound not in snapshots:
        raise HTTPException(status_code=404, detail="snapshot round not found")

    before = snapshots[fromRound]
    after = snapshots[toRound]
    changes = [
        {
            "field": "route",
            "before": before["map"]["routeA"],
            "after": after["map"]["route"],
        },
        {
            "field": "riskScore",
            "before": before["risk"]["score"],
            "after": after["risk"]["score"],
        },
        {
            "field": "smokeCount",
            "before": before["supply"]["smokeCount"],
            "after": after["supply"]["smokeCount"],
        },
        {
            "field": "relayGapSeconds",
            "before": before["operator"]["gapSeconds"],
            "after": after["operator"]["gapSeconds"],
        },
        {
            "field": "auditPass",
            "before": before["audit"]["pass"],
            "after": after["audit"]["pass"],
        },
    ]
    return {
        "runId": run_id,
        "fromRound": fromRound,
        "toRound": toRound,
        "changes": changes,
    }


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict[str, Any]:
    try:
        run = run_repository.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    if run["status"] in TERMINAL_RUN_STATUSES:
        return {"cancelled": False, "run": run}
    cancelled = run_orchestrator.cancel(run_id)
    return {"cancelled": cancelled, "run": run_repository.get_run(run_id)}


@app.post("/api/runs/{run_id}/retry", status_code=202)
async def retry_run(run_id: str) -> dict[str, Any]:
    try:
        source = run_repository.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    mission = MissionInput.model_validate(source["input"])
    workflow_key = source["workflow"]["key"]
    try:
        workflow = workflow_registry.get_workflow(workflow_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc
    definition = workflow["active"]["definition"]
    schedule = dynamic_scheduler.schedule(
        ["map", "risk", "supply", "operator", "audit"],
        tactic=mission.tactic,
        workflow_definition=definition,
    )
    run = run_repository.create_run(
        source["input"],
        source["maxRounds"],
        workflow_key=workflow_key,
        workflow_version=workflow["active"]["version"],
        agent_manifest=schedule["selected"],
    )
    run_orchestrator.start(
        run["id"],
        mission,
        source["maxRounds"],
        workflow=definition,
        schedule=schedule,
    )
    return run


@app.get("/api/runs/{run_id}/events")
async def stream_run_events(
    request: Request,
    run_id: str,
    after: int = Query(default=0, ge=0),
) -> StreamingResponse:
    try:
        run_repository.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc

    async def event_stream() -> AsyncIterator[str]:
        queue = event_broker.subscribe(run_id)
        seen: set[int] = set()
        try:
            for event in run_repository.get_events(run_id, after_id=after):
                if event["id"] in seen:
                    continue
                seen.add(event["id"])
                yield _format_sse(event)

            current = run_repository.get_run(run_id)
            if current["status"] in TERMINAL_RUN_STATUSES:
                return

            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if event["id"] in seen:
                    continue
                seen.add(event["id"])
                yield _format_sse(event)
                if event["type"] in {"run.completed", "run.failed", "run.cancelled"}:
                    return
        finally:
            event_broker.unsubscribe(run_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _format_sse(event: dict[str, Any]) -> str:
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return (
        f"id: {event['id']}\n"
        f"event: {event['type']}\n"
        f"data: {data}\n\n"
    )


@app.post("/api/agents/map-intel")
async def run_map_agent(payload: AgentRequest) -> dict[str, Any]:
    return await map_agent.run(payload)


@app.post("/api/agents/risk")
async def run_risk_agent(payload: AgentRequest) -> dict[str, Any]:
    return await risk_agent.run(payload)


@app.post("/api/agents/supply")
async def run_supply_agent(payload: AgentRequest) -> dict[str, Any]:
    return await supply_agent.run(payload)


@app.post("/api/agents/operator")
async def run_operator_agent(payload: AgentRequest) -> dict[str, Any]:
    return await operator_agent.run(payload)


@app.post("/api/agents/audit")
async def run_audit_agent(payload: AgentRequest) -> dict[str, Any]:
    return await audit_agent.run(payload)


@app.get("/", include_in_schema=False)
async def frontend() -> FileResponse:
    if not FRONTEND_PATH.exists():
        return JSONResponse(
            status_code=404,
            content={
                "error": "frontend_not_found",
                "expected_path": str(FRONTEND_PATH),
            },
        )
    return FileResponse(FRONTEND_PATH, media_type="text/html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)
