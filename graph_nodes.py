"""
LangGraph 节点层 - MatchAnalysisState 定义 + 三个纯函数节点
使用方式: 单独测试或后续接入 graph.add_node
"""

from typing import TypedDict

# ===================== State 定义 =====================


class MatchAnalysisState(TypedDict, total=False):
    """全局状态 schema，所有节点共享读写"""

    team_a: str
    """主队名称"""

    team_b: str
    """客队名称"""

    raw_intel: dict
    """原始情报：包含两队战绩 + 赔率"""

    analysis_draft: str
    """分析草稿：战术推演初稿（纯文本）"""

    final_report: str
    """最终报告：Markdown 格式，可直接展示"""

    fetch_errors: int
    """抓取 API 错误计数，用于监控/告警"""


# ===================== 节点实现 =====================

def scout_node(state: MatchAnalysisState) -> dict:
    """
    球探节点：拉取两队原始数据，合并写入 state['raw_intel']
    """
    # 延迟导入避免顶层耦合，真实项目可提前到文件顶部
    from sports_data import fetch_team_stats, fetch_match_odds

    team_a: str = state["team_a"]
    team_b: str = state["team_b"]

    errors = 0
    raw_intel: dict = {}

    # 拉取主队数据
    try:
        raw_intel["team_a_stats"] = fetch_team_stats(team_a)
    except Exception as e:
        errors += 1
        raw_intel["team_a_stats"] = {"error": str(e)}

    # 拉取客队数据
    try:
        raw_intel["team_b_stats"] = fetch_team_stats(team_b)
    except Exception as e:
        errors += 1
        raw_intel["team_b_stats"] = {"error": str(e)}

    # 拉取赔率
    try:
        raw_intel["odds"] = fetch_match_odds(team_a, team_b)
    except Exception as e:
        errors += 1
        raw_intel["odds"] = {"error": str(e)}

    # 返回必须用 dict 格式，LangGraph 会自动合并到 state
    return {
        "raw_intel": raw_intel,
        "fetch_errors": state.get("fetch_errors", 0) + errors,
    }


def analyst_node(state: MatchAnalysisState) -> dict:
    """
    分析节点：调用 MiniMax 大模型读取情报，输出战术推演草稿
    """
    from llm_client import chat, build_analysis_prompt

    team_a = state["team_a"]
    team_b = state["team_b"]
    intel = state.get("raw_intel", {})

    a_stats = intel.get("team_a_stats", {})
    b_stats = intel.get("team_b_stats", {})

    # 如果有数据错误，返回降级文本
    if a_stats.get("error") or b_stats.get("error"):
        return {
            "analysis_draft": "【分析暂不可用】数据获取不完整，无法进行战术分析。建议稍后重试。"
        }

    try:
        prompt = build_analysis_prompt(team_a, team_b, a_stats, b_stats)
        draft = chat(prompt)
    except Exception as e:
        logging.warning(f"MiniMax LLM 调用失败: {e}，降级为规则分析")
        # 降级：使用简单规则公式
        a_wr = a_stats.get("win_rate", 0.0)
        b_wr = b_stats.get("win_rate", 0.0)
        a_injuries = a_stats.get("injuries", [])
        b_injuries = b_stats.get("injuries", [])
        a_name = a_stats.get("team_name", team_a)
        b_name = b_stats.get("team_name", team_b)
        draft = (
            f"【战术推演 · {a_name} vs {b_name}】（LLM 不可用，降级为规则分析）\n\n"
            f"■ 近期状态：{a_name} 胜率 {a_wr:.0%}，{b_name} 胜率 {b_wr:.0%}。\n"
            f"■ 关键伤停：{a_name}：{a_injuries[0] if a_injuries else '无'}；"
            f"{b_name}：{b_injuries[0] if b_injuries else '无'}。\n"
            f"■ 战术预测：基于数据模型，{a_name} {'状态更佳' if a_wr > b_wr else '状态相当'}，"
            f"{b_name} {'需注意防守' if b_wr < a_wr else '具有竞争力'}。"
        )

    return {"analysis_draft": draft}


