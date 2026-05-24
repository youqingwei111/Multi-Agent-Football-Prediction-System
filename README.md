# 欧洲足球智能分析 Multi-Agent 系统

## 项目简介

一款基于大语言模型（LLM）与图状态机（Graph State Machine）的多 Agent 协作应用。系统模拟专业分析团队工作流，自动化完成外部赛事数据抓取、战术逻辑推演及最终排版。

## 技术栈

Vue3, TailwindCSS, FastAPI, LangGraph, Python, PostgreSQL, SQLModel

## 核心架构

### LangGraph 多节点流水线

```
球探(Scout) → 情报检索(Retriever) → 战术分析师(Analyst) → 主编(Editor)
```

- **球探节点**：调用外部体育 API 获取球队战绩、伤停、赔率数据，单节点内实现重试与降级（最大重试 3 次）
- **情报检索节点**：基于 PostgreSQL + pgvector 向量数据库，检索历史战术文章作为补充上下文
- **战术分析师节点**：基于 LLM 推理，结合实时数据与历史知识生成分析草稿
- **主编节点**：将分析草稿排版为标准 Markdown 报告

### 工程鲁棒性

- 节点级异常捕获与降级机制：数据抓取失败时返回空数据，不阻断后续链路
- Fallback 节点设计：主节点失败后自动切换至备用方案，保证服务可用性

### 异步非阻塞接口

- FastAPI 异步后端 + Vue3 前端
- Server-Sent Events 流式响应，实时推送 Agent 运行节点与状态

### 全链路状态持久化

- 每次完整运行的中间态快照（含原始数据、推理草稿、报错计数、运行时间戳）持久化至 PostgreSQL
- 支持 AI 思考全流程可追溯，为 Prompt 调优提供数据支撑