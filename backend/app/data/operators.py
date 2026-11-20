from __future__ import annotations

from typing import Any


CATALOG_VERSION = "2026-11-16"
ROSTER_SOURCE = "https://www.bilibili.com/video/BV18GNwzDEeW"


def _operator(
    name: str,
    operator_class: str,
    capabilities: list[str],
    abilities: list[str],
    planning_value: str,
    limitation: str,
    *,
    verification: str = "community_roster",
) -> dict[str, Any]:
    return {
        "id": name,
        "name": name,
        "className": operator_class,
        "role": operator_class,
        "capabilities": capabilities,
        "abilities": abilities,
        "contribution": planning_value,
        "planningValue": planning_value,
        "task": "由干员协同 Agent 根据队伍能力覆盖动态分配",
        "limitation": limitation,
        "carryRule": "根据能力覆盖和负重上限动态分配",
        "verificationStatus": verification,
        "verifiedAt": CATALOG_VERSION,
        "source": ROSTER_SOURCE,
    }


OPERATOR_PROFILES: dict[str, dict[str, Any]] = {
    "红狼": _operator(
        "红狼",
        "突击",
        ["mobility", "assault", "explosive", "breach"],
        ["动力外骨骼", "战术滑铲", "三联装手炮"],
        "缩短暴露区通过时间，并提供爆发火力与快速转点能力",
        "行动噪声较高，容易吸引附近队伍",
    ),
    "威龙": _operator(
        "威龙",
        "突击",
        ["mobility", "vertical", "assault", "explosive"],
        ["动力推进", "磁吸炸弹", "爆炸伤害抗性"],
        "提供垂直机动、快速压点和爆破突破能力",
        "空中机动过程容易暴露，需要队友提供观察",
    ),
    "无名": _operator(
        "无名",
        "突击",
        ["assault", "area_denial", "information_disruption"],
        ["突击型战术装备", "区域干扰"],
        "用于压缩敌方信息并制造正面突破窗口",
        "具体持续时间与作用范围需要在当前赛季实机核对",
        verification="needs_review",
    ),
    "张姐": _operator(
        "张姐",
        "突击",
        ["assault", "sustain", "frontline"],
        ["突击型战术装备"],
        "适合承担正面交火和队伍推进职责",
        "公开资料未完整确认技能数值，比赛数据需实机核对",
        verification="needs_review",
    ),
    "疾风": _operator(
        "疾风",
        "突击",
        ["assault", "mobility", "frontline"],
        ["高速突击型战术装备"],
        "适合快速切入、追击和转移",
        "需要确认当前赛季技能名称、持续时间和冷却",
        verification="needs_review",
    ),
    "野火": _operator(
        "野火",
        "突击",
        ["breach", "shield", "assault", "knockdown", "explosive"],
        ["盾式破障器", "正面防弹冲刺", "范围重击"],
        "可正面突破危险入口，并通过冲刺重击制造击倒",
        "冲刺方向受限，需要队伍保护侧翼",
        verification="official_announcement",
    ),
    "蜂医": _operator(
        "蜂医",
        "支援",
        ["healing", "revive", "smoke", "sustain"],
        ["远程治疗", "烟幕掩护", "倒地救援"],
        "维持队伍续航，并在危险路段制造烟幕通道",
        "需要保留医疗与烟幕资源，不适合独立前探",
    ),
    "蛊": _operator(
        "蛊",
        "支援",
        ["area_control", "debilitation", "support"],
        ["区域控制型战术装备"],
        "用于限制敌方推进和封锁交火区域",
        "当前公开资料中的技能持续时间和作用范围需实机确认",
        verification="needs_review",
    ),
    "蝶": _operator(
        "蝶",
        "支援",
        ["support", "recon_support", "team_utility"],
        ["团队支援型战术装备"],
        "用于补充队伍信息或辅助能力",
        "具体技能效果需在当前赛季实机核对",
        verification="needs_review",
    ),
    "牧羊人": _operator(
        "牧羊人",
        "工程",
        ["area_denial", "trap", "anti_rush"],
        ["声波陷阱", "区域压制装备"],
        "适合保护撤离点入口、后门和狭窄通道",
        "需要提前布置，无法完全替代正面火力",
    ),
    "乌鲁鲁": _operator(
        "乌鲁鲁",
        "工程",
        ["area_denial", "indirect_fire", "explosive"],
        ["燃烧型区域火力", "重型工程装备"],
        "可封锁开阔区、撤离点和敌方绕后路线",
        "范围火力可能暴露位置，并影响队友通行",
    ),
    "深蓝": _operator(
        "深蓝",
        "工程",
        ["fortification", "protection", "area_control"],
        ["工程防御型战术装备"],
        "适合保护队伍正面或临时封锁危险入口",
        "具体部署限制和耐久需在实机中核对",
        verification="needs_review",
    ),
    "比特": _operator(
        "比特",
        "工程",
        ["deployable", "utility", "area_control"],
        ["工程无人设备"],
        "用于侦察、干扰或区域控制",
        "当前公开资料不完整，技能参数必须核对",
        verification="needs_review",
    ),
    "露娜": _operator(
        "露娜",
        "侦察",
        ["recon", "detection", "area_denial", "rear_guard"],
        ["侦测箭", "电击箭", "区域预警"],
        "提前发现窗口和转角目标，并阻断敌方追击",
        "侦察存在范围和时机限制，需要前锋等待接应",
    ),
    "麦晓雯": _operator(
        "麦晓雯",
        "侦察",
        ["recon", "stealth", "information_gathering", "flank"],
        ["数据入侵", "静默移动", "诱饵或信息干扰"],
        "适合隐蔽侦察、绕后和获取敌方信息",
        "需要确认当前赛季技能形态和持续时间",
    ),
    "银翼": _operator(
        "银翼",
        "侦察",
        ["recon", "long_range_detection", "marking"],
        ["远程侦察型战术装备"],
        "适合远距离观察和标记撤离路线威胁",
        "近距离自保能力有限，需要队友掩护",
    ),
}


def get_operator_profile(name: str) -> dict[str, Any]:
    profile = OPERATOR_PROFILES.get(name)
    if profile is not None:
        return profile
    raise KeyError(f"operator is not in the current catalog: {name}")


def get_catalog_metadata() -> dict[str, Any]:
    classes: dict[str, int] = {}
    for profile in OPERATOR_PROFILES.values():
        classes[profile["className"]] = classes.get(profile["className"], 0) + 1
    return {
        "version": CATALOG_VERSION,
        "source": ROSTER_SOURCE,
        "count": len(OPERATOR_PROFILES),
        "classes": classes,
        "needsReview": sum(
            profile["verificationStatus"] == "needs_review"
            for profile in OPERATOR_PROFILES.values()
        ),
    }
