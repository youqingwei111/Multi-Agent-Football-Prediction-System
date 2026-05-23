"""
RAG 入库模块
负责将战术长文进行分块、Embedding 后存入 PostgreSQL + pgvector
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine, Session, Field

load_dotenv()
logger = logging.getLogger(__name__)

# ===================== Embedding 配置 =====================

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")  # "openai" | "minimax" | "local"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 默认维度


# ===================== SQLModel 实体 =====================

def get_engine():
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        DB_HOST = os.getenv("DB_HOST", "localhost")
        DB_PORT = os.getenv("DB_PORT", "5432")
        DB_NAME = os.getenv("DB_NAME", "football_db")
        DB_USER = os.getenv("DB_USER", "postgres")
        DB_PASSWORD = os.getenv("DB_PASSWORD", "")
        DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(DATABASE_URL, echo=False)


class TacticalArticle(SQLModel, table=True):
    """战术文章向量表"""
    __tablename__ = "tactical_articles"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    content: str          # 原始文章内容（长文）
    team_tags: str        # 涉及球队，逗号分隔，如 "Manchester City,Arsenal"
    chunk_index: int = 0  # 当前块在原文中的序号
    chunk_text: str       # 当前块的内容
    embedding: str        # 向量序列化字符串，应用层自行管理


# ===================== Embedding 生成 =====================


def get_embedding(text: str) -> list[float]:
    """
    根据配置调用不同的 Embedding 模型生成向量
    """
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
    """调用 OpenAI text-embedding-3-small"""
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def _qwen_embedding(text: str) -> list[float]:
    """
    调用阿里通义千问 Embedding
    需要安装 dashscope: pip install dashscope
    """
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
        "texts": [text],
        "type": "embo",
    }
    resp = _req.post(url, headers=headers, json=payload, timeout=30)

    # ---------- 防御：校验 HTTP 状态码 ----------
    if resp.status_code != 200:
        raw = resp.text
        logger.error(f"[MiniMax Embedding] HTTP {resp.status_code} | 原始响应: {raw}")
        raise ValueError(f"MiniMax Embedding HTTP 错误 {resp.status_code}，详情已打印到日志")

    data = resp.json()

    # ---------- 防御：校验返回结构 ----------
    if "vectors" not in data:
        raw = resp.text
        logger.error(f"[MiniMax Embedding] 响应缺少 'vectors' 字段 | 原始响应: {raw}")
        raise ValueError(f"MiniMax Embedding 返回结构异常（无 vectors 字段），详情已打印到日志")

    vectors = data["vectors"]
    if not vectors or not vectors[0]:
        logger.error(f"[MiniMax Embedding] vectors 为空 | 原始响应: {data}")
        raise ValueError("MiniMax Embedding 返回空向量，详情已打印到日志")

    return vectors[0]


def _local_embedding(text: str) -> list[float]:
    """
    调用本地 sentence-transformers 模型生成向量
    首次调用时下载模型，之后直接使用本地缓存
    """
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDING_MODEL)
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


# ===================== 文本分块 =====================

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    按 tokens 分块，带一定 overlap
    使用 tiktoken 估算 tokens（近似值）
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
        # fallback: 按字符数估算（1 token ≈ 4 chars）
        enc = None

    if enc:
        tokens = enc.encode(text)
        chunks = []
        start = 0
        while start < len(tokens):
            end = start + chunk_size
            chunk_tokens = tokens[start:end]
            # 解码回文本
            chunk_text = enc.decode(chunk_tokens)
            chunks.append(chunk_text.strip())
            start = end - overlap  # overlap 防止句子截断
        return [c for c in chunks if c]
    else:
        # fallback: 按字符分割
        chars = list(text)
        chunks = []
        start = 0
        while start < len(chars):
            end = start + chunk_size * 4
            chunk = "".join(chars[start:end])
            chunks.append(chunk.strip())
            start = end - overlap * 4
        return [c for c in chunks if c]


# ===================== 余弦相似度查询（应用层实现） =====================

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度"""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def vector_to_sql(embedding: list[float]) -> str:
    """将 Python list[float] 转为 PostgreSQL 向量字符串格式"""
    return "[" + ",".join(str(x) for x in embedding) + "]"


