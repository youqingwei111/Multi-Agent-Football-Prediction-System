"""
FastAPI 后端服务 - 足球赛事分析接口
启动方式: uvicorn main:app --reload --port 8000
"""

import asyncio
import json
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from multi_agent_graph import run_multi_agent_analysis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="足球赛事分析 API - Multi-Agent",
    description="基于 Multi-Agent 架构的足球比赛分析服务，流水线：球探→情报检索→分析师→主编",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    team_a: str
    team_b: str


class AnalyzeResponse(BaseModel):
    team_a: str
    team_b: str
    fetch_errors: int
    final_report: str


async def event_generator(node: str, status: str, message: str = ""):
    """生成 SSE 事件"""
    data = {"node": node, "status": status, "message": message}
    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/analyze/stream")
async def analyze_match_stream(req: AnalyzeRequest):
    """
    流式分析接口：Server-Sent Events 实时推送各节点运行状态
    """
    if not req.team_a or not req.team_b:
        raise HTTPException(status_code=400, detail="team_a 和 team_b 不能为空")

    logger.info(f"[SSE] 收到分析请求: {req.team_a} vs {req.team_b}")

    async def stream_response():
        try:
            # 启动分析任务（在新线程池中运行，避免阻塞事件循环）
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, run_multi_agent_analysis, req.team_a, req.team_b
            )

            # 推送完成事件
            yield f"data: {json.dumps({'node': 'done', 'status': 'completed', 'final_report': result.get('final_report', '')}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"[SSE] 分析失败: {e}")
            yield f"data: {json.dumps({'node': 'error', 'status': 'failed', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_match(req: AnalyzeRequest):
    if not req.team_a or not req.team_b:
        raise HTTPException(status_code=400, detail="team_a 和 team_b 不能为空")

    logger.info(f"收到分析请求: {req.team_a} vs {req.team_b}")

    try:
        result = run_multi_agent_analysis(req.team_a, req.team_b)
    except Exception as e:
        logger.error(f"Multi-Agent Graph 运行失败: {e}")
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")

    return AnalyzeResponse(
        team_a=result.get("team_a", req.team_a),
        team_b=result.get("team_b", req.team_b),
        fetch_errors=result.get("fetch_errors", 0),
        final_report=result.get("final_report", ""),
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)