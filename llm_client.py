"""
MiniMax LLM 客户端 - 用于 analyst_node 调用大模型进行战术分析
"""

import os
import json
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
MODEL = os.getenv("LLM_MODEL", "MiniMax-M2")


def chat(prompt: str, system_prompt: str = "你是一个专业的足球战术分析师。", max_retries: int = 3) -> str:
    """
    调用 MiniMax-M2 进行对话补全
    """
    url = f"{MINIMAX_BASE_URL}/text/chatcompletion_v2"
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 1024,
        "temperature": 0.7,
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # MiniMax 响应结构: choices[0].message.content
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]

            raise ValueError(f"Unexpected response structure: {data}")

        except Exception as e:
            logger.warning(f"[Attempt {attempt}/{max_retries}] MiniMax API failed: {e}")
            if attempt == max_retries:
                raise ConnectionError(f"MiniMax LLM 调用失败，已重试{max_retries}次") from e
            time.sleep(2 ** attempt)

    raise ConnectionError("MiniMax LLM 不可达")


def build_analysis_prompt(team_a: str, team_b: str, a_stats: dict, b_stats: dict) -> str:
    """
    构建发送给 LLM 的分析 Prompt
    """
    def fmt_stats(stats: dict) -> str:
        name = stats.get("team_name", "?")
        league = stats.get("league", "?")
        win_rate = stats.get("win_rate", 0.0)
        avg_goals = stats.get("avg_goals", 0.0)
        injuries = stats.get("injuries", [])
        matches = stats.get("recent_matches", [])

        lines = [
            f"球队：{name}（{league}）",
            f"赛季胜率：{win_rate:.0%}",
            f"场均进球：{avg_goals}",
            f"伤病/状态问题：{', '.join(injuries[:3]) if injuries else '无'}",
            "近5场战绩：",
        ]
        for m in matches[-5:]:
            lines.append(f"  {m.get('date','?')} {m.get('result','?')} vs {m.get('opponent','?')} {m.get('score','?')}")
        return "\n".join(lines)

    a_info = fmt_stats(a_stats)
    b_info = fmt_stats(b_stats)

    return f"""请分析以下这场比赛的战术走向和胜负预测：

【主队】
{a_info}

【客队】
{b_info}

请从以下角度进行分析（用中文输出）：
1. 近期状态对比（哪队状态更好）
2. 关键伤停影响（阵容完整度）
3. 战术风格预测（进攻/防守/控球）
4. 胜负预测与比分估算（给出你的判断）

分析要求：专业、简洁、有参考价值。"""


if __name__ == "__main__":
    # 快速连通性测试
    test_prompt = "用一句话评价曼城 vs 皇马的比赛前景。"
    try:
        result = chat(test_prompt)
        print(f"MiniMax 连通性测试成功: {result}")
    except Exception as e:
        print(f"MiniMax 连通性测试失败: {e}")