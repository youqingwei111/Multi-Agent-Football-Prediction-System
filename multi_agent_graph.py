"""
Multi-Agent 架构 - 四个独立 Agent 流水线执行
Agent1(球探) → Agent2(Retriever) → Agent3(分析师) → Agent4(主编)
流水线模式：上一个 Agent 的输出直接作为下一个 Agent 的输入
每个 Agent 是独立的 LLM 调用，无共享状态
"""

import logging
from dotenv import load_dotenv
load_dotenv()

from typing import TypedDict, Optional

from sports_data import fetch_team_stats, fetch_match_odds
from llm_client import chat
from rag_ingestion import save_graph_snapshot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================== 共享 State =====================


class MatchAnalysisState(TypedDict, total=False):
    team_a: str
    team_b: str
    scout_report: str           # Agent1 输出：原始情报摘要
    historical_knowledge: Optional[str]  # Agent2 输出：RAG 检索的历史知识（阶段 2）
    analysis_draft: str         # Agent3 输出：战术分析长文
    final_report: str          # Agent4 输出：Markdown 报告
    fetch_errors: int          # 数据抓取错误计数


# ===================== Prompts =====================

SCOUT_PROMPT = """你是一个顶级足球球探，专门负责收集球队基础情报。

你的任务：
请使用你的工具（get_team_stats 和 get_match_odds）来收集{team_a}和{team_b}两支球队的详细数据。
已知的工具信息如下：
- get_team_stats(team_name): 获取球队近期战绩、伤病等数据
- get_match_odds(team_a, team_b): 获取两队交手的赔率

请调用这两个工具，收集完整数据后整理成一段结构化的"球探情报摘要"。

输出要求：
- 包含两队的联赛、胜率、场均进球、伤病名单、近5场战绩
- 包含赔率数据
- 语言：中文
- 格式清晰，便于下一位分析师阅读

请开始收集情报。"""

ANALYST_PROMPT = """你是一位资深的足球战术分析师和盘口专家，精通战术克制关系和胜率预测。

你的任务是：根据下面提供的球探情报和历史战术知识，进行深度的战术分析和胜率推演。

=== 球探情报 ===
{scout_report}
===

=== 历史战术知识（仅供参考）===
{historical_knowledge}
===

分析要求（请逐一展开）：
1. **近期状态对比**：哪队状态更好？依据是什么？
2. **关键伤停影响**：伤病对阵容完整性影响多大？是否有关键球员缺阵？
3. **战术风格预测**：两队分别是进攻型/防守型/控球型？各自的优劣？
4. **战术克制关系**：是否存在风格相克？哪方更占据主动？
5. **胜率预测**：综合以上因素，预测主队胜/平/客队胜的概率分布
6. **盘口走势分析**：结合赔率数据，分析盘口是否合理？是否存在投注价值？
7. **比分预测**：给出一个你认为最可能的比分预测（列2-3个选项）

输出要求：
- 语言：中文
- 分析深入、有洞察力，避免空话套话
- 胜率预测给出具体百分比数字

请开始分析。"""

EDITOR_PROMPT = """你是一个专业的体育报告编辑，负责将战术分析草稿排版为标准 Markdown 格式。

你的任务：
将下面这段战术分析草稿，按照标准的 Markdown 格式进行排版。

=== 战术分析草稿 ===
{analysis_draft}
===

排版要求：
- 主标题使用 `# [足球] {team_a} vs {team_b} 比赛分析报告`
- 使用 `##` 分级标题（基础数据、伤停情况、近期战绩、战术推演、盘口数据等章节）
- 赔率数据用表格呈现（选项、赔率两列）
- 引用块用于展示关键数据
- 底部加一条水平线 `---` 和 "*本报告由 AI 自动生成，仅供参考*" 字样
- 保留原始分析的全部内容，不要删减

请直接输出排版后的 Markdown，无需任何解释。"""


# ===================== 流水线节点函数 =====================


