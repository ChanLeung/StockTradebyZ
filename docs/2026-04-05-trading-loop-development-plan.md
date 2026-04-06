# 交易闭环与分散化约束实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前研究回测链路升级为“AI 驱动买卖 + 持仓专属卖出复评 + 分散化约束 + 可留现金”的真实交易闭环。

**Architecture:** 保留现有 `candidates -> buy_review -> backtest -> signal_sheet` 主链路，在回测和信号单层补齐持仓专属卖出复评、指数/行业分散化约束、替换逻辑和 AI-only 使用方式。优先复用已有 `buy_review`、`sell_review`、`review_types`、`portfolio`、`engine`、`reporting` 模块，只在必要处新增配置和测试，不做无关重构。

**Tech Stack:** Python 3.12、Pytest、YAML 配置、Gemini/OpenAI 双模型 reviewer、现有本地 JSON/CSV 数据目录。

---

## 目标范围

本计划解决以下问题：

1. 卖出复评只对当前持仓生效。
2. 买入只允许 `buy_review = PASS`。
3. 卖出规则改成：
   - `sell PASS`：次日开盘卖出
   - `sell WATCH`：进入可替换池
   - `sell FAIL`：继续持有
4. 卖出后补仓时，只从 `buy PASS` 且满足分散化约束的股票中补位。
5. 限制同指数、同一级行业的持仓集中度。
6. 对外工作流以 AI-only 为主，`quant_only` 降级为内部调试能力。
7. 信号单和回测输出能解释“为什么买、为什么没买、为什么替换”。

## 非目标

- 本轮不处理券商自动下单。
- 本轮不做分钟级回测。
- 本轮不做复杂相关性优化和均值方差组合优化。
- 本轮不彻底删除 `quant_only` 内部实现，只调整为非主流程。
- 本轮不重做整套仓位资金分配引擎，但会为后续真实资金等权预留接口。

## 规则冻结

本计划按以下业务规则实施：

- 最大持仓数：`10`
- 买入门槛：`buy_review = PASS`
- 卖出门槛：`sell_review = PASS`
- `sell WATCH`：不立即卖出，但可被更优新票替换
- `sell FAIL`：继续持有
- 同一主指数最多持有：`4` 只
- 同一一级行业最多持有：`2` 只
- `risk_off`：禁止开新仓
- 允许留现金，不强行补满到 10 只
- 禁止同一只股票当天卖出后又买回

## 文件边界

### 核心修改文件

- `backtest/cli.py`
  - 负责装配本地回测输入
  - 需要确保卖出复评只读取持仓快照，而不是泛候选池
  - 需要调整 AI-only 工作流默认模式和提示

- `backtest/engine.py`
  - 负责信号日到交易日的主循环
  - 需要补强“先卖后补、可替换池、禁止卖出后买回、空仓保留”规则

- `trading/portfolio.py`
  - 负责构建目标持仓、分散化过滤、替换逻辑
  - 需要新增指数/行业约束和替换排序逻辑

- `trading/risk.py`
  - 负责 `risk_off` 判定
  - 需要保持现有逻辑，但确认和开新仓规则完全打通

- `backtest/reporting.py`
  - 负责信号单、Markdown 摘要、CSV
  - 需要补充“被约束拒绝的买入候选”“被替换持仓”“留现金原因”

- `agent/sell_review.py`
  - 负责卖出复评输出结构
  - 需要确认生成结果能稳定支撑 `sell PASS / WATCH / FAIL`

- `agent/review_types.py`
  - 负责买卖评分映射、聚合和决策语义
  - 需要显式固化卖出 `PASS/WATCH/FAIL -> decision`

- `config/backtest.yaml`
  - 新增或收敛组合约束配置

### 建议新增文件

- `tests/trading/test_portfolio_constraints.py`
  - 测分散化约束、补仓筛选、替换顺序

- `tests/backtest/test_signal_rotation.py`
  - 测完整交易循环：卖出、补仓、禁止买回、空仓保留

