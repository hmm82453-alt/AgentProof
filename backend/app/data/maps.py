from __future__ import annotations

from copy import deepcopy
from typing import Any


# Competition simulation data. Verify current extraction rules before the final event.
MAP_LIBRARY: dict[str, dict[str, Any]] = {
    "零号大坝": {
        "entry": "游客中心东侧",
        "routeA": "游客中心东侧 → 行政楼正门 → 西侧河岸",
        "route": "游客中心东侧 → 装卸区外沿 → 行政楼外环 → 西侧河岸",
        "extraction": "行政楼西侧撤离点",
        "altExtraction": "游客中心东侧撤离点",
        "hotspot": "行政楼、水泥厂、地下通道",
        "timing": "剩余 12:40 至 08:30",
        "intel": "行政楼正门存在持续观察位，装卸区外沿可以改走建筑背面。",
        "riskNode": "行政楼正门",
        "riskNodes": [
            {"name": "行政楼正门", "level": "极高", "reason": "二层窗口与外围道路形成交叉视线", "control": "禁止正面进入，改走装卸区外环"},
            {"name": "水泥厂北侧", "level": "中高", "reason": "厂房多个入口可能同时来敌", "control": "只做外沿搜索，停留不超过 40 秒"},
            {"name": "西侧河岸", "level": "中", "reason": "撤离前最后一段视野开阔", "control": "医疗支援位保留烟幕，侦察位持续观察后方"},
        ],
        "resources": [
            {"name": "行政楼", "items": "电子元件、情报资料、高价值保险容器", "value": "高", "risk": "极高", "dwell": "70 至 110 秒", "access": "后侧楼梯进入，避开正门"},
            {"name": "水泥厂", "items": "工业物资、工具、弹药", "value": "中高", "risk": "中高", "dwell": "50 至 80 秒", "access": "厂房外沿快速搜索"},
            {"name": "游客中心", "items": "医疗物资、生活物资、小型保险容器", "value": "中", "risk": "中低", "dwell": "60 至 90 秒", "access": "开局优先补给"},
            {"name": "主变电站", "items": "电子物资、设备零件", "value": "中高", "risk": "中", "dwell": "40 至 70 秒", "access": "建筑密集，适合短搜"},
            {"name": "地下通道", "items": "少量高价值容器", "value": "中", "risk": "高", "dwell": "仅通过", "access": "近距离遭遇概率高"},
        ],
        "exfils": [
            {"name": "行政楼西侧撤离点", "type": "常规撤离", "condition": "全员进入撤离区域并共同停留 8 秒", "risk": "中高", "note": "距离行政楼资源区最近"},
            {"name": "游客中心东侧撤离点", "type": "常规撤离", "condition": "全员进入撤离区域并共同停留 8 秒", "risk": "中低", "note": "适合提前撤离，但后期路线重合概率高"},
            {"name": "西侧河岸撤离点", "type": "团队撤离", "condition": "全员到场后开始倒计时，中途离场即中断", "risk": "中", "note": "可绕开行政楼正面，需要后卫观察"},
        ],
        "timeline": [
            {"time": "T+00:00", "point": "游客中心东侧", "action": "集合、核对医疗与弹药", "risk": "低"},
            {"time": "T+00:40", "point": "装卸区外沿", "action": "侦察位侦测，接敌位控制第一转折点", "risk": "中"},
            {"time": "T+01:25", "point": "行政楼外环", "action": "支援位释放第一段烟幕，避开正门", "risk": "中高"},
            {"time": "T+02:10", "point": "行政楼后侧", "action": "最多搜索 70 秒，只拿高价值小件", "risk": "高"},
            {"time": "T+02:45", "point": "西侧河岸", "action": "侦察位接管后卫，支援位保留最后一颗烟幕", "risk": "中"},
            {"time": "T+03:20", "point": "行政楼西侧", "action": "全员进入撤离区域并停留 8 秒", "risk": "中高"},
        ],
        "fallback": "行政楼发生高强度交火时放弃二层资源，改走地下通道南出口，并切换游客中心东侧撤离。",
    },
    "长弓溪谷": {
        "entry": "牧场南侧林线",
        "routeA": "牧场南侧林线 → 酒店正门 → 雷达站后侧",
        "route": "牧场南侧林线 → 溪谷北坡 → 雷达站后侧 → 酒店东南林线",
        "extraction": "酒店东南林间撤离点",
        "altExtraction": "码头接驳撤离点",
        "hotspot": "酒店、雷达站、码头",
        "timing": "剩余 14:20 至 09:10",
        "intel": "酒店高窗拥有持续观察位，北坡林线可以遮蔽中距离视线。",
        "riskNode": "酒店正门广场",
        "riskNodes": [
            {"name": "酒店正门广场", "level": "极高", "reason": "高窗、阳台与正面道路形成三层视线", "control": "走林线和酒店东南侧，不穿过广场"},
            {"name": "雷达站北坡", "level": "中高", "reason": "坡顶能观察北坡移动", "control": "沿林线阴影分散通过"},
            {"name": "码头栈桥", "level": "中高", "reason": "栈桥缺少遮蔽且容易形成堵点", "control": "只作为备用撤离，不进入长栈桥搜刮"},
        ],
        "resources": [
            {"name": "酒店", "items": "高价值房间、医疗物资、电子物品", "value": "高", "risk": "极高", "dwell": "60 至 120 秒", "access": "从东南后侧进入"},
            {"name": "雷达站", "items": "电子物资、情报资料、设备零件", "value": "高", "risk": "中高", "dwell": "50 至 80 秒", "access": "优先搜索后侧机房"},
            {"name": "码头", "items": "工业物资、补给箱", "value": "中", "risk": "中高", "dwell": "30 至 60 秒", "access": "避免停在栈桥中央"},
            {"name": "牧场", "items": "医疗物资、生活物资", "value": "中低", "risk": "低", "dwell": "30 至 50 秒", "access": "开局快速补给"},
        ],
        "exfils": [
            {"name": "酒店东南林间撤离点", "type": "团队撤离", "condition": "全员在树林区域集合并共同停留", "risk": "中", "note": "遮蔽较好，推荐主撤离"},
            {"name": "码头接驳撤离点", "type": "常规撤离", "condition": "进入接驳区域并等待撤离", "risk": "中高", "note": "栈桥暴露，适合备用"},
            {"name": "北侧林线撤离点", "type": "常规撤离", "condition": "全员进入林线边缘并共同停留", "risk": "中低", "note": "距离酒店资源区较远"},
        ],
        "timeline": [
            {"time": "T+00:00", "point": "牧场南侧", "action": "集合并分散观察", "risk": "低"},
            {"time": "T+00:35", "point": "溪谷北坡", "action": "侦察位侦测酒店窗口", "risk": "中"},
            {"time": "T+01:15", "point": "雷达站后侧", "action": "快速搜索电子物资", "risk": "中高"},
            {"time": "T+02:05", "point": "酒店东南后侧", "action": "支援位烟幕掩护，接敌位卡住楼梯", "risk": "高"},
            {"time": "T+03:00", "point": "酒店东南林线", "action": "全队集合撤离", "risk": "中"},
        ],
        "fallback": "酒店高窗持续锁定路线时放弃酒店房间，从北坡绕回北侧林线撤离。",
    },
    "巴克什": {
        "entry": "博物馆西南巷口",
        "routeA": "博物馆西南巷口 → 中央大厅 → 老城北门",
        "route": "西南巷区 → 博物馆后街 → 老城北门",
        "extraction": "老城北门接驳点",
        "altExtraction": "城区东侧车行撤离点",
        "hotspot": "博物馆、老城区、停车场",
        "timing": "剩余 11:50 至 07:40",
        "intel": "主街遭遇概率高，后街巷口可能形成双向夹击。",
        "riskNode": "博物馆中央大厅",
        "riskNodes": [
            {"name": "博物馆中央大厅", "level": "极高", "reason": "多个入口和多层回廊同时开放", "control": "只走馆后街，不进入中央大厅"},
            {"name": "老城西巷", "level": "高", "reason": "窄巷两端可能同时来敌", "control": "侦察位前探，队伍不在巷内停留"},
            {"name": "停车场入口", "level": "中高", "reason": "车辆与立柱遮挡视线", "control": "沿外墙通过，避免进入地下层"},
        ],
        "resources": [
            {"name": "博物馆", "items": "情报资料、高价值展柜、电子物品", "value": "极高", "risk": "极高", "dwell": "60 至 110 秒", "access": "从后街侧门短时进入"},
            {"name": "老城区", "items": "生活物资、医疗物资、民用保险箱", "value": "中", "risk": "高", "dwell": "40 至 80 秒", "access": "只搜索临街小屋"},
            {"name": "停车场", "items": "车辆配件、工具、电子物品", "value": "中高", "risk": "中高", "dwell": "40 至 70 秒", "access": "外场优先，谨慎进入地下"},
            {"name": "居民区", "items": "医疗物资、食物与小型保险箱", "value": "中低", "risk": "中", "dwell": "30 至 60 秒", "access": "适合作为路线补给点"},
        ],
        "exfils": [
            {"name": "老城北门接驳点", "type": "团队撤离", "condition": "全员进入北门区域并保持集合", "risk": "高", "note": "路线直接，但容易被堵截"},
            {"name": "城区东侧车行撤离点", "type": "条件撤离", "condition": "进入开放区域并完成撤离倒计时", "risk": "中", "note": "距离资源区较远，作为备用"},
            {"name": "博物馆外沿撤离点", "type": "常规撤离", "condition": "队伍抵达指定区域并等待撤离", "risk": "极高", "note": "不建议作为常规路线"},
        ],
        "timeline": [
            {"time": "T+00:00", "point": "博物馆西南巷口", "action": "确认后街入口没有双向威胁", "risk": "中"},
            {"time": "T+00:45", "point": "博物馆后街", "action": "侦察位侦测中央大厅侧门", "risk": "高"},
            {"time": "T+01:30", "point": "馆后资源层", "action": "短搜高价值小件，不进入大厅", "risk": "极高"},
            {"time": "T+02:20", "point": "老城西巷", "action": "接敌位先行，支援位烟幕隔断尾部视线", "risk": "高"},
            {"time": "T+03:00", "point": "老城北门", "action": "全队集合完成撤离", "risk": "高"},
        ],
        "fallback": "中央大厅发生交火时立即退出馆区，沿停车场外场绕过老城西巷，切换城区东侧撤离。",
    },
    "航天基地": {
        "entry": "南侧装卸区",
        "routeA": "南侧装卸区 → 核心区主通道 → 东侧围栏",
        "route": "南侧装卸区 → 试车场边缘 → 东侧围栏",
        "extraction": "试验场东侧撤离点",
        "altExtraction": "南侧地下通道撤离点",
        "hotspot": "核心区、装配车间、试车场",
        "timing": "剩余 13:10 至 08:50",
        "intel": "核心区视野开阔，沿试车场边缘移动能减少正面暴露。",
        "riskNode": "核心区主通道",
        "riskNodes": [
            {"name": "核心区主通道", "level": "极高", "reason": "通道长、掩体少、远距离火力覆盖充分", "control": "禁止横穿，沿试车场边缘绕行"},
            {"name": "装配车间", "level": "高", "reason": "内部多入口且设备遮挡严重", "control": "只在外侧观察，不深入搜索"},
            {"name": "东侧围栏", "level": "中高", "reason": "接近撤离点但暴露于长距离观察", "control": "支援位预留烟幕，队伍分散通过"},
        ],
        "resources": [
            {"name": "核心区", "items": "高价值电子设备、实验资料", "value": "极高", "risk": "极高", "dwell": "70 至 120 秒", "access": "必须由侦察位先行侦测"},
            {"name": "装配车间", "items": "工业物资、电子零件、工具", "value": "高", "risk": "高", "dwell": "50 至 90 秒", "access": "从侧面入口短搜"},
            {"name": "试车场", "items": "车辆物资、野外补给", "value": "中", "risk": "中高", "dwell": "30 至 50 秒", "access": "以移动路线为主"},
            {"name": "南侧装卸区", "items": "工业箱、弹药补给", "value": "中", "risk": "中", "dwell": "30 至 60 秒", "access": "开局快速搜索"},
        ],
        "exfils": [
            {"name": "试验场东侧撤离点", "type": "常规撤离", "condition": "队伍抵达围栏外撤离区域并等待", "risk": "中高", "note": "接近路线短，但视野暴露"},
            {"name": "南侧地下通道撤离点", "type": "条件撤离", "condition": "满足地图条件后进入通道完成撤离", "risk": "中高", "note": "可作为主撤离受阻时的绕行方案"},
            {"name": "南侧装卸区撤离点", "type": "团队撤离", "condition": "全员进入装卸区并共同停留", "risk": "中", "note": "距离起点近，资源收益低"},
        ],
        "timeline": [
            {"time": "T+00:00", "point": "南侧装卸区", "action": "快速补给并确认核心区方向", "risk": "中"},
            {"time": "T+00:40", "point": "试车场边缘", "action": "侦察位侦测核心区主通道", "risk": "中高"},
            {"time": "T+01:25", "point": "装配车间外沿", "action": "短搜电子零件，不深入内部", "risk": "高"},
            {"time": "T+02:15", "point": "核心区背侧", "action": "高价值目标停留不超过 70 秒", "risk": "极高"},
            {"time": "T+03:05", "point": "东侧围栏", "action": "烟幕掩护，全队分散进入撤离区", "risk": "中高"},
        ],
        "fallback": "主通道被远距离火力封锁时放弃核心区，沿试车场南侧退回地下通道撤离。",
    },
    "潮汐监狱": {
        "entry": "码头东侧排水渠",
        "routeA": "码头东侧排水渠 → 中央监区旋转楼梯 → 北侧海岸",
        "route": "排水渠 → 监区外廊 → 医务楼外侧 → 北侧海岸",
        "extraction": "北侧海岸撤离点",
        "altExtraction": "码头接驳撤离点",
        "hotspot": "中央监区、医务楼、地下层",
        "timing": "剩余 10:30 至 06:20",
        "intel": "监区内部转角密集，医务楼可以作为临时补给点。",
        "riskNode": "中央监区旋转楼梯",
        "riskNodes": [
            {"name": "中央监区旋转楼梯", "level": "极高", "reason": "上下层声音互通且转角视野短", "control": "侦察位前探，破障位负责近距突破"},
            {"name": "监区外廊", "level": "高", "reason": "长走廊容易被前后夹击", "control": "支援位烟幕分段通过"},
            {"name": "北侧海岸", "level": "中高", "reason": "撤离区域开阔，后方可能被追踪", "control": "侦察位最后进入，保留区域控制能力封锁追兵"},
        ],
        "resources": [
            {"name": "中央监区", "items": "情报资料、钥匙卡、高价值保险箱", "value": "高", "risk": "极高", "dwell": "60 至 100 秒", "access": "由破障位近距离突破"},
            {"name": "医务楼", "items": "医疗物资、药品、止血带", "value": "中高", "risk": "高", "dwell": "40 至 70 秒", "access": "路线中段补给"},
            {"name": "地下层", "items": "电子设备、受限区域物资", "value": "高", "risk": "极高", "dwell": "仅快速通过", "access": "需要侦测和烟幕同时覆盖"},
            {"name": "码头", "items": "工业物资、补给箱", "value": "中", "risk": "中高", "dwell": "30 至 50 秒", "access": "作为备用撤离区"},
        ],
        "exfils": [
            {"name": "北侧海岸撤离点", "type": "团队撤离", "condition": "全员抵达海岸并共同停留，途中离队会中断", "risk": "中高", "note": "距离医务楼较近，推荐主撤离"},
            {"name": "码头接驳撤离点", "type": "常规撤离", "condition": "进入码头指定区域并等待撤离", "risk": "高", "note": "路线长，容易被从后方追踪"},
            {"name": "排水渠撤离点", "type": "条件撤离", "condition": "进入排水系统并完成撤离倒计时", "risk": "高", "note": "近距离遭遇概率最高"},
        ],
        "timeline": [
            {"time": "T+00:00", "point": "码头东侧排水渠", "action": "检查医疗并确认近战分工", "risk": "中"},
            {"time": "T+00:35", "point": "监区外廊", "action": "侦察位前探，支援位准备第一段烟幕", "risk": "高"},
            {"time": "T+01:15", "point": "中央监区", "action": "破障位突破楼梯，快速拿取高价值目标", "risk": "极高"},
            {"time": "T+02:00", "point": "医务楼外侧", "action": "补充医疗但不在楼内久留", "risk": "中高"},
            {"time": "T+02:45", "point": "北侧海岸", "action": "侦察位最后进入，全队开始撤离", "risk": "中高"},
        ],
        "fallback": "中央楼梯被封锁时放弃监区内部资源，从外廊直接转医务楼外侧，切换码头接驳撤离。",
    },
}


