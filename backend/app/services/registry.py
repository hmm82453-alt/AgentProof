from __future__ import annotations

import json
import uuid
from typing import Any

from app.agents.audit import AuditAgent
from app.agents.map_intel import MapIntelAgent
from app.agents.operator import OperatorAgent
from app.agents.risk import RiskAgent
from app.agents.supply import SupplyAgent
from app.services.storage import RunRepository, run_repository, utc_now


AGENT_CLASS_MAP = {
    "map": MapIntelAgent,
    "risk": RiskAgent,
    "supply": SupplyAgent,
    "operator": OperatorAgent,
    "audit": AuditAgent,
}

AGENT_SEEDS = {
    "map": {
        "name": "地图情报 Agent",
        "capabilities": ["map_intel", "resource_discovery", "extraction_rules", "route_mapping"],
        "tools": ["map_lookup", "extraction_check"],
        "priority": 100,
    },
    "risk": {
        "name": "风险评估 Agent",
        "capabilities": ["risk_analysis", "route_validation", "conflict_detection"],
        "tools": ["route_risk_probe"],
        "priority": 90,
    },
    "supply": {
        "name": "物资规划 Agent",
        "capabilities": ["loadout_planning", "resource_priority", "weight_control"],
        "tools": ["loadout_validate"],
        "priority": 80,
    },
    "operator": {
        "name": "干员协同 Agent",
        "capabilities": ["team_formation", "operator_skills", "relay_planning"],
        "tools": ["operator_catalog"],
        "priority": 80,
    },
    "audit": {
        "name": "校验复盘 Agent",
        "capabilities": ["verification", "arbitration", "constraint_check", "feedback_loop"],
        "tools": ["loadout_validate", "extraction_check", "snapshot_query"],
        "priority": 100,
    },
}


class AgentRegistry:
    def __init__(self, repository: RunRepository | None = None) -> None:
        self.repository = repository or run_repository
        self.seed_defaults()

    def seed_defaults(self) -> None:
        now = utc_now()
        with self.repository._connection() as connection:
            for agent_key, seed in AGENT_SEEDS.items():
                connection.execute(
                    """
                    INSERT OR IGNORE INTO agent_definitions (
                        agent_key, display_name, created_at
                    ) VALUES (?, ?, ?)
                    """,
                    (agent_key, seed["name"], now),
                )
                existing = connection.execute(
                    """
                    SELECT version FROM agent_versions
                    WHERE agent_key = ?
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (agent_key,),
                ).fetchone()
                if existing is None:
                    agent_class = AGENT_CLASS_MAP[agent_key]
                    connection.execute(
                        """
                        INSERT INTO agent_versions (
                            id, agent_key, version, prompt, capabilities_json,
                            tools_json, priority, enabled, created_at
                        ) VALUES (?, ?, 1, ?, ?, ?, ?, 1, ?)
                        """,
                        (
                            uuid.uuid4().hex,
                            agent_key,
                            agent_class.system_prompt,
                            json.dumps(seed["capabilities"], ensure_ascii=False),
                            json.dumps(seed["tools"], ensure_ascii=False),
                            seed["priority"],
                            now,
                        ),
                    )

    def list_agents(self) -> list[dict[str, Any]]:
        with self.repository._connection() as connection:
            rows = connection.execute(
                """
                SELECT d.agent_key, d.display_name, d.created_at,
                       v.id, v.version, v.prompt, v.capabilities_json,
                       v.tools_json, v.priority, v.enabled, v.created_at AS version_created_at
                FROM agent_definitions d
                JOIN agent_versions v ON v.agent_key = d.agent_key
                ORDER BY d.agent_key ASC, v.version DESC
                """
            ).fetchall()

        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = grouped.setdefault(
                row["agent_key"],
                {
                    "key": row["agent_key"],
                    "displayName": row["display_name"],
                    "createdAt": row["created_at"],
                    "versions": [],
                },
            )
            item["versions"].append(self._version_row(row))
        return list(grouped.values())

    def get_agent(self, agent_key: str) -> dict[str, Any]:
        agents = self.list_agents()
        for agent in agents:
            if agent["key"] == agent_key:
                return agent
        raise KeyError(agent_key)

    def resolve(self, agent_key: str, required_capabilities: set[str] | None = None) -> dict[str, Any]:
        agent = self.get_agent(agent_key)
        required = required_capabilities or set()
        candidates = [
            version
            for version in agent["versions"]
            if version["enabled"] and required.issubset(set(version["capabilities"]))
        ]
        if not candidates:
            raise KeyError(
                f"no enabled {agent_key} version has capabilities {sorted(required)}"
            )
        selected = max(candidates, key=lambda version: (version["priority"], version["version"]))
        return {
            **selected,
            "key": agent_key,
            "displayName": agent["displayName"],
        }

    def register_version(
        self,
        agent_key: str,
        *,
        prompt: str,
        capabilities: list[str],
        tools: list[str],
        priority: int = 50,
        enabled: bool = True,
    ) -> dict[str, Any]:
        agent = self.get_agent(agent_key)
        with self.repository._connection() as connection:
            row = connection.execute(
                "SELECT MAX(version) AS version FROM agent_versions WHERE agent_key = ?",
                (agent_key,),
            ).fetchone()
            version = int(row["version"] or 0) + 1
            version_id = uuid.uuid4().hex
            now = utc_now()
            connection.execute(
                """
                INSERT INTO agent_versions (
                    id, agent_key, version, prompt, capabilities_json,
                    tools_json, priority, enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    agent_key,
                    version,
                    prompt,
                    json.dumps(capabilities, ensure_ascii=False),
                    json.dumps(tools, ensure_ascii=False),
                    priority,
                    int(enabled),
                    now,
                ),
            )
        return next(
            version_item
            for version_item in self.get_agent(agent_key)["versions"]
            if version_item["version"] == version
        )

    @staticmethod
    def _version_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "version": row["version"],
            "prompt": row["prompt"],
            "capabilities": json.loads(row["capabilities_json"]),
            "tools": json.loads(row["tools_json"]),
            "priority": row["priority"],
            "enabled": bool(row["enabled"]),
            "createdAt": row["version_created_at"],
        }


