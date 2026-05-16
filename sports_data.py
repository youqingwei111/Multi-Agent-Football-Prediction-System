"""
体育数据获取模块 - 接入 api-football.com 真实 API
Free plan 限制：仅支持 2022-2024 赛季，无赔率数据
"""

import os
import time
import logging
import requests
from dotenv import load_dotenv
from typing import TypedDict

load_dotenv()
logger = logging.getLogger(__name__)

API_KEY = os.getenv("SPORTSAPI_API_KEY")
HEADERS = {"x-apisports-key": API_KEY}
BASE_URL = "https://v3.football.api-sports.io"

# 中文队名 → API 搜索名 映射（补充 API 无法直接按中文搜索的情况）
TEAM_NAME_ALIASES: dict[str, str] = {
    "曼城": "Manchester City",
    "曼联": "Manchester United",
    "皇马": "Real Madrid",
    "巴萨": "Barcelona",
    "拜仁": "Bayern Munich",
    "利物浦": "Liverpool",
    "切尔西": "Chelsea",
    "阿森纳": "Arsenal",
    "尤文": "Juventus",
    "米兰": "AC Milan",
    "国米": "Inter",
    "多特": "Borussia Dortmund",
    "巴黎": "Paris Saint-Germain",
    "马竞": "Atletico Madrid",
    "热刺": "Tottenham Hotspur",
}

# Free plan 支持的赛季
DEFAULT_SEASON = 2024


# ===================== 数据结构 =====================

class MatchResultDict(TypedDict, total=False):
    team_name: str
    league: str
    recent_matches: list[dict]
    injuries: list[str]
    win_rate: float
    avg_goals: float


class OddsDict(TypedDict, total=False):
    team_a: str
    team_b: str
    home_win: float
    draw: float
    away_win: float
    fetch_time: str


# ===================== 工具函数 =====================

