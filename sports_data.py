"""
体育数据获取模块
USE_MOCK=true 时使用模拟数据（无 API 额度时启用）
USE_MOCK=false 时使用 api-football.com 真实 API
"""

import os
import time
import logging
import requests
from dotenv import load_dotenv
from typing import TypedDict

load_dotenv()

logger = logging.getLogger(__name__)

# ===================== Mock 模式开关 =====================
USE_MOCK = os.getenv("USE_MOCK", "true").lower() == "true"
# USE_MOCK=false 时才加载以下真实 API 配置
if not USE_MOCK:
    API_KEY = os.getenv("SPORTSAPI_API_KEY")
    HEADERS = {"x-apisports-key": API_KEY}
    BASE_URL = "https://v3.football.api-sports.io"
    DEFAULT_SEASON = 2024


# ===================== Mock 数据 =====================

MOCK_TEAM_STATS: dict[str, dict] = {
    "Manchester City": {
        "team_name": "Manchester City",
        "league": "Premier League",
        "recent_matches": [
            {"opponent": "Aston Villa", "result": "胜", "score": "2-1", "date": "2025-04-22"},
            {"opponent": "Wolves", "result": "胜", "score": "1-0", "date": "2025-05-02"},
            {"opponent": "Southampton", "result": "平", "score": "0-0", "date": "2025-05-10"},
            {"opponent": "Bournemouth", "result": "胜", "score": "3-1", "date": "2025-05-20"},
            {"opponent": "Fulham", "result": "胜", "score": "2-0", "date": "2025-05-25"},
        ],
        "injuries": ["O. Bobb (Missing Fixture)", "Rodri (Questionable)"],
        "win_rate": 0.55,
        "avg_goals": 1.9,
    },
    "Arsenal": {
        "team_name": "Arsenal",
        "league": "Premier League",
        "recent_matches": [
            {"opponent": "Crystal Palace", "result": "胜", "score": "3-0", "date": "2025-04-21"},
            {"opponent": "Manchester United", "result": "胜", "score": "2-1", "date": "2025-05-03"},
            {"opponent": "Brighton", "result": "平", "score": "1-1", "date": "2025-05-10"},
            {"opponent": "Liverpool", "result": "负", "score": "1-2", "date": "2025-05-18"},
            {"opponent": "Newcastle", "result": "胜", "score": "2-0", "date": "2025-05-25"},
        ],
        "injuries": ["B. Saka (Muscle Injury)", "O. Xhaka (Ankle)"],
        "win_rate": 0.65,
        "avg_goals": 2.1,
    },
    "Real Madrid": {
        "team_name": "Real Madrid",
        "league": "La Liga",
        "recent_matches": [
            {"opponent": "Barcelona", "result": "负", "score": "2-3", "date": "2025-05-11"},
            {"opponent": "Sevilla", "result": "胜", "score": "3-0", "date": "2025-05-04"},
            {"opponent": "Real Sociedad", "result": "胜", "score": "2-1", "date": "2025-04-27"},
            {"opponent": "Athletic Bilbao", "result": "平", "score": "1-1", "date": "2025-04-20"},
            {"opponent": "Getafe", "result": "胜", "score": "4-0", "date": "2025-04-13"},
        ],
        "injuries": ["E. Camavinga (Knee)", "J. Bellingham (Suspended)"],
        "win_rate": 0.62,
        "avg_goals": 2.0,
    },
    "Barcelona": {
        "team_name": "Barcelona",
        "league": "La Liga",
        "recent_matches": [
            {"opponent": "Real Madrid", "result": "胜", "score": "3-2", "date": "2025-05-11"},
            {"opponent": "Villarreal", "result": "胜", "score": "3-1", "date": "2025-05-04"},
            {"opponent": "Atletico Madrid", "result": "胜", "score": "2-0", "date": "2025-04-28"},
            {"opponent": "Real Sociedad", "result": "平", "score": "2-2", "date": "2025-04-21"},
            {"opponent": "Mallorca", "result": "胜", "score": "3-0", "date": "2025-04-14"},
        ],
        "injuries": ["Gavi (ACL - Long Term)", "A. Christensen (Calf)"],
        "win_rate": 0.70,
        "avg_goals": 2.3,
    },
}