- `tests/backtest/test_reporting_constraints.py`
  - 测信号单里新的解释字段

## Chunk 1: 冻结买卖语义与配置入口

### Task 1: 固化卖出决策语义

**Files:**
- Modify: `agent/review_types.py`
- Test: `tests/agent/test_review_types.py`

- [ ] **Step 1: 写失败测试，锁定卖出语义**

新增测试覆盖：

```python
def test_sell_pass_maps_to_sell():
    assert map_sell_verdict_to_decision("PASS") == "sell"


def test_sell_watch_maps_to_hold():
    assert map_sell_verdict_to_decision("WATCH") == "hold"


def test_sell_fail_maps_to_hold():
    assert map_sell_verdict_to_decision("FAIL") == "hold"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/agent/test_review_types.py -q`

- [ ] **Step 3: 实现最小修复**

在 `agent/review_types.py` 中确认并注释卖出语义：
- `PASS -> sell`
- `WATCH -> hold`
- `FAIL -> hold`

- [ ] **Step 4: 重新跑测试**

Run: `pytest tests/agent/test_review_types.py -q`

- [ ] **Step 5: 提交**

```bash
git add agent/review_types.py tests/agent/test_review_types.py
git commit -m "功能: 固化卖出复评决策语义"
```

### Task 2: 收敛回测配置为 AI-only 主流程

**Files:**
- Modify: `config/backtest.yaml`
- Modify: `backtest/cli.py`
- Modify: `README.md`
- Test: `tests/backtest/test_cli.py`

- [ ] **Step 1: 写失败测试**

覆盖以下行为：
- 默认模式为 `quant_plus_ai`
- CLI 帮助说明把 `quant_only` 标成内部调试用途

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backtest/test_cli.py -q`

- [ ] **Step 3: 最小实现**

调整：
- `backtest.cli` 默认模式改为 `quant_plus_ai`
- `quant_only` 仍保留 choices，但在 help/README 中标成内部调试

- [ ] **Step 4: 跑测试**

Run: `pytest tests/backtest/test_cli.py -q`

- [ ] **Step 5: 提交**

```bash
git add config/backtest.yaml backtest/cli.py README.md tests/backtest/test_cli.py
git commit -m "功能: 调整回测为AI优先工作流"
```

## Chunk 2: 实现持仓专属卖出复评与补仓主循环

### Task 3: 卖出复评只对持仓股票执行

**Files:**
- Modify: `backtest/cli.py`
- Modify: `trading/holdings_io.py`
- Test: `tests/backtest/test_signal_rotation.py`

- [ ] **Step 1: 写失败测试**

测试目标：
- 当天不在持仓中的股票，即便存在 `review_sell/<date>/<code>.json`，也不应进入卖出决策
- 当天在持仓中的股票，即便不在候选池里，也应继续读取卖出复评

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backtest/test_signal_rotation.py -q`

- [ ] **Step 3: 最小实现**

在回测 bundle 装配里引入“持仓驱动的卖出复评读取”：
- 优先读取 `holdings_snapshot`
- 对 snapshot 中的代码逐只查找卖出复评
- 不再用候选池顺手带卖出复评

- [ ] **Step 4: 跑测试**

Run: `pytest tests/backtest/test_signal_rotation.py -q`

- [ ] **Step 5: 提交**

```bash
git add backtest/cli.py trading/holdings_io.py tests/backtest/test_signal_rotation.py
git commit -m "功能: 卖出复评仅针对当前持仓"
```

### Task 4: 禁止卖出后同日买回

**Files:**
- Modify: `backtest/engine.py`
- Modify: `trading/portfolio.py`
- Test: `tests/backtest/test_signal_rotation.py`

- [ ] **Step 1: 写失败测试**