GAME_MODES: dict[str, dict[str, str]] = {
    "normal": {
        "id": "normal",
        "name": "普通烽火",
        "description": "常规烽火地带行动，数据以当前对局界面为准。",
    },
    "confidential": {
        "id": "confidential",
        "name": "机密行动",
        "description": "高风险烽火地带行动，撤离规则可能独立配置。",
    },
    "top_secret": {
        "id": "top_secret",
        "name": "绝密行动",
        "description": "当前版本最高风险行动，撤离限制必须按赛季核对。",
    },
}


# Publicly visible guide names that have been checked more recently than the
# original scaffold. Conditions remain partial unless the in-game panel confirms
# them. This prevents DeepSeek from inventing exact extraction rules.
MAP_VERIFICATION: dict[str, dict[str, Any]] = {
    "零号大坝": {
        "knownExfils": [
            {"name": "大坝常规撤离点", "type": "常规撤离", "condition": "进入撤离区域并等待倒计时，具体限制待实机确认", "risk": "中高", "note": "公开攻略确认名称"},
            {"name": "西撤离点", "type": "常规撤离", "condition": "全员抵达西侧撤离区域，具体停留时间待实机确认", "risk": "中高", "note": "公开攻略确认名称"},
            {"name": "拉闸撤离点", "type": "条件撤离", "condition": "完成地图拉闸流程后开放，拉闸位置与窗口待实机确认", "risk": "高", "note": "公开攻略确认名称"},
            {"name": "电梯撤离点", "type": "条件撤离", "condition": "电梯开放后使用，开放条件待实机确认", "risk": "高", "note": "公开攻略确认名称"},
            {"name": "游客中心撤离点", "type": "常规撤离", "condition": "抵达游客中心撤离区域，具体限制待实机确认", "risk": "中", "note": "公开攻略确认名称"},
        ],
        "reportedTotalExits": 8,
        "sources": ["https://www.bilibili.com/video/BV1wZ8x6sEdM"],
        "status": "partial",
    },
    "长弓溪谷": {
        "knownExfils": [
            {"name": "峡间撤离点", "type": "常规撤离", "condition": "进入峡间撤离区域，具体限制待实机确认", "risk": "中高", "note": "公开攻略确认名称"},
            {"name": "村庄撤离点", "type": "常规撤离", "condition": "进入村庄撤离区域，具体限制待实机确认", "risk": "中", "note": "公开攻略确认名称"},
            {"name": "车站撤离点", "type": "常规撤离", "condition": "进入车站撤离区域，具体限制待实机确认", "risk": "中高", "note": "公开攻略确认名称"},
            {"name": "蓝港码头", "type": "团队撤离", "condition": "抵达蓝港码头撤离区域，具体停留和人数规则待实机确认", "risk": "中高", "note": "公开攻略确认名称"},
        ],
        "reportedTotalExits": None,
        "sources": [
            "https://www.bilibili.com/video/BV1U31HBWExk",
            "https://www.bilibili.com/video/BV1CLcUz8EiD",
        ],
        "status": "partial",
    },
    "巴克什": {
        "knownExfils": [
            {"name": "塔前撤离点", "type": "常规撤离", "condition": "进入塔前撤离区域，具体限制待实机确认", "risk": "高", "note": "公开攻略确认名称"},
            {"name": "随机撤离点", "type": "随机撤离", "condition": "仅在对局随机出现时可用，不能作为唯一撤离方案", "risk": "高", "note": "随机机制公开确认"},
        ],
        "reportedTotalExits": None,
        "sources": [
            "https://www.bilibili.com/video/BV1mSMv6NE2R",
            "https://www.bilibili.com/video/BV1pJdDYtEuW",
        ],
        "status": "needs_review",
    },
    "航天基地": {
        "knownExfils": [
            {"name": "老太撤离点", "type": "条件撤离", "condition": "与地图首领或特殊事件相关，具体开放条件待实机确认", "risk": "高", "note": "公开攻略确认名称"},
            {"name": "直升机撤离点", "type": "条件撤离", "condition": "需要完成拉闸或呼叫流程，具体步骤待实机确认", "risk": "高", "note": "公开攻略确认名称"},
            {"name": "东区吊桥撤离点", "type": "条件撤离", "condition": "吊桥相关撤离路线，具体开放条件待实机确认", "risk": "极高", "note": "点位名称来自公开攻略"},
        ],
        "reportedTotalExits": 3,
        "sources": [
            "https://www.bilibili.com/video/BV1PX2sYqE4g",
            "https://www.bilibili.com/video/BV1BCJS6REtv",
            "https://www.bilibili.com/video/BV1ubhNzoEgm",
        ],
        "status": "partial",
    },
    "潮汐监狱": {
        "knownExfils": [
            {"name": "拉闸撤离点1", "type": "条件撤离", "condition": "完成拉闸流程后开放，具体拉闸位置待实机确认", "risk": "高", "note": "公开攻略画面确认名称"},
            {"name": "拉闸撤离点2", "type": "条件撤离", "condition": "完成拉闸流程后开放，具体拉闸位置待实机确认", "risk": "高", "note": "公开攻略画面确认名称"},
            {"name": "拉闸撤离点3", "type": "条件撤离", "condition": "完成拉闸流程后开放，具体拉闸位置待实机确认", "risk": "高", "note": "公开攻略画面确认名称"},
            {"name": "管道撤离点1", "type": "条件撤离", "condition": "进入管道撤离路线并完成倒计时，具体限制待实机确认", "risk": "极高", "note": "公开攻略画面确认名称"},
            {"name": "管道撤离点2", "type": "条件撤离", "condition": "进入管道撤离路线并完成倒计时，具体限制待实机确认", "risk": "极高", "note": "公开攻略画面确认名称"},
            {"name": "管道撤离点3", "type": "条件撤离", "condition": "进入管道撤离路线并完成倒计时，具体限制待实机确认", "risk": "极高", "note": "公开攻略画面确认名称"},
        ],
        "reportedTotalExits": None,
        "sources": ["https://www.bilibili.com/video/BV1uzUCBxEPw"],
        "status": "partial",
    },
}


