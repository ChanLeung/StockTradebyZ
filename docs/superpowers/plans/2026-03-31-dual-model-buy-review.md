# 双模型买入复评 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前买入复评从 Gemini 单模型升级为 Gemini + ChatGPT 5.4 双模型 50/50 加权，同时保持现有回测和 `suggestion.json` 主读取逻辑兼容。

**Architecture:** 保留现有 Gemini provider，新增 OpenAI provider，并在买入 reviewer 中聚合两边结果。聚合结果继续写入当前 `data/review/<date>/<code>.json` 的顶层核心字段，同时增加 `model_reviews` 和 `ensemble` 元数据，避免影响下游读取逻辑。

**Tech Stack:** Python, google-genai, openai Responses API, pytest, YAML

---

## Chunk 1: 测试与配置

### Task 1: 定义双模型配置与聚合结果测试

**Files:**
- Modify: `tests/agent/test_review_types.py`
- Modify: `config/gemini_review.yaml`
- Modify: `requirements.txt`

- [ ] **Step 1: 写失败测试**

```python
def test_buy_reviewer_aggregates_gemini_and_openai_scores():
    ...
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/agent/test_review_types.py -q`

- [ ] **Step 3: 最小实现配置结构**

```yaml
providers:
  gemini:
    model: gemini-3.1-flash-lite-preview
    weight: 0.5
  openai:
    model: gpt-5.4
    weight: 0.5
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/agent/test_review_types.py -q`

## Chunk 2: OpenAI provider 与 ensemble

### Task 2: 新增 OpenAI 买入 provider

**Files:**
- Create: `agent/openai_review.py`
- Modify: `agent/gemini_review.py`
- Test: `tests/agent/test_review_types.py`

- [ ] **Step 1: 为 OpenAI provider 写失败测试**
- [ ] **Step 2: 跑失败测试**
- [ ] **Step 3: 用 Responses API 实现最小 provider**
- [ ] **Step 4: 跑测试确认通过**

### Task 3: 在买入 reviewer 中做 50/50 加权聚合

**Files:**
- Modify: `agent/buy_review.py`
- Modify: `agent/review_types.py`
- Test: `tests/agent/test_review_types.py`

- [ ] **Step 1: 写失败测试，覆盖加权分数和 PASS/WATCH/FAIL 映射**
- [ ] **Step 2: 跑失败测试**
- [ ] **Step 3: 实现最小聚合逻辑**
- [ ] **Step 4: 跑测试确认通过**

## Chunk 3: 兼容入口与验证

### Task 4: 保持旧入口可用并补文档

**Files:**
- Modify: `agent/gemini_review.py`
- Modify: `README.md`
- Test: `tests/agent/test_base_reviewer.py`

- [ ] **Step 1: 写失败测试，确认旧入口仍输出买入聚合结果**
- [ ] **Step 2: 跑失败测试**
- [ ] **Step 3: 最小改动接回旧入口**
- [ ] **Step 4: 跑相关测试**

### Task 5: 全量验证

**Files:**
- Test: `tests/agent/test_review_types.py`
- Test: `tests/agent/test_base_reviewer.py`
- Test: `tests/backtest/test_engine.py`

- [ ] **Step 1: 跑 agent 相关测试**

Run: `pytest -p no:cacheprovider tests/agent -q`

- [ ] **Step 2: 跑回测装配相关测试**

Run: `pytest -p no:cacheprovider tests/backtest/test_engine.py -q`

- [ ] **Step 3: 跑全量测试**

Run: `pytest -p no:cacheprovider tests -q`

- [ ] **Step 4: 提交代码**

```bash
git add requirements.txt config/gemini_review.yaml agent/*.py tests/agent/*.py README.md
git commit -m "功能: 买入复评接入双模型加权"
```
