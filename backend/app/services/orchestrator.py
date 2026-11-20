from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any

from app.agents.audit import AuditAgent
from app.agents.map_intel import MapIntelAgent
from app.agents.operator import OperatorAgent
from app.agents.risk import RiskAgent
from app.agents.supply import SupplyAgent
from app.schemas import AgentRequest, MissionInput
from app.services.events import event_broker
from app.services.storage import RunRepository, run_repository
from app.tools.registry import tool_registry


logger = logging.getLogger(__name__)


class RunOrchestrator:
    def __init__(self, repository: RunRepository | None = None) -> None:
        self.repository = repository or run_repository
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.map_agent = MapIntelAgent()
        self.risk_agent = RiskAgent()
        self.supply_agent = SupplyAgent()
        self.operator_agent = OperatorAgent()
        self.audit_agent = AuditAgent()

    def start(
        self,
        run_id: str,
        mission: MissionInput,
        max_rounds: int,
        *,
        workflow: dict[str, Any] | None = None,
        schedule: dict[str, Any] | None = None,
        resume_context: dict[str, Any] | None = None,
        start_round: int = 1,
    ) -> None:
        task = asyncio.create_task(
            self.execute(
                run_id,
                mission,
                max_rounds,
                workflow=workflow,
                schedule=schedule,
                resume_context=resume_context,
                start_round=start_round,
            )
        )
        self.tasks[run_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(run_id, None))

    def cancel(self, run_id: str) -> bool:
        task = self.tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def _emit(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        event = self.repository.append_event(run_id, event_type, payload, agent_id)
        event_broker.publish(run_id, event)
        return event

    def _log(
        self,
        run_id: str,
        tag: str,
        message: str,
        kind: str = "info",
        agent_id: str | None = None,
    ) -> None:
        self._emit(
            run_id,
            "log",
            {"tag": tag, "message": message, "kind": kind},
            agent_id,
        )

    def _agent_state(
        self,
        run_id: str,
        agent_id: str,
        state: str,
        activity: str,
        *,
        latency: int | None = None,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
    ) -> None:
        self._emit(
            run_id,
            "agent.state",
            {
                "agentId": agent_id,
                "state": state,
                "activity": activity,
                "latency": latency,
                "evidence": {
                    "inputs": inputs or [],
                    "outputs": outputs or [],
                },
            },
            agent_id,
        )

    def _bus(
        self,
        run_id: str,
        *,
        source: str,
        target: str,
        title: str,
        detail: str,
        kind: str = "info",
    ) -> None:
        self._emit(
            run_id,
            "bus.message",
            {
                "from": source,
                "to": target,
                "title": title,
                "detail": detail,
                "kind": kind,
            },
        )

    async def _call_tool(
        self,
        run_id: str,
        name: str,
        arguments: dict[str, Any],
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        result = await tool_registry.invoke(name, arguments)
        self._emit(
            run_id,
            "tool.called",
            result,
            agent_id,
        )
        return result

    async def execute(
        self,
        run_id: str,
        mission: MissionInput,
        max_rounds: int,
        *,
        workflow: dict[str, Any] | None = None,
        schedule: dict[str, Any] | None = None,
        resume_context: dict[str, Any] | None = None,
        start_round: int = 1,
    ) -> None:
        self.repository.update_run(run_id, status="running")
        workflow = workflow or {}
        schedule = schedule or {"policy": "capability-load-priority", "selected": {}}
        selected_agents = schedule.get("selected", {})
        for role, selected in selected_agents.items():
            agent = getattr(self, f"{role}_agent", None)
            if agent is not None and selected.get("prompt"):
                agent.system_prompt = selected["prompt"]

        self._emit(
            run_id,
            "run.started",
            {
                "runId": run_id,
                "input": mission.model_dump(),
                "maxRounds": max_rounds,
                "resumedFrom": resume_context is not None,
            },
        )
        self._emit(
            run_id,
            "workflow.loaded",
            {
                "mode": "resume" if resume_context else "fresh",
                "startRound": start_round,
                "maxRounds": max_rounds,
                "stages": workflow.get("stages", []),
            },
        )
        self._emit(
            run_id,
            "scheduler.decision",
            schedule,
        )
        self._log(
            run_id,
            "ORCH",
            f"服务端运行启动：{mission.map} / {mission.squadSize} 人 / {mission.tactic}",
            "success",
        )

        map_result: dict[str, Any] | None = (
            resume_context.get("map") if resume_context else None
        )
        previous_audit: dict[str, Any] | None = (
            resume_context.get("audit") if resume_context else None
        )
        latest_context: dict[str, Any] | None = resume_context

        try:
            for round_number in range(start_round, max_rounds + 1):
                self.repository.update_run(run_id, current_round=round_number)
                self._emit(
                    run_id,
                    "round.started",
                    {"round": round_number, "maxRounds": max_rounds},
                )
                self._log(run_id, "ROUND", f"开始第{round_number}轮协同规划")

                if map_result is None:
                    self._agent_state(
                        run_id,
                        "map",
                        "working",
                        f"正在扫描{mission.map}的路线与撤离窗口",
                        inputs=["任务参数"],
                    )
                    started = perf_counter()
                    map_payload = AgentRequest(
                        input=mission,
                        round=round_number,
                        context={},
                    )
                    map_result = await self.map_agent.run(map_payload)
                    latency = round((perf_counter() - started) * 1000)
                    self._agent_state(
                        run_id,
                        "map",
                        "complete",
                        map_result["activity"],
                        latency=latency,
                        inputs=map_result.get("consumes", []),
                        outputs=map_result.get("broadcasts", []),
                    )
                    self._log(
                        run_id,
                        "MAP",
                        f"{map_result['messageId']} 情报产出：{map_result['intel']}",
                        agent_id="map",
                    )
                    self._bus(
                        run_id,
                        source=map_result["messageId"],
                        target="RISK / SUPPLY / OPERATOR",
                        title=f"{map_result['extraction']}与资源区已广播",
                        detail=(
                            f"{map_result['route']}；{len(map_result['resources'])}个资源点、"
                            f"{len(map_result['exfils'])}个撤离条件已写入共享上下文。"
                        ),
                        kind="success",
                    )
                    await self._call_tool(
                        run_id,
                        "map_lookup",
                        {"map": mission.map, "gameMode": mission.gameMode},
                        "map",
                    )
                    await self._call_tool(
                        run_id,
                        "extraction_check",
                        {
                            "map": mission.map,
                            "squadSize": mission.squadSize,
                            "gameMode": mission.gameMode,
                        },
                        "map",
                    )

                assert map_result is not None
                context = {"map": map_result, "previousAudit": previous_audit}
                payloads = {
                    "risk": AgentRequest(
                        input=mission,
                        round=round_number,
                        context={**context, "input": mission.model_dump()},
                        phase="draft",
                    ),
                    "supply": AgentRequest(
                        input=mission,
                        round=round_number,
                        context=context,
                        phase="draft",
                    ),
                    "operator": AgentRequest(
                        input=mission,
                        round=round_number,
                        context={**context, "input": mission.model_dump()},
                        phase="draft",
                    ),
                }

                for agent_id in ("risk", "supply", "operator"):
                    self._agent_state(
                        run_id,
                        agent_id,
                        "working",
                        "正在生成并行草稿",
                        inputs=["任务参数", map_result["messageId"]],
                    )

                started = perf_counter()
                risk_draft, supply_draft, operator_draft = await asyncio.gather(
                    self.risk_agent.run(payloads["risk"]),
                    self.supply_agent.run(payloads["supply"]),
                    self.operator_agent.run(payloads["operator"]),
                )
                self._bus(
                    run_id,
                    source="PARALLEL DRAFTS",
                    target="RSK ↔ SUP ↔ OPS",
                    title="三个并行 Agent 交换中间草稿",
                    detail=(
                        f"风险草稿{risk_draft['rawScore']}，物资草稿烟雾"
                        f"{supply_draft['smokeCount']}颗，干员草稿后卫延迟"
                        f"{operator_draft['gapSeconds']}秒。"
                    ),
                )

                peers = {
                    "riskDraft": risk_draft,
                    "supplyDraft": supply_draft,
                    "operatorDraft": operator_draft,
                    "previousAudit": previous_audit,
                }
                refine_payloads = {
                    key: payload.model_copy(
                        update={"phase": "refine", "peers": peers}
                    )
                    for key, payload in payloads.items()
                }
                risk, supply, operator = await asyncio.gather(
                    self.risk_agent.run(refine_payloads["risk"]),
                    self.supply_agent.run(refine_payloads["supply"]),
                    self.operator_agent.run(refine_payloads["operator"]),
                )
                latency = round((perf_counter() - started) * 1000)
                for agent_id, result in (
                    ("risk", risk),
                    ("supply", supply),
                    ("operator", operator),
                ):
                    self._agent_state(
                        run_id,
                        agent_id,
                        "complete",
                        result["activity"],
                        latency=latency,
                        inputs=result.get("consumes", []),
                        outputs=result.get("broadcasts", []),
                    )
                    self._bus(
                        run_id,
                        source=result["messageId"],
                        target=" / ".join(result["broadcasts"]),
                        title=result["activity"],
                        detail=(
                            result.get("relayRule")
                            or result.get("carryRule")
                            or result.get("routeDecision", "")
                        ),
                        kind=(
                            "warning"
                            if result.get("gapSeconds", 0) > 0
                            or result.get("overweight")
                            else "success"
                        ),
                    )

                self._agent_state(
                    run_id,
                    "audit",
                    "working",
                    "正在核对技能覆盖、资源条件、负重与撤离约束",
                    inputs=[
                        map_result["messageId"],
                        risk["messageId"],
                        supply["messageId"],
                        operator["messageId"],
                    ],
                )
                started = perf_counter()
                await self._call_tool(
                    run_id,
                    "loadout_validate",
                    {"weight": mission.weight, "capacity": 38},
                    "audit",
                )
                await self._call_tool(
                    run_id,
                    "extraction_check",
                    {
                        "map": mission.map,
                        "squadSize": mission.squadSize,
                        "gameMode": mission.gameMode,
                    },
                    "audit",
                )
                audit_payload = AgentRequest(
                    input=mission,
                    round=round_number,
                    context={
                        **context,
                        "risk": risk,
                        "supply": supply,
                        "operator": operator,
                    },
                )
                audit = await self.audit_agent.run(audit_payload)
                latency = round((perf_counter() - started) * 1000)
                self._agent_state(
                    run_id,
                    "audit",
                    "complete",
                    audit["activity"],
                    latency=latency,
                    inputs=audit.get("consumes", []),
                    outputs=audit.get("broadcasts", []),
                )

                latest_context = {
                    "map": map_result,
                    "risk": risk,
                    "supply": supply,
                    "operator": operator,
                    "audit": audit,
                    "previousAudit": previous_audit,
                }
                score = int(audit["score"])
                self.repository.update_run(run_id, score=score)
                self._emit(
                    run_id,
                    "round.result",
                    {
                        "round": round_number,
                        "pass": audit["pass"],
                        "audit": audit,
                        "context": latest_context,
                    },
                )
                snapshot = self.repository.create_snapshot(
                    run_id,
                    round_number,
                    f"第{round_number}轮{'通过' if audit['pass'] else '驳回'}快照",
                    latest_context,
                )
                self._emit(
                    run_id,
                    "snapshot.created",
                    {
                        "id": snapshot["id"],
                        "round": round_number,
                        "label": snapshot["label"],
                    },
                )
                self._log(
                    run_id,
                    "AUD",
                    (
                        f"{audit['messageId']} 仲裁通过，评分{score}"
                        if audit["pass"]
                        else f"{audit['messageId']} 仲裁拦截：{audit['issue']}"
                    ),
                    "success" if audit["pass"] else "error",
                    "audit",
                )

                if audit["pass"]:
                    self.repository.update_run(
                        run_id,
                        status="completed",
                        score=score,
                        result_json=audit,
                    )
                    self._emit(
                        run_id,
                        "run.completed",
                        {
                            "runId": run_id,
                            "status": "completed",
                            "round": round_number,
                            "result": audit,
                            "context": latest_context,
                        },
                    )
                    return

                previous_audit = audit

            assert latest_context is not None
            final_audit = latest_context["audit"]
            self.repository.update_run(
                run_id,
                status="rejected",
                result_json=final_audit,
            )
            self._emit(
                run_id,
                "run.completed",
                {
                    "runId": run_id,
                    "status": "rejected",
                    "round": max_rounds,
                    "result": final_audit,
                    "context": latest_context,
                },
            )
        except asyncio.CancelledError:
            self.repository.update_run(run_id, status="cancelled")
            self._emit(
                run_id,
                "run.cancelled",
                {"runId": run_id, "message": "运行已被取消"},
            )
            raise
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            self.repository.update_run(run_id, status="failed", error=str(exc))
            self._emit(
                run_id,
                "run.failed",
                {"runId": run_id, "message": str(exc)},
            )


run_orchestrator = RunOrchestrator()
