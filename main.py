"""
FastAPI 后端服务 - 足球赛事分析接口
启动方式: uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

from graph_workflow import run_analysis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================== FastAPI 实例 =====================

app = FastAPI(
    title="足球赛事分析 API",
    description="基于 LangGraph 多节点编排的足球比赛分析服务",
    version="1.0.0",
)

# ===================== CORS 中间件 =====================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有前端 origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== 请求/响应 Schema =====================


class AnalyzeRequest(BaseModel):
    team_a: str
    """主队名称（支持中文，如"曼城"）"""
    team_b: str
    """客队名称（支持中文，如"阿森纳"）"""


class AnalyzeResponse(BaseModel):
    team_a: str
    team_b: str
    fetch_errors: int
    final_report: str


# ===================== 路由 =====================


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_match(req: AnalyzeRequest):
    """
    分析指定两队比赛，返回完整 Markdown 报告
    """
    if not req.team_a or not req.team_b:
        raise HTTPException(status_code=400, detail="team_a 和 team_b 不能为空")

    logger.info(f"收到分析请求: {req.team_a} vs {req.team_b}")

    try:
        result = run_analysis(req.team_a, req.team_b)
    except Exception as e:
        logger.error(f"Graph 运行失败: {e}")
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")

    return AnalyzeResponse(
        team_a=result.get("team_a", req.team_a),
        team_b=result.get("team_b", req.team_b),
        fetch_errors=result.get("fetch_errors", 0),
        final_report=result.get("final_report", ""),
    )


# ===================== 健康检查 =====================


@app.get("/health")
async def health():
    return {"status": "ok"}


# ===================== 独立运行 =====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)