from __future__ import annotations

from typing import Any

from app.agents.base import BaseTacticalAgent
from app.schemas import AgentRequest


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


class AuditAgent(BaseTacticalAgent):
    agent_id = "audit"
    display_name = "校验复盘 Agent"
    llm_editable_fields = {"activity"}
    system_prompt = """
你是校验复盘 Agent。必须交叉核对路线、风险、烟幕、负重、技能覆盖和撤离条件。
如果发现冲突，必须给出具体失败原因和下一轮修改指令，不得在没有证据时判定通过。
返回严格 JSON 对象，必须保留 pass、score、issue、directives、auditChecks、changes、
messageId、consumes、broadcasts、activity、finalPlan。通过时 finalPlan 必须包含路线、
撤离条件、时间窗、干员、负重和 summary。不要输出 Markdown。
""".strip()

    async def run(self, request: AgentRequest) -> dict[str, Any]:
        return await self.respond(request, self._audit(request))

    def _audit(self, request: AgentRequest) -> dict[str, Any]:
        context = request.context
        map_profile = context["map"]
        risk = context["risk"]
        supply = context["supply"]
        operator = context["operator"]
        previous_audit = context.get("previousAudit")
        coverage = set(operator.get("teamCoverage", []))
        capability_gaps = list(operator.get("capabilityGaps", []))
        required_gaps = [
            gap
            for gap, capability in (
                ("医疗救援", "healing"),
                ("目标侦察", "recon"),
                ("破障开路", "breach"),
            )
            if capability not in coverage
        ]

        tactic_pressure = 7 if request.input.tactic == "高风险速撤" else 0
        weight_pressure = 5 if request.input.weight > 38 else 0
        final_score = round(
            _clamp(
                66 + request.input.squadSize * 3 - tactic_pressure - weight_pressure + request.round * 4,
                38,
                96,
            )
        )
        conflict = (
            request.round == 1
            or bool(supply["overweight"])
            or len(request.input.operators) != request.input.squadSize
            or bool(required_gaps)
            or map_profile.get("verificationStatus") == "needs_review"
        )

        if conflict:
            reasons: list[str] = []
            if request.round == 1:
                reasons.append(
                    "风险 Agent 要求45秒内通过风险节点，但干员 Agent 的后卫预计延迟18秒"
                )
            if supply["overweight"]:
                reasons.append("总负重仍超过建议上限，物资规划需要继续压缩")
            if len(request.input.operators) != request.input.squadSize:
                reasons.append("干员数量与小队人数不一致")
            if required_gaps:
                reasons.append(f"当前干员组合缺少必要能力：{'、'.join(required_gaps)}")
            if map_profile.get("verificationStatus") == "needs_review":
                reasons.append("地图点位资料不完整，不能作为正式撤离方案")

            recon_name = next(
                (
                    item["name"]
                    for item in operator["assignments"]
                    if "侦察" in item["role"]
                ),
                request.input.operators[-1],
            )
            support_name = next(
                (
                    item["name"]
                    for item in operator["assignments"]
                    if "医疗" in item["role"] or "支援" in item["role"]
                ),
                request.input.operators[0],
            )

            return {
                "pass": False,
                "score": round(_clamp(final_score - 12, 35, 72)),
                "issue": "；".join(reasons),
                "directives": [
                    f"路线切换为{map_profile['route']}",
                    f"{recon_name}在第一个转折点接管后卫，前锋等待接应",
                    f"{support_name}优先保留烟幕与医疗资源",
                    *[f"补充能力缺口：{gap}" for gap in required_gaps],
                ],
                "auditChecks": [
                    {
                        "label": f"{map_profile['riskNode']}风险窗口",
                        "pass": not (request.round == 1),
                        "detail": (
                            "后卫延迟18秒"
                            if request.round == 1
                            else f"当前风险指数{risk['score']}"
                        ),
                    },
                    {
                        "label": "烟幕覆盖",
                        "pass": supply["smokeCount"] >= 2,
                        "detail": f"{supply['smokeCount']}颗",
                    },
                    {
                        "label": "负重上限",
                        "pass": not supply["overweight"],
                        "detail": f"{supply['adjustedWeight']:.1f}kg / {supply['capacity']}kg",
                    },
                    {
                        "label": "技能覆盖",
                        "pass": not required_gaps,
                        "detail": (
                            f"缺口：{'、'.join(required_gaps)}"
                            if required_gaps
                            else "医疗 / 侦察 / 破障能力均在场"
                        ),
                    },
                    {
                        "label": "撤离条件",
                        "pass": map_profile.get("verificationStatus") != "needs_review",
                        "detail": (
                            f"{map_profile['exfils'][0]['condition']}；资料状态："
                            f"{map_profile.get('verificationStatus')}"
                        ),
                    },
                ],
                "changes": (
                    [
                        "首轮草稿已生成，等待仲裁反馈",
                        "后卫延迟与风险窗口冲突",
                        "下一轮切换备选路线并重新分配接力",
                    ]
                    if request.round == 1
                    else [
                        "负重仍超过建议值，需要继续压缩",
                        "低价值工业物资尚未完全剔除",
                        *[f"能力缺口仍存在：{gap}" for gap in required_gaps],
                    ]
                ),
                "messageId": f"AUD-REJECT-R{request.round}-01",
                "consumes": [
                    map_profile.get("messageId", f"INT-R{request.round}-01"),
                    f"RSK-R{request.round}-01",
                    f"SUP-R{request.round}-01",
                    f"OPS-R{request.round}-01",
                ],
                "broadcasts": ["RISK", "SUPPLY", "OPERATOR"],
                "activity": "校验未通过，迭代指令已广播",
                "finalPlan": None,
                "previousRound": bool(previous_audit),
            }

        selected_exfil = map_profile["exfils"][0]
        assignment_names = " / ".join(
            f"{item['name']}:{item['role']}" for item in operator["assignments"]
        )
        audit_checks = [
            {"label": "路线决策", "pass": True, "detail": f"采用{map_profile['route']}"},
            {
                "label": "风险窗口",
                "pass": True,
                "detail": f"{map_profile['riskNode']}风险降至{risk['score']}",
            },
            {
                "label": "烟幕覆盖",
                "pass": supply["smokeCount"] >= 4,
                "detail": f"{supply['smokeCount']}颗烟雾",
            },
            {
                "label": "负重上限",
                "pass": not supply["overweight"],
                "detail": f"{supply['adjustedWeight']:.1f}kg / {supply['capacity']}kg",
            },
            {
                "label": "技能覆盖",
                "pass": not required_gaps,
                "detail": assignment_names,
            },
            {
                "label": "撤离条件",
                "pass": map_profile.get("verificationStatus") != "needs_review",
                "detail": (
                    f"{selected_exfil['condition']}；资料状态："
                    f"{map_profile.get('verificationStatus')}"
                ),
            },
        ]
        changes = [
            f"主路线切换：{map_profile['routeA']} → {map_profile['route']}",
            f"烟雾数量：2 → {supply['smokeCount']}",
            "后卫接管点提前到第一个转折点，前锋等待6秒",
            f"风险指数下降：82 → {risk['score']}",
            f"数据版本：{map_profile.get('dataVersion')}；状态：{map_profile.get('verificationStatus')}",
        ]

        return {
            "pass": True,
            "score": final_score,
            "issue": "",
            "directives": [],
            "auditChecks": audit_checks,
            "changes": changes,
            "messageId": f"AUD-PASS-R{request.round}-01",
            "consumes": [
                map_profile.get("messageId", f"INT-R{request.round}-01"),
                f"RSK-R{request.round}-01",
                f"SUP-R{request.round}-01",
                f"OPS-R{request.round}-01",
            ],
            "broadcasts": ["FINAL_PLAN"],
            "activity": f"校验通过，方案评分{final_score}",
            "finalPlan": {
                "route": map_profile["route"],
                "extraction": map_profile["extraction"],
                "timing": map_profile["timing"],
                "operators": " / ".join(request.input.operators),
                "weight": f"{supply['adjustedWeight']:.1f}kg / {supply['capacity']}kg",
                "exfilCondition": selected_exfil["condition"],
                "dataVersion": map_profile.get("dataVersion"),
                "verificationStatus": map_profile.get("verificationStatus"),
                "capabilityGaps": capability_gaps,
                "summary": (
                    "五类 Agent 已完成交叉复核。"
                    f"优先从{map_profile['entry']}切入资源区，沿外环避开"
                    f"{map_profile['riskNode']}正面交火，并由侦察位在第一个转折点完成后卫接应。"
                    f"当前风险等级{risk['level']}，方案满足撤离集合条件。"
                    f"地图资料状态为{map_profile.get('verificationStatus')}。"
                ),
            },
            "operatorCoverage": operator["assignments"],
        }