MOCK_ODDS = {
    ("Manchester City", "Arsenal"): {"home_win": 2.10, "draw": 3.30, "away_win": 3.40},
    ("Arsenal", "Manchester City"): {"home_win": 2.20, "draw": 3.25, "away_win": 3.20},
    ("Real Madrid", "Barcelona"): {"home_win": 2.05, "draw": 3.40, "away_win": 3.50},
    ("Barcelona", "Real Madrid"): {"home_win": 2.30, "draw": 3.20, "away_win": 3.00},
}

# 中文别名（Mock 模式也需要）
TEAM_NAME_ALIASES: dict[str, str] = {
    "曼城": "Manchester City",
    "曼联": "Manchester United",
    "皇马": "Real Madrid",
    "巴萨": "Barcelona",
    "拜仁": "Bayern München",
    "利物浦": "Liverpool",
    "切尔西": "Chelsea",
    "阿森纳": "Arsenal",
    "尤文": "Juventus",
    "米兰": "AC Milan",
    "国米": "Inter",
    "多特": "Borussia Dortmund",
    "巴黎": "Paris Saint-Germain",
    "巴黎圣日尔曼": "Paris Saint-Germain",
    "马竞": "Atletico Madrid",
    "热刺": "Tottenham Hotspur",
    "维拉": "Aston Villa",
    "维罗纳": "Hellas Verona",
}

# 欧洲焦点球队 ID 映射表（通过 API /teams 接口查出）
TEAM_ID_MAPPING: dict[str, int] = {
    # 英超
    "Manchester City": 50,
    "Manchester United": 33,
    "Liverpool": 40,
    "Chelsea": 49,
    "Arsenal": 42,
    "Aston Villa": 103,
    "Tottenham Hotspur": 47,
    # 西甲
    "Real Madrid": 541,
    "Barcelona": 529,
    "Atletico Madrid": 530,
    # 德甲
    "Bayern München": 157,
    "Borussia Dortmund": 165,
    # 意甲
    "Juventus": 109,
    "AC Milan": 108,
    "Inter": 108,
    # 法甲
    "Paris Saint-Germain": 85,
}


def get_team_id(team_name: str) -> int | None:
    """
    将中文队名或英文队名转换为 API 球队 ID。
    优先从 TEAM_ID_MAPPING 查询，未知球队再通过 API 搜索并缓存。
    """
    # 1. 先尝试 ID 映射表（英文名）
    if team_name in TEAM_ID_MAPPING:
        return TEAM_ID_MAPPING[team_name]
    # 2. 通过别名转英文后再查映射表
    resolved = TEAM_NAME_ALIASES.get(team_name, team_name)
    if resolved in TEAM_ID_MAPPING:
        return TEAM_ID_MAPPING[resolved]
    # 3. 动态搜索 API
    team_id = _search_team_id(team_name)
    if team_id is not None:
        TEAM_ID_MAPPING[resolved] = team_id
        logger.info(f"[Team ID] Cached {resolved} -> {team_id}")
    return team_id


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


# ===================== Mock 实现 =====================


def _mock_team_stats(team_name: str, resolved_name: str) -> MatchResultDict:
    if resolved_name in MOCK_TEAM_STATS:
        data = MOCK_TEAM_STATS[resolved_name]
        return {
            "team_name": resolved_name,
            "league": data["league"],
            "recent_matches": data["recent_matches"],
            "injuries": data["injuries"],
            "win_rate": data["win_rate"],
            "avg_goals": data["avg_goals"],
        }
    # 未知球队返回合理默认值
    return {
        "team_name": resolved_name,
        "league": "Unknown",
        "recent_matches": [],
        "injuries": [],
        "win_rate": 0.0,
        "avg_goals": 0.0,
    }


def _mock_match_odds(team_a: str, team_b: str) -> OddsDict:
    key = (team_a, team_b)
    if key in MOCK_ODDS:
        odds = MOCK_ODDS[key]
    elif (team_b, team_a) in MOCK_ODDS:
        o = MOCK_ODDS[(team_b, team_a)]
        odds = {"home_win": o["away_win"], "draw": o["draw"], "away_win": o["home_win"]}
    else:
        # 未知对决生成模拟赔率
        import random
        odds = {
            "home_win": round(random.uniform(1.9, 2.5), 2),
            "draw": round(random.uniform(3.0, 3.5), 2),
            "away_win": round(random.uniform(2.5, 4.0), 2),
        }
    return {
        "team_a": team_a,
        "team_b": team_b,
        **odds,
        "fetch_time": __import__("datetime").datetime.now().isoformat(),
    }


