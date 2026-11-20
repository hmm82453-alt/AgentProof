from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any, Awaitable, Callable

from app.data.maps import get_map_profile
from app.data.operators import OPERATOR_PROFILES, get_operator_profile
from app.services.storage import run_repository


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]


async def _map_lookup(arguments: dict[str, Any]) -> dict[str, Any]:
    game_mode = str(arguments.get("gameMode", "normal"))
    profile = get_map_profile(arguments.get("map", "零号大坝"), game_mode)
    return {
        "map": arguments.get("map", "零号大坝"),
        "gameMode": game_mode,
        "route": profile["route"],
        "resources": profile["resources"],
        "exfils": profile["exfils"],
        "riskNodes": profile["riskNodes"],
        "dataVersion": profile["dataVersion"],
        "verificationStatus": profile["verificationStatus"],
        "verificationNote": profile["verificationNote"],
        "sources": profile["sources"],
    }


async def _route_risk_probe(arguments: dict[str, Any]) -> dict[str, Any]:
    score = float(arguments.get("score", 50))
    length = float(arguments.get("exposedSeconds", 45))
    adjusted = min(99, round(score + max(0, length - 45) * 0.3))
    return {
        "score": adjusted,
        "level": "高" if adjusted >= 78 else "中高" if adjusted >= 62 else "中",
        "requiresSmoke": adjusted >= 72 or length > 45,
    }


async def _loadout_validate(arguments: dict[str, Any]) -> dict[str, Any]:
    weight = float(arguments.get("weight", 0))
    capacity = float(arguments.get("capacity", 38))
    return {
        "valid": weight <= capacity,
        "weight": weight,
        "capacity": capacity,
        "overweightBy": max(0, round(weight - capacity, 1)),
    }


async def _extraction_check(arguments: dict[str, Any]) -> dict[str, Any]:
    map_name = arguments.get("map", "零号大坝")
    game_mode = str(arguments.get("gameMode", "normal"))
    profile = get_map_profile(map_name, game_mode)
    team_size = int(arguments.get("squadSize", 3))
    exfil = profile["exfils"][0]
    return {
        "map": map_name,
        "gameMode": game_mode,
        "extraction": exfil["name"],
        "condition": exfil["condition"],
        "requiresAllMembers": "全员" in exfil["condition"],
        "teamSize": team_size,
        "satisfiedByPlan": team_size >= 1,
        "verificationStatus": profile["verificationStatus"],
        "verificationNote": profile["verificationNote"],
    }


async def _operator_catalog(arguments: dict[str, Any]) -> dict[str, Any]:
    names = arguments.get("operators") or list(OPERATOR_PROFILES)
    return {
        "items": [get_operator_profile(name) for name in names]
    }


async def _snapshot_query(arguments: dict[str, Any]) -> dict[str, Any]:
    run_id = arguments.get("runId")
    if not run_id:
        return {"items": []}
    return {"items": run_repository.list_snapshots(str(run_id))}


TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "map_lookup": {
        "description": "读取地图资源点、风险节点和撤离条件。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "map": {"type": "string"},
                "gameMode": {
                    "type": "string",
                    "enum": ["normal", "confidential", "top_secret"],
                },
            },
            "required": ["map"],
        },
        "handler": _map_lookup,
    },
    "route_risk_probe": {
        "description": "根据风险分和暴露时长计算路线风险。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "exposedSeconds": {"type": "number"},
            },
        },
        "handler": _route_risk_probe,
    },
    "loadout_validate": {
        "description": "校验负重是否超过容量。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "weight": {"type": "number"},
                "capacity": {"type": "number"},
            },
            "required": ["weight", "capacity"],
        },
        "handler": _loadout_validate,
    },
    "extraction_check": {
        "description": "查询撤离条件和队伍人数约束。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "map": {"type": "string"},
                "squadSize": {"type": "integer"},
                "gameMode": {
                    "type": "string",
                    "enum": ["normal", "confidential", "top_secret"],
                },
            },
            "required": ["map"],
        },
        "handler": _extraction_check,
    },
    "operator_catalog": {
        "description": "读取干员能力、限制和携带规则。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operators": {"type": "array", "items": {"type": "string"}}
            },
        },
        "handler": _operator_catalog,
    },
    "snapshot_query": {
        "description": "查询某次运行的战术状态快照。",
        "inputSchema": {
            "type": "object",
            "properties": {"runId": {"type": "string"}},
            "required": ["runId"],
        },
        "handler": _snapshot_query,
    },
}


class ToolRegistry:
    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "description": definition["description"],
                "inputSchema": definition["inputSchema"],
            }
            for name, definition in TOOL_DEFINITIONS.items()
        ]

    async def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        definition = TOOL_DEFINITIONS.get(name)
        if definition is None:
            raise KeyError(name)
        started = perf_counter()
        result = definition["handler"](arguments)
        if asyncio.iscoroutine(result):
            result = await result
        return {
            "tool": name,
            "arguments": arguments,
            "result": result,
            "durationMs": round((perf_counter() - started) * 1000),
        }


tool_registry = ToolRegistry()
