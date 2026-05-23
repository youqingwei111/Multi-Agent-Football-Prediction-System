"""
Retriever Node - RAG 检索节点
在 Scout 和 Analyst 之间运行，从 PostgreSQL + pgvector 向量库检索历史战术知识
"""

import os
import logging
from typing import TypedDict, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ===================== Embedding 配置 =====================

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


# ===================== Embedding 生成 =====================

def get_embedding(text: str) -> list[float]:
    if EMBEDDING_PROVIDER == "openai":
        return _openai_embedding(text)
    elif EMBEDDING_PROVIDER == "qwen":
        return _qwen_embedding(text)
    elif EMBEDDING_PROVIDER == "minimax":
        return _minimax_embedding(text)
    elif EMBEDDING_PROVIDER == "local":
        return _local_embedding(text)
    else:
        raise ValueError(f"不支持的 EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER}")


def _openai_embedding(text: str) -> list[float]:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def _qwen_embedding(text: str) -> list[float]:
    import dashscope
    from dashscope import TextEmbedding
    dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
    response = TextEmbedding.call(
        model=EMBEDDING_MODEL or "text-embedding-v2",
        input=text,
    )
    if response.status_code != 200:
        raise ConnectionError(f"Qwen Embedding 失败: {response.message}")
    return response.output["embeddings"][0]["embedding"]


def _minimax_embedding(text: str) -> list[float]:
    """
    调用 MiniMax Embedding API

    ⚠️ 重要：必须使用 MiniMax 专属的 Embedding 模型名称，不能用对话模型！
    支持的 Embedding 模型: embo-01、embo-20240607 等（具体以 MiniMax 文档为准）
    绝对不能使用 minimax-m2、MiniMax-M2 等对话模型，否则返回结构完全不同
    """
    import requests as _req
    url = "https://api.minimax.chat/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {os.getenv('MINIMAX_API_KEY')}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": EMBEDDING_MODEL,
        "input": text,
    }
    resp = _req.post(url, headers=headers, json=payload, timeout=30)

    if resp.status_code != 200:
        raw = resp.text
        logger.error(f"[MiniMax Embedding] HTTP {resp.status_code} | 原始响应: {raw}")
        raise ValueError(f"MiniMax Embedding HTTP 错误 {resp.status_code}，详情已打印到日志")

    data = resp.json()

    if "data" not in data:
        raw = resp.text
        logger.error(f"[MiniMax Embedding] 响应缺少 'data' 字段 | 原始响应: {raw}")
        raise ValueError(f"MiniMax Embedding 返回结构异常（无 data 字段），详情已打印到日志")

    embedding = data["data"][0].get("embedding")
    if not embedding:
        logger.error(f"[MiniMax Embedding] embedding 字段为空 | 原始响应: {data}")
        raise ValueError("MiniMax Embedding 返回空向量，详情已打印到日志")

    return embedding


def _local_embedding(text: str) -> list[float]:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDING_MODEL)
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


# ===================== 余弦相似度 =====================

def cosine_similarity(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ===================== 向量检索 =====================

def search_similar_chunks(
    query_embedding: list[float],
    team_filter: str,
    top_k: int = 3,
) -> list[dict]:
    """
    从 PostgreSQL 检索与 query_embedding 余弦相似度最高的 top_k 条 chunk
    """
    import json
    from sqlmodel import Session, select
    from sqlmodel.sql.filter import or_
    from rag_ingestion import TacticalArticle, get_engine

    engine = get_engine()
    with Session(engine) as session:
        tags = [t.strip() for t in team_filter.split(",")]
        conditions = [TacticalArticle.team_tags.contains(t) for t in tags]
        query = select(TacticalArticle).where(or_(*conditions))
        results = session.exec(query).all()

    scored = []
    for row in results:
        emb = json.loads(row.embedding)
        score = cosine_similarity(query_embedding, emb)
        scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "title": row.title,
            "chunk_text": row.chunk_text,
            "score": round(score, 4),
        }
        for score, row in scored[:top_k]
    ]


# ===================== Retriever Node =====================

class MatchAnalysisState(TypedDict, total=False):
    team_a: str
    team_b: str
    scout_report: str
    historical_knowledge: Optional[str]
    analysis_draft: str
    final_report: str
    fetch_errors: int


def retriever_node(state: MatchAnalysisState) -> dict:
    """
    RAG 检索节点
    读取 state 中的 team_a 和 team_b，检索历史战术知识库，
    将结果写入 state['historical_knowledge']。
    未找到结果时写入空字符串，不阻断流水线。
    """
    team_a = state["team_a"]
    team_b = state["team_b"]

    logger.info(f"[Retriever] 检索两队历史战术知识: {team_a} vs {team_b}")

    try:
        # 1. 构造检索查询（使用两队名 + "战术" 关键词）
        query_text = f"{team_a} {team_b} 战术 对阵 分析"
        query_embedding = get_embedding(query_text)

        # 2. 执行向量检索
        results = search_similar_chunks(
            query_embedding=query_embedding,
            team_filter=f"{team_a},{team_b}",
            top_k=3,
        )

        # 3. 拼接检索结果
        if results:
            knowledge_parts = []
            for i, r in enumerate(results, 1):
                knowledge_parts.append(
                    f"[知识片段 {i}]（相似度 {r['score']}）\n"
                    f"来源：{r['title']}\n"
                    f"内容：{r['chunk_text']}"
                )
            historical_knowledge = "\n\n".join(knowledge_parts)
            logger.info(f"[Retriever] 检索到 {len(results)} 条相关知识")
        else:
            historical_knowledge = ""
            logger.info("[Retriever] 未检索到相关知识，写入空字符串")

        return {"historical_knowledge": historical_knowledge}

    except Exception as e:
        logger.warning(f"[Retriever] 检索失败，降级为空知识: {e}")
        return {"historical_knowledge": ""}


# ===================== 测试入口 =====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    test_state: MatchAnalysisState = {
        "team_a": "曼城",
        "team_b": "阿森纳",
        "scout_report": "球探情报摘要...",
        "historical_knowledge": "",
        "analysis_draft": "",
        "final_report": "",
        "fetch_errors": 0,
    }

    result = retriever_node(test_state)
    print(f"\nhistorical_knowledge 长度: {len(result['historical_knowledge'])} chars")
    if result["historical_knowledge"]:
        print(f"内容预览:\n{result['historical_knowledge'][:200]}...")
    else:
        print("（空，未找到相关知识 或 数据库未初始化）")

    print("\nRetriever Node 测试完成")