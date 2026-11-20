from __future__ import annotations

from typing import Any

from app.agents.base import BaseTacticalAgent
from app.data.maps import get_map_profile
from app.schemas import AgentRequest


class MapIntelAgent(BaseTacticalAgent):
    agent_id = "map"
    display_name = "地图情报 Agent"
    llm_editable_fields = {"intel", "activity"}
    system_prompt = """
你是《三角洲行动》撤离任务的地图情报 Agent。
只依据请求中的 grounded_result 和地图事实，不得虚构当前游戏版本不存在的资源点或撤离条件。
必须明确区分已确认点位和待实机核验条件，不得把待核验内容写成确定事实。
返回严格 JSON 对象，必须保留 messageId、resources、exfils、timeline、riskNodes、fallback、
consumes、broadcasts、activity 字段。资源点必须包含 items、value、risk、dwell、access；
撤离点必须包含 type、condition、risk、note。不要输出 Markdown。
""".strip()

    async def run(self, request: AgentRequest) -> dict[str, Any]:
        profile = get_map_profile(request.input.map, request.input.gameMode)
        message_id = f"INT-R{request.round}-01"
        grounded_result = {
            **profile,
            "messageId": message_id,
            "consumes": ["任务参数"],
            "broadcasts": ["RISK", "SUPPLY", "OPERATOR"],
            "activity": (
                f"{profile['gameModeName']}情报已载入；"
                f"{len(profile['exfils'])} 个公开攻略点位，状态 {profile['verificationStatus']}"
            ),
        }
        return await self.respond(request, grounded_result)