# ===================== 真实 API 实现 =====================


def _do_request(endpoint: str, params: dict, max_retries: int = 3) -> dict:
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
    search_name = TEAM_NAME_ALIASES.get(team_name, team_name)
    data = _do_request("teams", {"name": search_name})
    if data.get("results", 0) > 0:
        return data["response"][0]["team"]["id"]
    return None


# ===================== 核心函数 =====================


def fetch_team_stats(team_name: str, max_retries: int = 3) -> MatchResultDict:
    """
    获取球队近5场战绩和伤病名单
    """
    # ---------- Mock 模式 ----------
    if USE_MOCK:
        resolved = TEAM_NAME_ALIASES.get(team_name, team_name)
        logger.info(f"[MOCK] fetch_team_stats: {team_name} -> {resolved}")
        return _mock_team_stats(team_name, resolved)

    # ---------- 真实 API 模式 ----------
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            team_id = get_team_id(team_name)
            if team_id is None:
                raise ValueError(f"球队不存在或名称不匹配: {team_name}")

            stats_data = _do_request(
                "teams/statistics",
                {"team": team_id, "league": 39, "season": DEFAULT_SEASON},
            )
            stats = stats_data["response"]
            league_id = stats.get("league", {}).get("id", 39)

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
                for f in team_fixtures[-5:]:
                    ft = f["fixture"]
                    home, away = f["teams"]["home"], f["teams"]["away"]
                    gh, ga = f["goals"]["home"], f["goals"]["away"]
                    is_home = home["id"] == team_id
                    if is_home:
                        outcome = "胜" if gh > ga else "平" if gh == ga else "负"
                        matches.append({"date": ft["date"][:10], "opponent": away["name"], "result": outcome, "score": f"{gh}-{ga}"})
                    else:
                        outcome = "胜" if ga > gh else "平" if ga == gh else "负"
                        matches.append({"date": ft["date"][:10], "opponent": home["name"], "result": outcome, "score": f"{ga}-{gh}"})

            form_str = stats.get("form", "") or ""
            win_rate = sum(1 for c in form_str.upper() if c == "W") / len(form_str) if form_str else 0.0

            injuries_data = _do_request("injuries", {"team": team_id, "season": DEFAULT_SEASON})
            injuries = [inj["player"]["name"] + "（" + inj["player"].get("type", "未知") + "）"
                        for inj in injuries_data.get("response", [])[:5]]

            logger.info(f"成功获取球队数据: {team_name} (id={team_id})")
            return {
                "team_name": team_name,
                "league": stats.get("league", {}).get("name", "未知"),
                "recent_matches": matches,
                "injuries": injuries,
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
    """获取比赛胜平负赔率"""
    if USE_MOCK:
        resolved_a = TEAM_NAME_ALIASES.get(team_a, team_a)
        resolved_b = TEAM_NAME_ALIASES.get(team_b, team_b)
        logger.info(f"[MOCK] fetch_match_odds: {team_a} vs {team_b}")
        return _mock_match_odds(resolved_a, resolved_b)

    # 真实 API：Free plan 不提供赔率
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
    print(f"USE_MOCK = {USE_MOCK}")

    print("\n--- fetch_team_stats ---")
    s1 = fetch_team_stats("曼城")
    print(f"{s1['team_name']} | 胜率 {s1['win_rate']:.0%} | 场均 {s1['avg_goals']}球")
    print(f"  伤病: {s1['injuries']}")

    s2 = fetch_team_stats("阿森纳")
    print(f"{s2['team_name']} | 胜率 {s2['win_rate']:.0%} | 场均 {s2['avg_goals']}球")

    print("\n--- fetch_match_odds ---")
    o1 = fetch_match_odds("曼城", "阿森纳")
    print(f"{o1['team_a']} vs {o1['team_b']}: 主胜 {o1['home_win']} 平 {o1['draw']} 主负 {o1['away_win']}")

    print("\n--- fetch_team_stats (未知球队降级) ---")
    s3 = fetch_team_stats("某未知队")
    print(f"降级返回: {s3}")

    print("\n测试完成 OK")
    