def get_map_profile(name: str, game_mode: str = "normal") -> dict[str, Any]:
    profile = MAP_LIBRARY.get(name, MAP_LIBRARY["零号大坝"])
    profile = deepcopy(profile)
    verification = MAP_VERIFICATION.get(name, {})
    profile["gameMode"] = game_mode
    profile["gameModeName"] = GAME_MODES.get(game_mode, GAME_MODES["normal"])["name"]
    profile["exfils"] = deepcopy(verification.get("knownExfils", profile["exfils"]))
    profile["extraction"] = profile["exfils"][0]["name"]
    profile["altExtraction"] = (
        profile["exfils"][1]["name"]
        if len(profile["exfils"]) > 1
        else profile["exfils"][0]["name"]
    )
    profile["reportedTotalExits"] = verification.get("reportedTotalExits")
    profile["sources"] = verification.get("sources", [])
    profile["verificationStatus"] = verification.get("status", "needs_review")
    profile["dataVersion"] = "2026-11-16-public-guides"
    profile["verificationNote"] = (
        "已核对公开攻略中出现的点位名称；具体开放条件仍以当前对局界面为准。"
        if profile["verificationStatus"] == "partial"
        else "点位或条件资料不完整，必须实机确认后才能作为比赛正式数据。"
    )
    for resource in profile.get("resources", []):
        resource["verificationStatus"] = "needs_review"
    return profile
