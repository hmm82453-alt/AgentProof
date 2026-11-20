from __future__ import annotations

from typing import Any

from app.agents.base import BaseTacticalAgent
from app.schemas import AgentRequest


class SupplyAgent(BaseTacticalAgent):
    agent_id = "supply"
    display_name = "物资规划 Agent"
    llm_editable_fields = {"lootRule", "carryRule", "activity"}
    system_prompt = """
你是撤离任务的物资规划 Agent。结合地图资源、风险草稿、干员草稿和负重，
决定烟雾、医疗、搜刮优先级和携带方式。不得虚构物品价值。
返回严格 JSON 对象，必须保留 messageId、consumes、broadcasts、adjustedWeight、
capacity、smokeCount、overweight、supplies、resourcePriority、lootRule、
carryRule、peerInput、activity。不要输出 Markdown。
""".strip()

    async def run(self, request: AgentRequest) -> dict[str, Any]:
        if request.phase == "draft":
            return self._draft(request)
        return await self.respond(request, self._refine(request))

    def _draft(self, request: AgentRequest) -> dict[str, Any]:
        return {
            "draft": True,
            "messageId": f"SUP-DR-R{request.round}",
            "initialWeight": request.input.weight,
            "capacity": 38,
            "smokeCount": 2 if request.round == 1 else 4,
            "mapResources": request.context["map"]["resources"],
        }

    def _refine(self, request: AgentRequest) -> dict[str, Any]:
        map_profile = request.context["map"]
        risk_draft = request.peers.get("riskDraft", {})
        operator_draft = request.peers.get("operatorDraft", {})
        previous_audit = request.peers.get("previousAudit")
        draft = request.peers.get("supplyDraft", self._draft(request))
        smoke_user = operator_draft.get("smokeUser") or "投掷物支援位"

        capacity = int(draft["capacity"])
        initial_weight = float(draft["initialWeight"])
        risk_pressure = 2 if float(risk_draft.get("rawScore", 80)) >= 75 else 0
        smoke_count = int(min(max(int(draft["smokeCount"]) + risk_pressure, 2), 6))
        adjusted_weight = initial_weight
        if adjusted_weight > capacity and request.round > 1:
            adjusted_weight = max(12, adjusted_weight - (request.round - 1) * 4)
        overweight = adjusted_weight > capacity
        resources = map_profile.get("resources", [])

        return {
            "messageId": f"SUP-R{request.round}-01",
            "consumes": [
                map_profile.get("messageId", f"INT-R{request.round}-01"),
                f"RSK-DR-R{request.round}",
                f"OPS-DR-R{request.round}",
            ],
            "broadcasts": ["RISK", "OPERATOR", "AUDIT"],
            "adjustedWeight": adjusted_weight,
            "capacity": capacity,
            "smokeCount": smoke_count,
            "overweight": overweight,
            "supplies": [
                "医疗包 ×2",
                "止血带 ×3",
                f"烟雾弹 ×{smoke_count}",
                "侦察标记 ×1",
            ],
            "resourcePriority": [
                f"{item['name']}：{item['items']}"
                for item in resources
                if item["value"] in {"高", "极高"}
            ][:2],
            "lootRule": (
                "只收高价值小件，优先保证烟幕、医疗与弹药"
                if request.input.tactic == "高风险速撤" or overweight
                else "先保队伍补给，再按价值密度搜索，避免长时间停留"
            ),
            "carryRule": (
                f"根据仲裁反馈取消低价值工业物资，为{smoke_user}保留烟幕资源"
                if previous_audit
                else f"烟雾按风险草稿临时增加，优先交给{smoke_user}携带"
            ),
            "peerInput": [
                f"风险草稿 {risk_draft.get('rawScore')}",
                f"干员草稿需要 {smoke_user} 承担烟幕",
            ],
            "activity": f"完成物资复核，烟雾{smoke_count}颗，负重{adjusted_weight:.1f}kg",
        }
