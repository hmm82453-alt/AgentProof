from __future__ import annotations

from typing import Any

from app.agents.base import BaseTacticalAgent
from app.data.operators import get_operator_profile
from app.schemas import AgentRequest


class OperatorAgent(BaseTacticalAgent):
    agent_id = "operator"
    display_name = "干员协同 Agent"
    llm_editable_fields = {"formation", "activity"}
    system_prompt = """
你是撤离任务的干员协同 Agent。必须从完整干员图鉴读取用户选择的所有干员，
根据技能标签动态分配职责，不得把红狼、蜂医或露娜写死为唯一角色。
如果某名干员的技能资料标记为 needs_review，只能陈述待核验事实，不得补造持续时间或数值。
返回严格 JSON 对象，必须保留 messageId、consumes、broadcasts、assignments、
formation、relayRule、gapSeconds、smokeUser、teamCoverage、capabilityGaps、
peerInput、activity。不要输出 Markdown。
""".strip()

    async def run(self, request: AgentRequest) -> dict[str, Any]:
        if request.phase == "draft":
            return self._draft(request)
        return await self.respond(request, self._refine(request))

    def _draft(self, request: AgentRequest) -> dict[str, Any]:
        profiles = [get_operator_profile(name) for name in request.input.operators]
        coverage = sorted(
            {
                capability
                for profile in profiles
                for capability in profile["capabilities"]
            }
        )
        smoke_user = next(
            (
                profile["name"]
                for profile in profiles
                if "smoke" in profile["capabilities"]
            ),
            None,
        )
        return {
            "draft": True,
            "messageId": f"OPS-DR-R{request.round}",
            "profiles": profiles,
            "teamCoverage": coverage,
            "smokeUser": smoke_user or "无专职烟幕位",
            "gapSeconds": 18 if request.round == 1 else 6,
        }

    def _role_for(self, profile: dict[str, Any], index: int) -> str:
        capabilities = set(profile["capabilities"])
        if "healing" in capabilities or "revive" in capabilities:
            return "医疗支援位"
        if "recon" in capabilities or "detection" in capabilities:
            return "侦察与后卫位"
        if "breach" in capabilities or "shield" in capabilities:
            return "破障突入位"
        if "area_denial" in capabilities or "fortification" in capabilities:
            return "区域控制位"
        if "assault" in capabilities:
            return "第一接敌位"
        if "mobility" in capabilities or "flank" in capabilities:
            return "机动接应位"
        return f"战术协同位 {index + 1}"

    def _task_for(
        self,
        profile: dict[str, Any],
        role: str,
        risk_node: str,
        smoke_count: int,
    ) -> str:
        capabilities = set(profile["capabilities"])
        if "healing" in capabilities:
            return f"负责队伍治疗和倒地救援，并携带 {smoke_count} 颗烟幕中的支援部分"
        if "recon" in capabilities or "detection" in capabilities:
            return f"进入 {risk_node} 前完成侦测，撤离阶段负责后方观察"
        if "breach" in capabilities or "shield" in capabilities:
            return f"从正面打开 {risk_node} 入口，突破后立即让出通道"
        if "area_denial" in capabilities or "indirect_fire" in capabilities:
            return "封锁敌方绕后或撤离点入口，避免范围火力覆盖队友"
        if "assault" in capabilities:
            return f"承担{role}，控制风险节点外侧火力窗口"
        return profile["task"]

    def _refine(self, request: AgentRequest) -> dict[str, Any]:
        map_profile = request.context["map"]
        risk_draft = request.peers.get("riskDraft", {})
        supply_draft = request.peers.get("supplyDraft", {})
        previous_audit = request.peers.get("previousAudit")
        draft = request.peers.get("operatorDraft", self._draft(request))

        gap_seconds = 0 if previous_audit else int(draft["gapSeconds"])
        coverage = {
            capability
            for profile in draft["profiles"]
            for capability in profile["capabilities"]
        }
        smoke_count = int(supply_draft.get("smokeCount", 2))
        risk_node = map_profile["riskNode"]
        assignments = []

        for index, profile in enumerate(draft["profiles"]):
            role = self._role_for(profile, index)
            assignments.append(
                {
                    "id": profile["id"],
                    "name": profile["name"],
                    "className": profile["className"],
                    "role": role,
                    "abilities": profile["abilities"],
                    "contribution": profile["contribution"],
                    "task": self._task_for(profile, role, risk_node, smoke_count),
                    "limitation": profile["limitation"],
                    "carryRule": profile["carryRule"],
                    "verificationStatus": profile["verificationStatus"],
                }
            )

        ordered_roles = "、".join(
            f"{assignment['name']}负责{assignment['role']}"
            for assignment in assignments
        )
        formation = (
            f"按能力顺序展开：{ordered_roles}。"
            + (
                "队伍具备烟幕能力，采用两段式遮蔽。"
                if "smoke" in coverage
                else "队伍缺少专职烟幕能力，改用投掷物和硬掩体控制通行窗口。"
            )
        )
        relay_rule = (
            "先锋通过第一个转折点后等待接应位进入有效支援范围，再继续推进"
            if gap_seconds == 0
            else "接应位预计延迟18秒抵达转折点，当前队形与风险窗口不兼容"
        )
        gaps = [
            label
            for label, capability in (
                ("医疗救援", "healing"),
                ("目标侦察", "recon"),
                ("烟幕遮蔽", "smoke"),
                ("破障开路", "breach"),
            )
            if capability not in coverage
        ]

        return {
            "messageId": f"OPS-R{request.round}-01",
            "consumes": [
                map_profile.get("messageId", f"INT-R{request.round}-01"),
                f"RSK-DR-R{request.round}",
                f"SUP-DR-R{request.round}",
            ],
            "broadcasts": ["RISK", "SUPPLY", "AUDIT"],
            "assignments": assignments,
            "formation": formation,
            "relayRule": relay_rule,
            "gapSeconds": gap_seconds,
            "smokeUser": draft["smokeUser"],
            "teamCoverage": sorted(coverage),
            "capabilityGaps": gaps,
            "peerInput": [
                f"采用风险草稿 {risk_draft.get('rawScore')}",
                f"采用物资草稿的烟雾数量 {supply_draft.get('smokeCount')}",
            ],
            "activity": (
                f"完成{len(assignments)}人动态分工，"
                + (f"能力缺口：{'、'.join(gaps)}" if gaps else "队伍能力覆盖完整")
            ),
        }
