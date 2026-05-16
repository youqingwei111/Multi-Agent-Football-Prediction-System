"""
LangGraph 状态机编排 - 包含条件边、重试逻辑、降级节点
"""

from langgraph.graph import StateGraph, END
from typing import TypedDict

# 导入本项目节点
from graph_nodes import (
    MatchAnalysisState,
    scout_node,
    analyst_node,
    editor_node,
)


# ===================== 降级节点 =====================


def fallback_node(state: MatchAnalysisState) -> dict:
    """
    降级节点：scout 重试超过阈值后执行，输出终止原因
    """
    return {
        "final_report": (
            "# 数据获取失败，终止分析\n\n"
            "多次重试后仍无法获取比赛数据，可能原因：\n"
            "- 球队名称输入有误\n"
            "- 第三方 API 服务暂时不可用\n\n"
            "**建议**：请核实球队名称后重试，或稍后再试。"
        )
    }


# ===================== 路由函数（条件边核心） =====================


def scout_route_after_check(state: MatchAnalysisState) -> str:
    """
    scout_node 之后的条件边路由函数
    返回值决定下一步走哪个节点（字符串对应节点名）
    """
    raw_intel: dict = state.get("raw_intel", {})
    fetch_errors: int = state.get("fetch_errors", 0)

    # 检查数据是否为空（各字段均无有效数据）
    team_a_data = raw_intel.get("team_a_stats", {})
    team_b_data = raw_intel.get("team_b_stats", {})
    odds_data = raw_intel.get("odds", {})

    data_is_empty = (
        not team_a_data.get("team_name")
        and not team_b_data.get("team_name")
        and not odds_data.get("team_a")
    )

    if data_is_empty:
        if fetch_errors >= 3:
            return "fallback"
        return "scout"  # 重新执行 scout_node（重试逻辑由 scout_node 内部累加错误数）
    return "analyst"


# ===================== 图构建 =====================


def build_analysis_graph():
    """
    构建并编译比赛分析状态机图
    """
    # 1. 创建图实例，指定状态 schema
    graph = StateGraph(MatchAnalysisState)

    # 2. 添加节点
    graph.add_node("scout", scout_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("editor", editor_node)
    graph.add_node("fallback", fallback_node)

    # 3. 设置入口点
    graph.set_entry_point("scout")

    # 4. 添加条件边：scout_node 之后根据数据状态路由
    graph.add_conditional_edges(
        source="scout",
        path=scout_route_after_check,
        path_map={
            "scout": "scout",      # 重新执行 scout（会由 scout 内部累加 fetch_errors）
            "analyst": "analyst",  # 正常下一步
            "fallback": "fallback",  # 降级终止
        },
    )

    # 5. 正常流程节点之间的边
    graph.add_edge("analyst", "editor")
    graph.add_edge("editor", END)
    graph.add_edge("fallback", END)

    # 6. 编译图
    return graph.compile()


# ===================== 公开 API =====================

analysis_graph = build_analysis_graph()


def run_analysis(team_a: str, team_b: str) -> dict:
    """
    外部调用入口：输入主队和客队，运行完整状态机
    """
    initial_state: MatchAnalysisState = {
        "team_a": team_a,
        "team_b": team_b,
        "raw_intel": {},
        "analysis_draft": "",
        "final_report": "",
        "fetch_errors": 0,
    }

    final_state = analysis_graph.invoke(initial_state)
    return final_state


# ===================== 测试用例 =====================

if __name__ == "__main__":
    print("=" * 60)
    print("LangGraph 状态机测试")
    print("=" * 60)

    # --- 正常流程 ---
    print("\n>>> 正常流程：曼城 vs 皇马")
    result = run_analysis("曼城", "皇马")
    print(f"fetch_errors: {result['fetch_errors']}")
    print(f"final_report length: {len(result['final_report'])} chars")
    print("\n--- Markdown 报告预览 ---")
    print(result["final_report"][:500])

    print("\n" + "-" * 60)

    # --- 异常流程（未知球队触发重试） ---
    print("\n>>> 异常流程：某未知球队 vs 皇马（触发重试+降级）")
    result2 = run_analysis("某未知球队", "皇马")
    print(f"fetch_errors: {result2['fetch_errors']}")
    print(f"final_report:\n{result2['final_report']}")

    print("\n" + "-" * 60)

    # --- 部分数据缺失（只缺赔率，analyst 仍可执行） ---
    print("\n>>> 部分缺失：某未知球队 vs 某未知球队B（均无数据）")
    result3 = run_analysis("某未知球队A", "某未知球队B")
    print(f"fetch_errors: {result3['fetch_errors']}")
    print(f"final_report:\n{result3['final_report']}")

    print("\n测试完成 OK")