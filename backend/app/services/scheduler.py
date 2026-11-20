from __future__ import annotations

from typing import Any

from app.services.registry import AgentRegistry, agent_registry


class DynamicAgentScheduler:
    """Select the highest priority compatible Agent version per workflow role."""

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or agent_registry

    def schedule(
        self,
        roles: list[str],
        *,
        tactic: str,
        workflow_definition: dict[str, Any],
    ) -> dict[str, Any]:
        requirements = {
            "risk": {"risk_analysis"},
            "supply": {"loadout_planning"},
            "operator": {"team_formation"},
            "map": {"map_intel"},
            "audit": {"verification"},
        }
        selected: dict[str, Any] = {}
        reasons: dict[str, str] = {}

        for role in roles:
            required = requirements.get(role, set())
            candidate = self.registry.resolve(role, required)
            selected[role] = candidate
            reason = (
                f"能力匹配 {sorted(required)}，版本 {candidate['version']}，"
                f"优先级 {candidate['priority']}"
            )
            if role == "risk" and tactic == "高风险速撤":
                reason += "；高风险打法提高风险审查权重"
            reasons[role] = reason

        policy = workflow_definition.get("scheduler", {})
        return {
            "policy": policy.get("policy", "capability-load-priority"),
            "maxParallel": policy.get("maxParallel", 3),
            "selected": {
                role: {
                    "version": item["version"],
                    "prompt": item["prompt"],
                    "priority": item["priority"],
                    "capabilities": item["capabilities"],
                    "tools": item["tools"],
                }
                for role, item in selected.items()
            },
            "reasons": reasons,
        }


dynamic_scheduler = DynamicAgentScheduler()