def editor_node(state: MatchAnalysisState) -> dict:
    """
    主编节点：将分析草稿排版为标准 Markdown 报告
    """
    team_a = state["team_a"]
    team_b = state["team_b"]
    draft = state.get("analysis_draft", "")
    intel = state.get("raw_intel", {})
    odds = intel.get("odds", {})

    # 提取基础信息
    a_stats = intel.get("team_a_stats", {})
    b_stats = intel.get("team_b_stats", {})
    a_name = a_stats.get("team_name", team_a)
    b_name = b_stats.get("team_name", team_b)

    # 格式化为 Markdown
    report_lines = [
        f"# [足球] {a_name} vs {b_name} 比赛分析报告",
        "",
        f"> **联赛**：{a_stats.get('league', '未知')} vs {b_stats.get('league', '未知')}",
        f"> **时间**：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## 一、基础数据",
        "",
        f"| 指标 | {a_name} | {b_name} |",
        f"|------|------|------|",
        f"| 联赛 | {a_stats.get('league', '-')} | {b_stats.get('league', '-')} |",
        f"| 近5场胜率 | {a_stats.get('win_rate', 0):.0%} | {b_stats.get('win_rate', 0):.0%} |",
        f"| 场均进球 | {a_stats.get('avg_goals', 0):.1f} | {b_stats.get('avg_goals', 0):.1f} |",
        "",
        "## 二、伤停情况",
        "",
        f"**{a_name}**：{', '.join(a_stats.get('injuries', ['无']))}",
        f"**{b_name}**：{', '.join(b_stats.get('injuries', ['无']))}",
        "",
        "## 三、近期战绩",
        "",
        f"### {a_name}",
    ]

    # 主队近期战绩
    for m in a_stats.get("recent_matches", []):
        report_lines.append(f"- {m.get('date','?')} · {m.get('result','?')} vs {m.get('opponent','?')} · {m.get('score','?')}")

    report_lines.extend(["", f"### {b_name}"])

    for m in b_stats.get("recent_matches", []):
        report_lines.append(f"- {m.get('date','?')} · {m.get('result','?')} vs {m.get('opponent','?')} · {m.get('score','?')}")

    report_lines.extend(["", "## 四、战术推演", "", draft, "", "## 五、盘口数据", "",
        f"| 选项 | 赔率 |", "|------|------|",
        f"| 主胜 | {odds.get('home_win', '-')} |",
        f"| 平局 | {odds.get('draw', '-')} |",
        f"| 主负 | {odds.get('away_win', '-')} |",
        "",
        "---",
        "*本报告由 AI 自动生成，仅供参考*",
    ])

    return {"final_report": "\n".join(report_lines)}


# ===================== 独立测试入口 =====================

if __name__ == "__main__":
    print("=" * 60)
    print("LangGraph 节点独立测试")
    print("=" * 60)

    # 模拟一次完整流程
    state: MatchAnalysisState = {
        "team_a": "曼城",
        "team_b": "皇马",
        "raw_intel": {},
        "analysis_draft": "",
        "final_report": "",
        "fetch_errors": 0,
    }

    print("\n>>> Step 1: scout_node")
    update = scout_node(state)
    state.update(update)
    print(f"    fetch_errors={state['fetch_errors']}")
    print(f"    team_a_stats loaded: {'team_name' in state['raw_intel'].get('team_a_stats', {})}")

    print("\n>>> Step 2: analyst_node")
    update = analyst_node(state)
    state.update(update)
    print(f"    draft length: {len(state['analysis_draft'])} chars")

    print("\n>>> Step 3: editor_node")
    update = editor_node(state)
    state.update(update)
    print(f"    final_report length: {len(state['final_report'])} chars")
    print(f"\n{state['final_report']}")

    print("\n节点测试完成 OK")