def scout_node(state: MatchAnalysisState) -> dict:
    """
    Agent1 - 球探节点
    调用本地工具（fetch_team_stats + fetch_match_odds）收集原始数据，
    然后用 LLM 整理成情报摘要。
    """
    team_a = state["team_a"]
    team_b = state["team_b"]

    logger.info(f"[Scout Agent] 开始收集情报: {team_a} vs {team_b}")

    fetch_errors = 0

    # 1. 调用本地工具获取数据
    try:
        a_stats = fetch_team_stats(team_a)
    except Exception as e:
        logger.warning(f"[Scout] 获取 {team_a} 数据失败: {e}")
        fetch_errors += 1
        a_stats = {"team_name": team_a, "league": "Unknown", "win_rate": 0.0,
                   "avg_goals": 0.0, "injuries": [], "recent_matches": []}

    try:
        b_stats = fetch_team_stats(team_b)
    except Exception as e:
        logger.warning(f"[Scout] 获取 {team_b} 数据失败: {e}")
        fetch_errors += 1
        b_stats = {"team_name": team_b, "league": "Unknown", "win_rate": 0.0,
                   "avg_goals": 0.0, "injuries": [], "recent_matches": []}

    try:
        odds = fetch_match_odds(team_a, team_b)
    except Exception as e:
        logger.warning(f"[Scout] 获取赔率数据失败: {e}")
        fetch_errors += 1
        odds = {"team_a": team_a, "team_b": team_b,
                "home_win": "N/A", "draw": "N/A", "away_win": "N/A"}

    # 2. 构建原始数据摘要（给 LLM 阅读）
    def fmt_stats(stats: dict) -> str:
        lines = [
            f"球队：{stats['team_name']}（{stats['league']}）",
            f"赛季胜率：{stats['win_rate']:.0%}，场均进球：{stats['avg_goals']}",
            f"伤病/状态：{', '.join(stats['injuries']) if stats['injuries'] else '无'}",
            "近5场战绩：",
        ]
        for m in stats["recent_matches"]:
            lines.append(f"  {m['date']} {m['result']} vs {m['opponent']} {m['score']}")
        return "\n".join(lines)

    raw_data = f"""=== {team_a} 基础数据 ===
{fmt_stats(a_stats)}

=== {team_b} 基础数据 ===
{fmt_stats(b_stats)}

=== 赔率数据 ===
对阵：{odds['team_a']} vs {odds['team_b']}
主胜：{odds['home_win']} | 平局：{odds['draw']} | 主负：{odds['away_win']}"""

    # 3. 让 LLM 将原始数据整理成"球探情报摘要"
    system_prompt = "你是一个顶级足球球探，擅长收集和整理球队情报。请根据提供的原始数据，输出一段结构化的球探情报摘要。"
    scout_report = chat(
        prompt=f"请将以下原始数据整理成一段专业的球探情报摘要：\n\n{raw_data}",
        system_prompt=system_prompt,
    )

    logger.info(f"[Scout Agent] 情报收集完成，长度: {len(scout_report)} chars")
    return {"scout_report": scout_report, "fetch_errors": fetch_errors}


def analyst_node(state: MatchAnalysisState) -> dict:
    """
    Agent3 - 战术分析师节点
    接收球探情报 + 历史知识，纯 LLM 逻辑推理，输出战术分析草稿。
    """
    scout_report = state["scout_report"]
    historical_knowledge = state.get("historical_knowledge") or "（暂无历史知识参考）"

    logger.info(f"[Analyst Agent] 开始战术分析")

    analysis_draft = chat(
        prompt=ANALYST_PROMPT.format(
            scout_report=scout_report,
            historical_knowledge=historical_knowledge,
        ),
        system_prompt="你是一位资深的足球战术分析师和盘口专家，精通战术克制关系和胜率预测。",
    )

    logger.info(f"[Analyst Agent] 分析完成，长度: {len(analysis_draft)} chars")
    return {"analysis_draft": analysis_draft}


def editor_node(state: MatchAnalysisState) -> dict:
    """
    Agent4 - 主编节点
    接收战术分析草稿，纯格式排版，输出 Markdown 报告。
    """
    team_a = state["team_a"]
    team_b = state["team_b"]
    analysis_draft = state["analysis_draft"]

    logger.info(f"[Editor Agent] 开始排版 Markdown")

    final_report = chat(
        prompt=EDITOR_PROMPT.format(team_a=team_a, team_b=team_b, analysis_draft=analysis_draft),
        system_prompt="你是一个专业的体育报告编辑，负责将分析草稿排版为标准 Markdown。",
    )

    logger.info(f"[Editor Agent] 排版完成，长度: {len(final_report)} chars")
    return {"final_report": final_report}