def _do_request(endpoint: str, params: dict, max_retries: int = 3) -> dict:
    """带重试的 HTTP GET"""
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(
                f"{BASE_URL}/{endpoint}",
                params=params,
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("errors") and any(data["errors"].values()):
                raise ConnectionError(f"API errors: {data['errors']}")
            return data
        except Exception as e:
            logger.warning(f"[Attempt {attempt}/{max_retries}] {endpoint} failed: {e}")
            if attempt == max_retries:
                raise ConnectionError(f"{endpoint} failed after {max_retries} retries") from e
            time.sleep(2 ** attempt)
    raise ConnectionError("unreachable")


def _search_team_id(team_name: str) -> int | None:
    """按队名搜索球队，返回 team_id（支持中文别名映射）"""
    # 中文名转英文
    search_name = TEAM_NAME_ALIASES.get(team_name, team_name)
    data = _do_request("teams", {"name": search_name})
    if data.get("results", 0) > 0:
        return data["response"][0]["team"]["id"]
    return None


# ===================== 核心函数 =====================

def fetch_team_stats(team_name: str, max_retries: int = 3) -> MatchResultDict:
    """
    获取球队近5场战绩和伤病名单（真实 API）
    Free plan 限制：仅 2022-2024 赛季数据
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            # 1. 查找球队 ID
            team_id = _search_team_id(team_name)
            if team_id is None:
                raise ValueError(f"球队不存在或名称不匹配: {team_name}")

            # 2. 球队统计（含 form 战绩字符串）
            stats_data = _do_request(
                "teams/statistics",
                {"team": team_id, "league": 39, "season": DEFAULT_SEASON},
            )
            stats = stats_data["response"]

            # 从统计中获取正确的 league_id
            league_id = stats.get("league", {}).get("id", 39)

            # 6. 获取近5场战绩（Free plan 不支持 last=N，改用 league fixtures 过滤）
            all_fixtures_data = _do_request(
                "fixtures",
                {"league": league_id, "season": DEFAULT_SEASON},
            )
            matches = []
            if all_fixtures_data.get("results", 0) > 0:
                team_fixtures = [
                    f for f in all_fixtures_data["response"]
                    if f["teams"]["home"]["id"] == team_id or f["teams"]["away"]["id"] == team_id
                ]
                # 取最近5场
                for f in team_fixtures[-5:]:
                    ft = f["fixture"]
                    home = f["teams"]["home"]
                    away = f["teams"]["away"]
                    gh, ga = f["goals"]["home"], f["goals"]["away"]
                    is_home = home["id"] == team_id
                    if is_home:
                        outcome = "胜" if gh > ga else "平" if gh == ga else "负"
                        opp = away["name"]
                        score = f"{gh}-{ga}"
                    else:
                        outcome = "胜" if ga > gh else "平" if ga == gh else "负"
                        opp = home["name"]
                        score = f"{ga}-{gh}"
                    matches.append({
                        "date": ft["date"][:10],
                        "opponent": opp,
                        "result": outcome,
                        "score": score,
                    })

            # 4. 计算胜负率
            form_str = stats.get("form", "") or ""
            if form_str:
                wins = sum(1 for c in form_str.upper() if c == "W")
                win_rate = wins / len(form_str)
            else:
                win_rate = 0.0

            # 5. 伤病名单
            injuries_data = _do_request(
                "injuries",
                {"team": team_id, "season": DEFAULT_SEASON},
            )
            injuries = []
            if injuries_data.get("results", 0) > 0:
                for inj in injuries_data["response"]:
                    player = inj["player"]
                    injuries.append(f"{player['name']}（{player.get('type','未知伤情')}）")

            # 6. 联赛信息
            league_name = stats.get("league", {}).get("name", "未知")

            logger.info(f"成功获取球队数据: {team_name} (id={team_id})")
            return {
                "team_name": team_name,
                "league": league_name,
                "recent_matches": matches,
                "injuries": injuries[:5],  # 最多5条
                "win_rate": win_rate,
                "avg_goals": float(stats.get("goals", {}).get("for", {}).get("average", {}).get("total", 0.0) or 0.0),
            }

        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if "429" in err_str or "too many requests" in err_str:
                wait_time = 5 * attempt
                logger.warning(f"[Attempt {attempt}/{max_retries}] Rate limit hit, waiting {wait_time}s: {e}")
                time.sleep(wait_time)
                continue
            logger.warning(f"[Attempt {attempt}/{max_retries}] 获取球队数据失败: {e}")
            if attempt == max_retries:
                raise ConnectionError(f"获取球队数据失败，已重试{max_retries}次: {e}") from last_error
            time.sleep(2 ** attempt)

    raise ConnectionError(f"获取球队数据失败: {last_error}")


def fetch_match_odds(team_a: str, team_b: str, max_retries: int = 3) -> OddsDict:
    """
    获取比赛胜平负赔率
    注意：api-football free plan 不提供赔率数据，返回 N/A
    """
    # Free plan 无赔率，直接返回 N/A，避免阻断主流程
    logger.warning(f"[Free Plan] 赔率数据不可用: {team_a} vs {team_b}")
    return {
        "team_a": team_a,
        "team_b": team_b,
        "home_win": "N/A",
        "draw": "N/A",
        "away_win": "N/A",
        "fetch_time": __import__("datetime").datetime.now().isoformat(),
    }


# ===================== 测试入口 =====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=" * 50)
    print("测试 fetch_team_stats")
    print("=" * 50)

    stats = fetch_team_stats("Manchester City")
    print(f"\n球队: {stats['team_name']} ({stats['league']})")
    print(f"胜率: {stats['win_rate']:.0%} | 场均进球: {stats['avg_goals']}")
    print("近期战绩:")
    for m in stats["recent_matches"]:
        print(f"  {m['date']} {m['result']} {m['opponent']} {m['score']}")
    print(f"伤病: {', '.join(stats['injuries']) if stats['injuries'] else '无'}")

    print("\n" + "-" * 50)

    stats2 = fetch_team_stats("Real Madrid")
    print(f"\n球队: {stats2['team_name']} ({stats2['league']})")
    print(f"伤病: {', '.join(stats2['injuries']) if stats2['injuries'] else '无'}")

    print("\n" + "=" * 50)
    print("测试 fetch_match_odds")
    print("=" * 50)

    odds = fetch_match_odds("Manchester City", "Real Madrid")
    print(f"\n{odds['team_a']} vs {odds['team_b']}")
    print(f"主胜: {odds['home_win']} | 平局: {odds['draw']} | 主负: {odds['away_win']}")

    print("\n所有测试通过 OK")