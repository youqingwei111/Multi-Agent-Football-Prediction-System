"""
MiniMax LLM 客户端 - 包含 LangChain ChatModel 适配器
用于 create_react_agent 的 model 参数
"""

import os
import json
import time
import logging
import requests
from dotenv import load_dotenv
from typing import Any

load_dotenv()
logger = logging.getLogger(__name__)

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
MODEL = os.getenv("LLM_MODEL", "MiniMax-M2")

# ===================== 基础 chat 接口（保持向后兼容） =====================


def chat(prompt: str, system_prompt: str = "你是一个专业的足球战术分析师。", max_retries: int = 3) -> str:
    """
    调用 MiniMax-M2 进行对话补全（同步简单调用）
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

            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]

            raise ValueError(f"Unexpected response structure: {data}")

        except Exception as e:
            logger.warning(f"[Attempt {attempt}/{max_retries}] MiniMax API failed: {e}")
            if attempt == max_retries:
                raise ConnectionError(f"MiniMax LLM 调用失败，已重试{max_retries}次") from e
            time.sleep(2 ** attempt)

    raise ConnectionError("MiniMax LLM 不可达")


# ===================== LangChain ChatModel 适配器 =====================


def _convert_messages(messages) -> list[dict]:
    """将 LangChain message 对象列表转换为 OpenAI 格式"""
    result = []
    for msg in messages:
        if hasattr(msg, "type"):
            if msg.type == "system":
                result.append({"role": "system", "content": msg.content})
            elif msg.type == "human":
                result.append({"role": "user", "content": msg.content})
            elif msg.type == "ai":
                result.append({"role": "assistant", "content": msg.content})
            elif msg.type == "tool":
                result.append({"role": "user", "content": f"[tool result]: {msg.content}"})
    return result


def MiniMaxChatModel(**kwargs: Any):
    """
    工厂函数：返回适配 LangChain 的 MiniMax ChatModel callable
    供 create_react_agent(model=...) 使用
    """
    model_name = kwargs.get("model_name", MODEL)
    base_url = kwargs.get("base_url", MINIMAX_BASE_URL)
    api_key = kwargs.get("api_key", MINIMAX_API_KEY)
    max_tokens = kwargs.get("max_tokens", 1024)

    def _invoke(messages: list, **call_kwargs) -> str:
        url = f"{base_url}/text/chatcompletion_v2"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        openai_messages = _convert_messages(messages)
        if not openai_messages:
            openai_messages = [{"role": "user", "content": "hello"}]

        payload = {
            "model": model_name,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "temperature": call_kwargs.get("temperature", 0.7),
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    return _invoke


# ===================== 测试入口 =====================

if __name__ == "__main__":
    # 快速连通性测试
    test_prompt = "用一句话评价曼城 vs 皇马的比赛前景。"
    try:
        result = chat(test_prompt)
        print(f"MiniMax 连通性测试成功: {result}")
    except Exception as e:
        print(f"MiniMax 连通性测试失败: {e}")