覆盖：
- 某股票当天触发卖出后，即使它也在新的 `buy PASS` 候选池里，也不能再次买回

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backtest/test_signal_rotation.py -q`

- [ ] **Step 3: 最小实现**

在主循环里维护一个 `sold_today_codes` 集合，并在买入筛选时排除。

- [ ] **Step 4: 跑测试**

Run: `pytest tests/backtest/test_signal_rotation.py -q`

- [ ] **Step 5: 提交**

```bash
git add backtest/engine.py trading/portfolio.py tests/backtest/test_signal_rotation.py
git commit -m "功能: 禁止同日卖出后买回"
```

### Task 5: 允许空仓，不强行补满

**Files:**
- Modify: `backtest/engine.py`
- Modify: `trading/portfolio.py`
- Test: `tests/backtest/test_signal_rotation.py`

- [ ] **Step 1: 写失败测试**

覆盖：
- 卖出后如果只有 2 只新的 `buy PASS`，最终持仓应少于 10，只补这 2 只

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backtest/test_signal_rotation.py -q`

- [ ] **Step 3: 最小实现**

补仓逻辑改为：
- 只遍历通过规则的 `buy PASS`
- 不足时停止
- 不生成凑数买单

- [ ] **Step 4: 跑测试**

Run: `pytest tests/backtest/test_signal_rotation.py -q`

- [ ] **Step 5: 提交**

```bash
git add backtest/engine.py trading/portfolio.py tests/backtest/test_signal_rotation.py
git commit -m "功能: 支持不补满持仓并保留现金"
```

## Chunk 3: 实现组合分散化约束

### Task 6: 加入主指数持仓上限

**Files:**
- Modify: `trading/portfolio.py`
- Modify: `config/backtest.yaml`
- Test: `tests/trading/test_portfolio_constraints.py`

- [ ] **Step 1: 写失败测试**

覆盖：
- 候选里即使前 6 名都属于同一主指数，也最多只能选前 4 只

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/trading/test_portfolio_constraints.py -q`

- [ ] **Step 3: 最小实现**

新增组合约束函数，例如：

```python
def within_index_limit(code, stock_to_index, current_counts, max_same_index):
    ...
```

并把它接入 `build_target_positions` 或新的候选筛选函数。

- [ ] **Step 4: 跑测试**

Run: `pytest tests/trading/test_portfolio_constraints.py -q`

- [ ] **Step 5: 提交**

```bash
git add trading/portfolio.py config/backtest.yaml tests/trading/test_portfolio_constraints.py
git commit -m "功能: 增加主指数分散化约束"
```

### Task 7: 加入一级行业持仓上限

**Files:**
- Modify: `pipeline/reference_io.py`
- Modify: `trading/portfolio.py`
- Modify: `backtest/cli.py`
- Test: `tests/trading/test_portfolio_constraints.py`

- [ ] **Step 1: 写失败测试**

覆盖：
- 同一一级行业最多 2 只
- 如果行业映射缺失，策略能优雅降级，只应用指数约束

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/trading/test_portfolio_constraints.py -q`

- [ ] **Step 3: 最小实现**

引入 `stock_to_industry`：
- 本地有映射就启用
- 没有映射就跳过行业限制

- [ ] **Step 4: 跑测试**

Run: `pytest tests/trading/test_portfolio_constraints.py -q`

- [ ] **Step 5: 提交**

```bash
git add pipeline/reference_io.py trading/portfolio.py backtest/cli.py tests/trading/test_portfolio_constraints.py
git commit -m "功能: 增加行业分散化约束"
```

### Task 8: 实现 WATCH 可替换池

**Files:**
- Modify: `trading/portfolio.py`
- Modify: `backtest/engine.py`
- Test: `tests/backtest/test_signal_rotation.py`

- [ ] **Step 1: 写失败测试**