# ===================== 入库函数 =====================

def build_table():
    """创建表（仅需运行一次）"""
    from sqlmodel import SQLModel
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    logger.info("表 tactical_articles 创建完成")


def ingest_article(
    title: str,
    content: str,
    team_tags: str,
) -> int:
    """
    将一篇战术长文分块、Embedding 后入库
    返回入库 chunk 数量
    """
    from sqlmodel import Session
    engine = get_engine()
    chunks = chunk_text(content)

    ingested = 0
    with Session(engine) as session:
        for i, chunk in enumerate(chunks):
            embedding = get_embedding(chunk)
            article = TacticalArticle(
                title=title,
                content=content,       # 保留原文
                team_tags=team_tags,    # 复制到每条 chunk
                chunk_index=i,
                chunk_text=chunk,
                embedding=vector_to_sql(embedding),
            )
            session.add(article)
            ingested += 1
        session.commit()
    logger.info(f"入库完成: {title}，共 {ingested} 个 chunk")
    return ingested


# ===================== 查询函数（入库后检索用） =====================

def search_similar_chunks(
    query_embedding: list[float],
    team_filter: str,
    top_k: int = 3,
) -> list[dict]:
    """
    在数据库中检索与 query_embedding 余弦相似度最高的 top_k 条 chunk
    team_filter: 逗号分隔的球队名，如 "Manchester City,Arsenal"
    """
    from sqlmodel import Session, select
    from sqlalchemy import or_

    engine = get_engine()
    with Session(engine) as session:
        # 取出所有 team_tags 包含 filter 的记录
        tags = [t.strip() for t in team_filter.split(",")]
        conditions = [TacticalArticle.team_tags.contains(t) for t in tags]
        query = select(TacticalArticle).where(or_(*conditions))
        results = session.exec(query).all()

    # 应用层计算余弦相似度并排序
    scored = []
    for row in results:
        import json
        emb = json.loads(row.embedding)
        score = cosine_similarity(query_embedding, emb)
        scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "title": row.title,
            "chunk_text": row.chunk_text,
            "score": score,
        }
        for score, row in scored[:top_k]
    ]


# ===================== 测试入口 =====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # 1. 建表
    build_table()

    # 2. 模拟一篇"曼城破高位逼抢"战术长文
    sample_article = """
    标题：曼城破高位逼抢：战术深度复盘

    瓜迪奥拉的曼城在面对对手高位逼抢时，展现出教科书级别的破密防策略。
    本文通过 2024-2025 赛季多场关键比赛，深度拆解曼城如何通过短传三角、中场后撤
    和边后卫内收三种手段瓦解对手的高位压迫。

    一、短传三角体系
    曼城在持球阶段经常构建德布劳内-Rodri-Bernardo 的短传三角，
    通过快速的三角传递拉扯对手中场线，迫使对手暴露空档。

    二、Rodri 回撤接应
    当对手高位逼抢强度提升时，Rodri 会主动回撤到两名中卫之间，
    形成三中卫出球结构，瞬间瓦解对手的前场压迫。

    三、边后卫内收
    Walker 和 Gvardiol 在特定场景下会内收至中场线，
    增加中场接球点数，同时为边路进攻拉开宽度。

    这套体系的核心在于球员的多位置能力和极高足球智商，
    历史上很少有球队能持续做到这一点。
    """

    count = ingest_article(
        title="曼城破高位逼抢：战术深度复盘",
        content=sample_article.strip(),
        team_tags="Manchester City",
    )
    print(f"入库 chunk 数量: {count}")

    # 3. 简单检索验证
    query_emb = get_embedding("Manchester City high press tactical analysis")
    results = search_similar_chunks(query_emb, "Manchester City", top_k=2)
    print("\n检索结果:")
    for r in results:
        print(f"  [{r['score']:.4f}] {r['title']} - {r['chunk_text'][:80]}...")

    print("\n入库测试完成 OK")