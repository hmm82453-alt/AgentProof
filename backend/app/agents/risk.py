from __future__ import annotations

from typing import Any

from app.agents.base import BaseTacticalAgent
from app.schemas import AgentRequest


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


class RiskAgent(BaseTacticalAgent):
    agent_id = "risk"
    display_name = "风险评估 Agent"
    llm_editable_fields = {"warnings", "decision", "activity"}
    system_prompt = """
你是撤离任务的风险评估 Agent。读取地图风险节点、风险与物资草稿、干员草稿，
交叉判断路线冲突、烟幕覆盖与后卫接力延迟。只依据输入数据，不得虚构事实。
返回严格 JSON 对象，必须保留 messageId、consumes、broadcasts、score、level、
riskNodes、warnings、route、routeDecision、decision、peerInput、activity。不要输出 Markdown。
""".strip()

    async def run(self, request: AgentRequest) -> dict[str, Any]:
        if request.phase == "draft":
            return self._draft(request)
        return await self.respond(request, self._refine(request))

    def _draft(self, request: AgentRequest) -> dict[str, Any]:
        tactic_modifier = {
            "稳健搜打": 4,
            "高风险速撤": 13,
            "潜行避战": -7,
        }[request.input.tactic]
        squad_modifier = -4 if request.input.squadSize >= 3 else 7
        pressure = 10 if request.round == 1 else 0
        raw_score = round(_clamp(70 + tactic_modifier + squad_modifier + pressure, 48, 94))
        map_profile = request.context["map"]
        return {
            "draft": True,
            "messageId": f"RSK-DR-R{request.round}",
            "rawScore": raw_score,
            "riskNode": map_profile["riskNode"],
            "route": map_profile["routeA"] if request.round == 1 else map_profile["route"],
        }

    def _refine(self, request: AgentRequest) -> dict[str, Any]:
        map_profile = request.context["map"]
        supply_draft = request.peers.get("supplyDraft", {})
        operator_draft = request.peers.get("operatorDraft", {})
        previous_audit = request.peers.get("previousAudit")
        draft = request.peers.get("riskDraft", {})

        raw_score = float(draft.get("rawScore", self._draft(request)["rawScore"]))
        smoke_count = int(supply_draft.get("smokeCount", 2))
        gap_seconds = int(operator_draft.get("gapSeconds", 18))
        smoke_coverage = 9 if smoke_count >= 4 else 0
        operator_delay = 3 if gap_seconds > 12 else 0
        previous_rework = 7 if previous_audit else 0
        score = round(_clamp(raw_score - smoke_coverage - previous_rework + operator_delay, 38, 94))
        level = "高" if score >= 78 else "中高" if score >= 62 else "中"
        route = draft.get("route") if request.round == 1 else map_profile["route"]

        return {
            "messageId": f"RSK-R{request.round}-01",
            "consumes": [
                map_profile["messageId"] if "messageId" in map_profile else f"INT-R{request.round}-01",
                f"SUP-DR-R{request.round}",
                f"OPS-DR-R{request.round}",
            ],
            "broadcasts": ["SUPPLY", "OPERATOR", "AUDIT"],
            "score": score,
            "level": level,
            "riskNodes": map_profile["riskNodes"],
            "warnings": [
                f"{node['name']}：{node['reason']}"
                for node in map_profile["riskNodes"]
            ],
            "route": route,
            "routeDecision": (
                f"{map_profile['riskNode']}风险过高，建议下一轮切换{map_profile['route']}"
                if request.round == 1
                else f"采纳地图备选路线并压缩{map_profile['riskNode']}停留时间"
            ),
            "decision": "缩短热点停留，采用两段式撤离" if score >= 72 else "沿外环推进，保持双向观察",
            "peerInput": [
                f"物资草稿提供烟雾{smoke_count}颗",
                f"干员草稿后卫延迟{gap_seconds}秒",
            ],
            "activity": f"风险指数{score}，已吸收物资与干员草稿完成复核",
        }