def fallback_scout_node(state: MatchAnalysisState) -> dict:
    """
    Fallback 节点：Scout 失败后备用尝试
    返回降级空数据，不阻断后续链路
    """
    team_a = state["team_a"]
    team_b = state["team_b"]
    logger.warning(f"[Fallback Scout] 备用尝试: {team_a} vs {team_b}")
    try:
        a_stats = fetch_team_stats(team_a)
        b_stats = fetch_team_stats(team_b)
        odds = fetch_match_odds(team_a, team_b)
        def fmt_stats(stats):
            lines = [
                f"球队：{stats['team_name']}（{stats['league']}）",
                f"赛季胜率：{stats['win_rate']:.0%}，场均进球：{stats['avg_goals']}",
                f"伤病/状态：{', '.join(stats['injuries']) if stats['injuries'] else '无'}",
                "近5场战绩：",
            ]
            for m in stats["recent_matches"]:
                lines.append(f"  {m['date']} {m['result']} vs {m['opponent']} {m['score']}")
            return "\n".join(lines)
        raw_data = f"=== {team_a} 基础数据 ===\n{fmt_stats(a_stats)}\n\n=== {team_b} 基础数据 ===\n{fmt_stats(b_stats)}\n\n=== 赔率数据 ===\n主胜：{odds['home_win']} | 平局：{odds['draw']} | 主负：{odds['away_win']}"
        scout_report = chat(prompt=f"请将以下原始数据整理成一段专业的球探情报摘要：\n\n{raw_data}",
                           system_prompt="你是一个顶级足球球探，擅长收集和整理球队情报。")
        logger.info("[Fallback Scout] 备用成功")
        return {"scout_report": scout_report}
    except Exception as e:
        logger.warning(f"[Fallback Scout] 备用仍然失败: {e}")
        return {"scout_report": ""}  # 降级空数据，不阻断后续


# ===================== 图构建 =====================


def build_multi_agent_graph():
    from langgraph.graph import StateGraph, END
    from retriever_node import retriever_node

    graph = StateGraph(MatchAnalysisState)

    graph.add_node("scout", scout_node)
    graph.add_node("fallback_scout", fallback_scout_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("editor", editor_node)

    graph.set_entry_point("scout")
    graph.add_edge("scout", "retriever")
    graph.add_edge("retriever", "analyst")
    graph.add_edge("analyst", "editor")
    graph.add_edge("editor", END)

    return graph.compile()


multi_agent_graph = build_multi_agent_graph()


# ===================== 入口函数 =====================


def run_multi_agent_analysis(team_a: str, team_b: str) -> dict:
    initial_state: MatchAnalysisState = {
        "team_a": team_a,
        "team_b": team_b,
        "scout_report": "",
        "historical_knowledge": "",
        "analysis_draft": "",
        "final_report": "",
        "fetch_errors": 0,
    }
    result = multi_agent_graph.invoke(initial_state)
    # 全链路状态持久化
    save_graph_snapshot(result)
    return result


# ===================== 测试入口 =====================

if __name__ == "__main__":
    print("=" * 60)
    print("Multi-Agent 流水线测试（含 RAG Retriever）")
    print("=" * 60)

    result = run_multi_agent_analysis("曼城", "阿森纳")

    # 写入文件避免 Windows GBK 编码问题
    with open("multi_agent_output.txt", "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("Agent1 (Scout) 输出:\n")
        f.write(result["scout_report"])
        f.write("\n\n" + "=" * 60 + "\n")
        f.write("Agent2 (Retriever) 输出:\n")
        f.write(result.get("historical_knowledge", ""))
        f.write("\n\n" + "=" * 60 + "\n")
        f.write("Agent3 (Analyst) 输出:\n")
        f.write(result["analysis_draft"])
        f.write("\n\n" + "=" * 60 + "\n")
        f.write("Agent4 (Editor) 输出:\n")
        f.write(result["final_report"])
        f.write("\n\n" + "=" * 60 + "\n")
        f.write(f"fetch_errors: {result.get('fetch_errors', 0)}\n")
        f.write(f"最终报告长度: {len(result['final_report'])} chars\n")

    print(f"scout_report: {len(result['scout_report'])} chars")
    print(f"historical_knowledge: {len(result.get('historical_knowledge', '') or '')} chars")
    print(f"analysis_draft: {len(result['analysis_draft'])} chars")
    print(f"final_report: {len(result['final_report'])} chars")
    print("输出已写入 multi_agent_output.txt")
    print("测试完成 OK")