DEFAULT_WORKFLOW = {
    "maxRounds": 4,
    "stages": [
        {"id": "map-intel", "type": "agent", "role": "map"},
        {
            "id": "parallel-drafts",
            "type": "parallel",
            "roles": ["risk", "supply", "operator"],
            "phase": "draft",
        },
        {
            "id": "peer-refine",
            "type": "parallel",
            "roles": ["risk", "supply", "operator"],
            "phase": "refine",
        },
        {"id": "audit", "type": "agent", "role": "audit"},
        {
            "id": "decision-gate",
            "type": "condition",
            "field": "audit.pass",
            "onFalse": "next-round",
        },
    ],
    "scheduler": {
        "policy": "capability-load-priority",
        "maxParallel": 3,
    },
}


class WorkflowRegistry:
    def __init__(self, repository: RunRepository | None = None) -> None:
        self.repository = repository or run_repository
        self.seed_defaults()

    def seed_defaults(self) -> None:
        now = utc_now()
        with self.repository._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO workflows (workflow_key, name, created_at)
                VALUES ('extraction-default', '撤离多 Agent 协同规划', ?)
                """,
                (now,),
            )
            exists = connection.execute(
                """
                SELECT 1 FROM workflow_versions
                WHERE workflow_key = 'extraction-default'
                LIMIT 1
                """
            ).fetchone()
            if exists is None:
                connection.execute(
                    """
                    INSERT INTO workflow_versions (
                        id, workflow_key, version, definition_json, enabled, created_at
                    ) VALUES (?, 'extraction-default', 1, ?, 1, ?)
                    """,
                    (uuid.uuid4().hex, json.dumps(DEFAULT_WORKFLOW, ensure_ascii=False), now),
                )

    def list_workflows(self) -> list[dict[str, Any]]:
        with self.repository._connection() as connection:
            rows = connection.execute(
                """
                SELECT w.workflow_key, w.name, w.created_at,
                       v.id, v.version, v.definition_json, v.enabled,
                       v.created_at AS version_created_at
                FROM workflows w
                JOIN workflow_versions v ON v.workflow_key = w.workflow_key
                ORDER BY w.workflow_key ASC, v.version DESC
                """
            ).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            workflow = grouped.setdefault(
                row["workflow_key"],
                {
                    "key": row["workflow_key"],
                    "name": row["name"],
                    "createdAt": row["created_at"],
                    "versions": [],
                },
            )
            workflow["versions"].append(
                {
                    "id": row["id"],
                    "version": row["version"],
                    "definition": json.loads(row["definition_json"]),
                    "enabled": bool(row["enabled"]),
                    "createdAt": row["version_created_at"],
                }
            )
        return list(grouped.values())

    def get_workflow(self, workflow_key: str = "extraction-default") -> dict[str, Any]:
        for workflow in self.list_workflows():
            if workflow["key"] == workflow_key:
                active = [item for item in workflow["versions"] if item["enabled"]]
                if not active:
                    raise KeyError(f"{workflow_key} has no enabled version")
                return {
                    **workflow,
                    "active": max(active, key=lambda item: item["version"]),
                }
        raise KeyError(workflow_key)

    def register_version(
        self,
        workflow_key: str,
        definition: dict[str, Any],
        *,
        enabled: bool = True,
    ) -> dict[str, Any]:
        workflow = self.get_workflow(workflow_key)
        with self.repository._connection() as connection:
            version = max(item["version"] for item in workflow["versions"]) + 1
            version_id = uuid.uuid4().hex
            now = utc_now()
            connection.execute(
                """
                INSERT INTO workflow_versions (
                    id, workflow_key, version, definition_json, enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    workflow_key,
                    version,
                    json.dumps(definition, ensure_ascii=False),
                    int(enabled),
                    now,
                ),
            )
        return next(
            item
            for item in self.get_workflow(workflow_key)["versions"]
            if item["version"] == version
        )


agent_registry = AgentRegistry()
workflow_registry = WorkflowRegistry()