覆盖：
- `sell FAIL` 持仓不会被替换
- `sell WATCH` 持仓可以被更高质量的 `buy PASS` 替换
- 每日替换上限生效

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backtest/test_signal_rotation.py -q`

- [ ] **Step 3: 最小实现**

新增替换排序：
- 先按卖出总分降序
- 再按风险标签数量降序
- 再按持仓天数降序

只允许：
- 新票 `buy PASS`
- 老票 `sell WATCH`

- [ ] **Step 4: 跑测试**

Run: `pytest tests/backtest/test_signal_rotation.py -q`

- [ ] **Step 5: 提交**

```bash
git add trading/portfolio.py backtest/engine.py tests/backtest/test_signal_rotation.py
git commit -m "功能: 增加WATCH持仓替换机制"
```

## Chunk 4: 解释性输出与验收

### Task 9: 信号单输出约束拒绝原因和留现金原因

**Files:**
- Modify: `backtest/reporting.py`
- Test: `tests/backtest/test_reporting_constraints.py`

- [ ] **Step 1: 写失败测试**

覆盖输出字段：
- `buy_candidates_rejected_by_index_limit`
- `buy_candidates_rejected_by_industry_limit`
- `replaceable_watch_list`
- `cash_reserved_reason`

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backtest/test_reporting_constraints.py -q`

- [ ] **Step 3: 最小实现**

在 `signal_sheet.json`、Markdown 摘要、CSV 中补充上述解释字段。

- [ ] **Step 4: 跑测试**

Run: `pytest tests/backtest/test_reporting_constraints.py -q`

- [ ] **Step 5: 提交**

```bash
git add backtest/reporting.py tests/backtest/test_reporting_constraints.py
git commit -m "功能: 信号单增加约束拒绝与留现金原因"
```

### Task 10: 做一轮端到端验收

**Files:**
- Modify: `README.md`
- Modify: `docs/2026-04-04-project-analysis.md`
- Test: `tests/backtest/test_engine.py`
- Test: `tests/backtest/test_signal_rotation.py`
- Test: `tests/trading/test_portfolio_constraints.py`
- Test: `tests/backtest/test_reporting_constraints.py`

- [ ] **Step 1: 补验收说明**

在 README 和分析文档里更新：
- 当前默认回测模式
- 买卖语义
- 分散化约束
- 空仓保留规则

- [ ] **Step 2: 跑完整测试**

Run:

```bash
pytest tests/agent/test_review_types.py -q
pytest tests/trading/test_portfolio_constraints.py -q
pytest tests/backtest/test_signal_rotation.py -q
pytest tests/backtest/test_reporting_constraints.py -q
pytest tests/backtest/test_engine.py -q
pytest tests -q
```

Expected:
- 全绿
- 没有因为 `quant_only` 降级而破坏现有 AI 主流程

- [ ] **Step 3: 做一次真实区间 smoke test**

Run:

```bash
python -m backtest.cli --config config/backtest.yaml --mode quant_plus_ai --start 2026-03-16 --end 2026-03-17
```

Expected:
- 能输出 summary / signal_sheet / brief
- 信号单能体现约束拒绝和补仓不足原因

- [ ] **Step 4: 提交**

```bash
git add README.md docs/2026-04-04-project-analysis.md
git add tests/backtest/test_engine.py tests/backtest/test_signal_rotation.py
git add tests/trading/test_portfolio_constraints.py tests/backtest/test_reporting_constraints.py
git commit -m "文档: 更新AI交易闭环与分散化约束说明"
```

## 交付验收标准

满足以下条件才算本计划完成：

- 卖出复评只作用于当前持仓
- 买入只允许 `PASS`
- `sell PASS / WATCH / FAIL` 语义完整打通
- 同一主指数上限生效
- 同一一级行业上限生效或优雅降级
- 卖出后不会同日买回
- 可替换池只允许替换 `WATCH` 老仓，不替换 `FAIL`
- 不足额补仓时系统保留现金，不乱买
- 信号单能说明“为什么没买”“为什么替换”“为什么留现金”
- 相关测试和 smoke test 全部通过

## 执行建议

建议执行顺序不要打乱：

1. 先冻结卖出语义
2. 再改主循环
3. 再加分散化约束
4. 最后补输出解释和文档

这样最容易在每个阶段都保持系统可运行、可验证、可回滚。
