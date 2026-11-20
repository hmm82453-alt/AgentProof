from __future__ import annotations

from copy import deepcopy
import asyncio
from typing import Any
import time

from fastapi.testclient import TestClient

from app.main import app
from mcp_server import StdioMcpServer


client = TestClient(app)


def mission_payload(*, weight: float = 31.5, map_name: str = "零号大坝") -> dict[str, Any]:
    return {
        "input": {
            "map": map_name,
            "squadSize": 3,
            "tactic": "稳健搜打",
            "operators": ["红狼", "蜂医", "露娜"],
            "weight": weight,
        },
        "round": 1,
        "context": {},
    }


def run_round(
    round_number: int,
    *,
    weight: float = 31.5,
    map_name: str = "零号大坝",
    previous_audit: dict[str, Any] | None = None,
    map_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base = mission_payload(weight=weight, map_name=map_name)
    base["round"] = round_number

    if map_context is None:
        map_response = client.post("/api/agents/map-intel", json=base)
        assert map_response.status_code == 200
        map_context = map_response.json()

    context = {"map": map_context}
    draft_requests = []
    for endpoint in ("risk", "supply", "operator"):
        payload = deepcopy(base)
        payload["context"] = context
        payload["phase"] = "draft"
        draft_requests.append(client.post(f"/api/agents/{endpoint}", json=payload))
    assert all(response.status_code == 200 for response in draft_requests)
    risk_draft, supply_draft, operator_draft = [
        response.json() for response in draft_requests
    ]

    peers = {
        "riskDraft": risk_draft,
        "supplyDraft": supply_draft,
        "operatorDraft": operator_draft,
        "previousAudit": previous_audit,
    }
    refine_responses = []
    for endpoint in ("risk", "supply", "operator"):
        payload = deepcopy(base)
        payload["context"] = context
        payload["phase"] = "refine"
        payload["peers"] = peers
        refine_responses.append(client.post(f"/api/agents/{endpoint}", json=payload))
    assert all(response.status_code == 200 for response in refine_responses)
    risk, supply, operator = [response.json() for response in refine_responses]

    audit_payload = deepcopy(base)
    audit_payload["context"] = {
        **context,
        "risk": risk,
        "supply": supply,
        "operator": operator,
        "previousAudit": previous_audit,
    }
    audit_response = client.post("/api/agents/audit", json=audit_payload)
    assert audit_response.status_code == 200
    return audit_response.json(), map_context


def test_health_and_frontend_are_available() -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["provider"] == "mock"

    frontend = client.get("/")
    assert frontend.status_code == 200
    assert "撤离线" in frontend.text


def test_all_maps_have_resources_exfils_and_fallbacks() -> None:
    response = client.get("/api/maps")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    for profile in data["items"].values():
        assert len(profile["resources"]) >= 4
        assert len(profile["exfils"]) >= 2
        assert profile["route"]
        assert profile["verificationStatus"] in {"partial", "needs_review"}


def test_complete_operator_catalog_and_three_person_limit() -> None:
    operators = client.get("/api/operators")
    assert operators.status_code == 200
    data = operators.json()
    assert data["count"] == 16
    assert data["catalog"]["classes"] == {"突击": 6, "支援": 3, "工程": 4, "侦察": 3}

    payload = mission_payload()
    payload["input"]["squadSize"] = 4
    payload["input"]["operators"] = ["红狼", "蜂医", "露娜", "野火"]
    response = client.post("/api/agents/map-intel", json=payload)
    assert response.status_code == 422

    duplicate = mission_payload()
    duplicate["input"]["operators"] = ["红狼", "红狼", "蜂医"]
    assert client.post("/api/agents/map-intel", json=duplicate).status_code == 422

    unknown = mission_payload()
    unknown["input"]["operators"] = ["红狼", "蜂医", "不存在干员"]
    assert client.post("/api/agents/map-intel", json=unknown).status_code == 422


def test_default_round_fails_then_round_two_passes() -> None:
    first_audit, map_context = run_round(1)
    assert first_audit["pass"] is False
    assert "18秒" in first_audit["issue"]

    second_audit, _ = run_round(
        2,
        previous_audit=first_audit,
        map_context=map_context,
    )
    assert second_audit["pass"] is True
    assert second_audit["finalPlan"]["route"]
    assert len(second_audit["auditChecks"]) == 6


def test_high_weight_reaches_four_round_limit() -> None:
    previous = None
    map_context = None
    for round_number in range(1, 5):
        audit, map_context = run_round(
            round_number,
            weight=60,
            map_name="长弓溪谷",
            previous_audit=previous,
            map_context=map_context,
        )
        assert audit["pass"] is False
        previous = audit
    assert "负重" in previous["issue"]


def test_invalid_input_is_rejected() -> None:
    payload = mission_payload()
    payload["input"]["squadSize"] = 8
    response = client.post("/api/agents/map-intel", json=payload)
    assert response.status_code == 422


def test_persistent_run_events_and_snapshot() -> None:
    with TestClient(app) as local_client:
        response = local_client.post(
            "/api/runs",
            json={"input": mission_payload()["input"], "maxRounds": 4},
        )
        assert response.status_code == 202
        run_id = response.json()["id"]

        deadline = time.monotonic() + 10
        run = None
        while time.monotonic() < deadline:
            run = local_client.get(f"/api/runs/{run_id}").json()
            if run["status"] in {"completed", "rejected", "failed", "cancelled"}:
                break
            time.sleep(0.05)

        assert run is not None
        assert run["status"] == "completed"
        assert run["currentRound"] == 2

        event_log = local_client.get(f"/api/runs/{run_id}/event-log").json()
        event_types = [item["type"] for item in event_log["items"]]
        assert "round.result" in event_types
        assert "agent.state" in event_types
        assert "run.completed" in event_types

        snapshots = local_client.get(f"/api/runs/{run_id}/snapshots").json()
        assert snapshots["count"] == 2
        assert snapshots["items"][-1]["round"] == 2

        sse = local_client.get(f"/api/runs/{run_id}/events")
        assert sse.status_code == 200
        assert "event: run.completed" in sse.text


def test_registry_tools_restore_and_diff() -> None:
    with TestClient(app) as local_client:
        agents = local_client.get("/api/agents")
        workflows = local_client.get("/api/workflows")
        tools = local_client.get("/api/tools")
        assert agents.status_code == 200
        assert len(agents.json()["items"]) == 5
        assert workflows.json()["items"][0]["key"] == "extraction-default"
        assert tools.json()["count"] >= 5

        tool_result = local_client.post(
            "/api/tools/loadout_validate/invoke",
            json={"arguments": {"weight": 31.5, "capacity": 38}},
        )
        assert tool_result.status_code == 200
        assert tool_result.json()["result"]["valid"] is True

        response = local_client.post(
            "/api/runs",
            json={"input": mission_payload()["input"], "maxRounds": 4},
        )
        run_id = response.json()["id"]
        deadline = time.monotonic() + 10
        run = None
        while time.monotonic() < deadline:
            run = local_client.get(f"/api/runs/{run_id}").json()
            if run["status"] in {"completed", "rejected", "failed", "cancelled"}:
                break
            time.sleep(0.05)
        assert run["status"] == "completed"

        snapshots = local_client.get(f"/api/runs/{run_id}/snapshots").json()["items"]
        diff = local_client.get(
            f"/api/runs/{run_id}/diff?fromRound=1&toRound=2"
        )
        assert diff.status_code == 200
        assert diff.json()["changes"][-1]["after"] is True

        restored = local_client.post(
            f"/api/runs/{run_id}/snapshots/{snapshots[0]['id']}/restore"
        )
        assert restored.status_code == 202
        restored_run_id = restored.json()["id"]
        deadline = time.monotonic() + 10
        restored_run = None
        while time.monotonic() < deadline:
            restored_run = local_client.get(f"/api/runs/{restored_run_id}").json()
            if restored_run["status"] in {
                "completed",
                "rejected",
                "failed",
                "cancelled",
            }:
                break
            time.sleep(0.05)
        assert restored_run["status"] == "completed"


def test_agent_version_registration_and_mcp_tools() -> None:
    response = client.post(
        "/api/agents/risk/versions",
        json={
            "prompt": "这是一个用于测试的低优先级风险 Agent 提示词版本。必须返回结构化 JSON。",
            "capabilities": ["risk_analysis", "route_validation"],
            "tools": ["route_risk_probe"],
            "priority": 1,
            "enabled": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["version"] >= 2

    async def exercise_mcp() -> None:
        server = StdioMcpServer()
        initialized = await server.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        assert initialized["result"]["serverInfo"]["name"] == "delta-exfil-tools"
        tools = await server.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        )
        assert any(tool["name"] == "map_lookup" for tool in tools["result"]["tools"])
        called = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "loadout_validate",
                    "arguments": {"weight": 45, "capacity": 38},
                },
            }
        )
        assert called["result"]["isError"] is False

    asyncio.run(exercise_mcp())


def test_evaluation_report() -> None:
    response = client.post("/api/evaluations/run")
    assert response.status_code == 200
    report = response.json()
    assert report["summary"]["scenarios"] == 8
    assert report["summary"]["passed"] == 8

    latest = client.get("/api/evaluations/latest")
    assert latest.status_code == 200
    assert latest.json()["summary"]["passRate"] == 1.0
