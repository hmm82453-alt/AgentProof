from __future__ import annotations

import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.schemas import MissionInput
from app.services.orchestrator import RunOrchestrator
from app.services.registry import workflow_registry
from app.services.scheduler import dynamic_scheduler
from app.services.storage import RunRepository


REPORT_PATH = Path(__file__).resolve().parents[2] / "reports" / "evaluation-latest.json"

SCENARIOS = [
    {
        "name": f"{map_name} / 稳健搜打",
        "map": map_name,
        "squadSize": 3,
        "tactic": "稳健搜打",
        "operators": ["红狼", "蜂医", "露娜"],
        "weight": 31.5,
        "expectedStatus": "completed",
    }
    for map_name in ["零号大坝", "长弓溪谷", "巴克什", "航天基地", "潮汐监狱"]
] + [
    {
        "name": "零号大坝 / 超重负重",
        "map": "零号大坝",
        "squadSize": 3,
        "tactic": "稳健搜打",
        "operators": ["红狼", "蜂医", "露娜"],
        "weight": 60,
        "expectedStatus": "rejected",
    },
    {
        "name": "航天基地 / 干员数量不足",
        "map": "航天基地",
        "squadSize": 3,
        "tactic": "稳健搜打",
        "operators": ["红狼"],
        "weight": 31.5,
        "expectedStatus": "rejected",
    },
    {
        "name": "长弓溪谷 / 高风险速撤",
        "map": "长弓溪谷",
        "squadSize": 3,
        "tactic": "高风险速撤",
        "operators": ["野火", "蜂医", "露娜"],
        "weight": 34.5,
        "expectedStatus": "completed",
    },
]

# Bakash currently lacks a complete public extraction-point set.
SCENARIOS[2]["expectedStatus"] = "rejected"


class EvaluationService:
    async def run(self) -> dict[str, Any]:
        workflow = workflow_registry.get_workflow("extraction-default")
        definition = workflow["active"]["definition"]
        results: list[dict[str, Any]] = []

        with tempfile.TemporaryDirectory(prefix="delta-eval-") as temp_dir:
            repository = RunRepository(str(Path(temp_dir) / "evaluation.db"))
            orchestrator = RunOrchestrator(repository)

            for scenario in SCENARIOS:
                mission = MissionInput(
                    map=scenario["map"],
                    squadSize=scenario["squadSize"],
                    tactic=scenario["tactic"],
                    operators=scenario["operators"],
                    weight=scenario["weight"],
                )
                schedule = dynamic_scheduler.schedule(
                    ["map", "risk", "supply", "operator", "audit"],
                    tactic=mission.tactic,
                    workflow_definition=definition,
                )
                max_rounds = int(definition.get("maxRounds", 4))
                run = repository.create_run(
                    mission.model_dump(),
                    max_rounds,
                    workflow_key=workflow["key"],
                    workflow_version=workflow["active"]["version"],
                    agent_manifest=schedule["selected"],
                )
                started = time.perf_counter()
                await orchestrator.execute(
                    run["id"],
                    mission,
                    max_rounds,
                    workflow=definition,
                    schedule=schedule,
                )
                elapsed = round(time.perf_counter() - started, 3)
                final = repository.get_run(run["id"])
                events = repository.get_events(run["id"])
                success = final["status"] == scenario["expectedStatus"]
                results.append(
                    {
                        **scenario,
                        "runId": run["id"],
                        "actualStatus": final["status"],
                        "round": final["currentRound"],
                        "score": final["score"],
                        "elapsedSeconds": elapsed,
                        "eventCount": len(events),
                        "snapshots": len(repository.list_snapshots(run["id"])),
                        "passed": success,
                    }
                )

        passed = sum(item["passed"] for item in results)
        report = {
            "generatedAt": datetime.now(UTC).isoformat(),
            "workflow": {
                "key": workflow["key"],
                "version": workflow["active"]["version"],
            },
            "summary": {
                "scenarios": len(results),
                "passed": passed,
                "passRate": round(passed / len(results), 4),
                "averageRounds": round(
                    sum(item["round"] for item in results) / len(results),
                    2,
                ),
                "averageElapsedSeconds": round(
                    sum(item["elapsedSeconds"] for item in results) / len(results),
                    3,
                ),
            },
            "scenarios": results,
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report

    @staticmethod
    def latest() -> dict[str, Any]:
        if not REPORT_PATH.exists():
            raise FileNotFoundError(str(REPORT_PATH))
        return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


evaluation_service = EvaluationService()
