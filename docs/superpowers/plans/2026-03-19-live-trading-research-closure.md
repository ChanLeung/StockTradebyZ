# 第一阶段实盘研究闭环实施计划

> **给执行型 agent：** REQUIRED：实现本计划时必须使用 `superpowers:subagent-driven-development`（若当前环境允许使用子代理）或 `superpowers:executing-plans`。所有步骤均使用复选框 `- [ ]` 语法跟踪。

**目标：** 在当前 StockTradebyZ 项目上补齐第一阶段“研究闭环 + 次日人工执行信号单”，包括卖出逻辑、双层风控、AI 出场复评、动态基准和完整历史回测。

**架构：** 保留现有 `pipeline/`、`agent/`、`dashboard/` 主入口，在此基础上新增专注职责的 `trading/` 包承载持仓、订单、组合状态、风险状态和基准映射，再新增 `backtest/` 包负责回测调度与报表。AI 评审拆成买入与卖出两套模块，面向回测的批量评审不再依赖慢速 Plotly/Kaleido 导图，而是改为缓存化的静态图渲染链路，并补上基准指数与宏观风险代理数据。

**技术栈：** Python 3.12、pandas、numpy、PyYAML、Tushare、google-genai、matplotlib/mplfinance、pytest

---

## 文件结构

### 新建

- `trading/__init__.py`：包标记
- `trading/schemas.py`：定义 `Position`、`Order`、`TradeFill`、`PortfolioState`、`RiskState`、`BenchmarkMapping`、`BacktestDailySnapshot`
- `trading/portfolio.py`：实现前 10 只等权组合构建与持仓状态迁移
- `trading/orders.py`：实现次日开盘订单生成与撮合
- `trading/risk.py`：实现个股层与组合层风险判断
- `trading/benchmark.py`：实现股票到指数的优先级映射与动态基准收益计算
- `backtest/__init__.py`：包标记
- `backtest/engine.py`：实现“收盘出信号，次日开盘成交”的日频回测主循环
- `backtest/reporting.py`：生成回测统计、日报和次日信号单
- `backtest/cli.py`：回测命令行入口
- `agent/review_types.py`：定义买入 / 卖出 AI 评审的共享结构
- `agent/buy_review.py`：买入 AI 评审执行器
- `agent/sell_review.py`：卖出 AI 评审执行器
- `agent/review_cache.py`：图表和 AI 结果磁盘缓存
- `agent/chart_renderer.py`：面向 AI 的快速静态 K 线图渲染器
- `agent/prompts/buy_prompt.md`：买入评审 prompt
- `agent/prompts/sell_prompt.md`：卖出评审 prompt
- `pipeline/fetch_reference_data.py`：抓取或读取基准指数与风险代理数据
- `pipeline/reference_io.py`：统一保存 / 加载参考数据
- `config/backtest.yaml`：回测、成本、持有期、风控参数
- `config/reference_data.yaml`：指数优先级、指数代码、风险代理配置
- `tests/conftest.py`：测试夹具与合成 OHLCV 数据构造器
- `tests/trading/test_benchmark.py`
- `tests/trading/test_orders.py`
- `tests/trading/test_portfolio.py`
- `tests/trading/test_risk.py`
- `tests/agent/test_review_cache.py`
- `tests/agent/test_chart_renderer.py`
- `tests/backtest/test_engine.py`
- `tests/backtest/test_reporting.py`
- `requirements-dev.txt`：测试环境依赖

### 修改

- `requirements.txt`：加入运行期静态图渲染依赖
- `pipeline/schemas.py`：扩展候选股可追踪字段
- `pipeline/pipeline_io.py`：保存和读取扩展候选字段
- `agent/base_reviewer.py`：沉淀买入 / 卖出评审共享逻辑
- `agent/gemini_review.py`：收窄为兼容包装器，或迁移调用到 `agent/buy_review.py`
- `dashboard/export_kline_charts.py`：与新的 AI 渲染链路职责分离
- `run_all.py`：保留现有日常跑批入口，并视情况暴露回测入口
- `README.md`：补充参考数据、回测模式、AI 缓存和次日信号单说明

## Chunk 1：基础设施与参考数据

### 任务 1：补齐测试基础设施与共享夹具

**文件：**
- 新建：`requirements-dev.txt`
- 新建：`tests/conftest.py`
- 修改：`README.md`

- [ ] **步骤 1：先写一个会失败的夹具冒烟测试**

```python
def test_price_frame_fixture_has_required_columns(price_frame):
    assert list(price_frame.columns) == ["date", "open", "close", "high", "low", "volume"]
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`pytest tests -k fixture_has_required_columns -v`  
预期：FAIL，并提示 `fixture 'price_frame' not found`

- [ ] **步骤 3：补充测试依赖和共享夹具**

```text
pytest==8.4.0
```

```python
@pytest.fixture
def price_frame():
    return build_price_frame(...)
```

- [ ] **步骤 4：再次运行测试，确认夹具已生效**

运行：`pytest tests -k fixture_has_required_columns -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add requirements-dev.txt tests/conftest.py README.md
git commit -m "test: add backtest fixture scaffold"
```

### 任务 2：建立参考数据配置与加载器

**文件：**
- 新建：`config/reference_data.yaml`
- 新建：`pipeline/reference_io.py`
- 测试：`tests/trading/test_benchmark.py`

- [ ] **步骤 1：先写一个会失败的指数优先级映射测试**

```python
def test_pick_primary_index_uses_priority_order():
    mapping = {"600000": ["CSI1000", "HS300"]}
    priority = ["HS300", "CSI500", "CSI1000", "CSI2000", "ALLA"]
    assert pick_primary_index("600000", mapping, priority) == "HS300"
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`pytest tests/trading/test_benchmark.py::test_pick_primary_index_uses_priority_order -v`  
预期：FAIL，并出现 `ImportError` 或 `NameError`

- [ ] **步骤 3：定义参考数据配置和加载函数**

```yaml
benchmark_priority:
  - HS300
  - CSI500
  - CSI1000
  - CSI2000
  - ALLA
```

```python
def load_reference_config(path: str | Path) -> dict: ...
def load_index_membership(path: str | Path) -> dict[str, list[str]]: ...
```

- [ ] **步骤 4：再次运行测试，确认优先级逻辑通过**

运行：`pytest tests/trading/test_benchmark.py -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add config/reference_data.yaml pipeline/reference_io.py tests/trading/test_benchmark.py
git commit -m "feat: add benchmark reference config"
```

### 任务 3：补齐指数与宏观风险代理数据接入

**文件：**
- 新建：`pipeline/fetch_reference_data.py`
- 修改：`README.md`
- 测试：`tests/trading/test_benchmark.py`

- [ ] **步骤 1：先写一个会失败的参考数据加载测试**

```python
def test_load_reference_series_returns_index_and_proxy_frames(tmp_path):
    result = load_reference_series(tmp_path)
    assert {"benchmarks", "risk_proxies"} <= set(result)
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`pytest tests/trading/test_benchmark.py -k reference_series -v`  
预期：FAIL，并提示缺少加载函数

- [ ] **步骤 3：实现参考数据入口**

```python
def load_reference_series(data_dir: Path) -> dict[str, pd.DataFrame]:
    return {"benchmarks": benchmarks_df, "risk_proxies": proxies_df}
```

- [ ] **步骤 4：补充 CLI 说明并验证测试通过**

运行：`pytest tests/trading/test_benchmark.py -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add pipeline/fetch_reference_data.py README.md tests/trading/test_benchmark.py
git commit -m "feat: add reference data ingestion"
```

## Chunk 2：AI 评审拆分与缓存渲染

### 任务 4：引入共享的 AI 评审结果结构

**文件：**
- 新建：`agent/review_types.py`
- 修改：`agent/base_reviewer.py`
- 测试：`tests/agent/test_review_cache.py`

- [ ] **步骤 1：先写一个会失败的买入评审解析测试**

```python
def test_parse_buy_review_keeps_total_score_and_verdict():
    parsed = parse_buy_review({...})
    assert parsed.total_score == 4.2
    assert parsed.verdict == "PASS"
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`pytest tests/agent/test_review_cache.py -k parse_buy_review -v`  
预期：FAIL，并提示缺少解析函数或类型

- [ ] **步骤 3：定义买入 / 卖出评审结构**

```python
@dataclass
class BuyReviewResult: ...

@dataclass
class SellReviewResult: ...
```

- [ ] **步骤 4：更新共享 reviewer 解析逻辑并验证测试**

运行：`pytest tests/agent/test_review_cache.py -k parse_buy_review -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add agent/review_types.py agent/base_reviewer.py tests/agent/test_review_cache.py
git commit -m "refactor: add typed ai review contracts"
```

### 任务 5：增加面向 AI 的快速静态图渲染与缓存

**文件：**
- 新建：`agent/chart_renderer.py`
- 新建：`agent/review_cache.py`
- 修改：`requirements.txt`
- 测试：`tests/agent/test_chart_renderer.py`
- 测试：`tests/agent/test_review_cache.py`

- [ ] **步骤 1：先写一个会失败的图表缓存测试**

```python
def test_render_chart_uses_cache_key(tmp_path, price_frame):
    path1 = render_review_chart(price_frame, cache_dir=tmp_path, review_type="buy")
    path2 = render_review_chart(price_frame, cache_dir=tmp_path, review_type="buy")
    assert path1 == path2
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`pytest tests/agent/test_chart_renderer.py::test_render_chart_uses_cache_key -v`  
预期：FAIL，并提示缺少渲染器

- [ ] **步骤 3：实现快速渲染器与缓存键**

```python
def render_review_chart(df: pd.DataFrame, *, cache_dir: Path, review_type: str, window: int = 120) -> Path: ...
def build_cache_key(*parts: str) -> str: ...
```

- [ ] **步骤 4：补充运行时依赖并验证测试**

运行：`pytest tests/agent/test_chart_renderer.py tests/agent/test_review_cache.py -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add requirements.txt agent/chart_renderer.py agent/review_cache.py tests/agent/test_chart_renderer.py tests/agent/test_review_cache.py
git commit -m "feat: add cached ai chart renderer"
```

### 任务 6：拆分买入评审与卖出评审

**文件：**
- 新建：`agent/buy_review.py`
- 新建：`agent/sell_review.py`
- 新建：`agent/prompts/buy_prompt.md`
- 新建：`agent/prompts/sell_prompt.md`
- 修改：`agent/gemini_review.py`
- 测试：`tests/agent/test_review_cache.py`

- [ ] **步骤 1：先写一个会失败的卖出评审契约测试**

```python
def test_sell_review_requires_hold_or_sell():
    parsed = parse_sell_review({"decision": "sell", "reasoning": "trend broken"})
    assert parsed.decision == "sell"
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`pytest tests/agent/test_review_cache.py -k sell_review_requires_hold_or_sell -v`  
预期：FAIL，并提示缺少卖出评审解析器

- [ ] **步骤 3：实现独立的买入 / 卖出评审执行器**

```python
class BuyReviewer(...): ...
class SellReviewer(...): ...
```

- [ ] **步骤 4：保留兼容入口并验证测试通过**

运行：`pytest tests/agent/test_review_cache.py -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add agent/buy_review.py agent/sell_review.py agent/prompts/buy_prompt.md agent/prompts/sell_prompt.md agent/gemini_review.py tests/agent/test_review_cache.py
git commit -m "feat: split buy and sell ai review flows"
```

## Chunk 3：交易域模型、风控与回测引擎

### 任务 7：补齐交易状态数据结构

**文件：**
- 新建：`trading/__init__.py`
- 新建：`trading/schemas.py`
- 修改：`pipeline/schemas.py`
- 修改：`pipeline/pipeline_io.py`
- 测试：`tests/trading/test_portfolio.py`

- [ ] **步骤 1：先写一个会失败的组合状态序列化测试**

```python
def test_portfolio_state_tracks_positions_and_cash():
    state = PortfolioState(cash=100000, positions=[])
    assert state.cash == 100000
    assert state.positions == []
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`pytest tests/trading/test_portfolio.py -k portfolio_state_tracks_positions_and_cash -v`  
预期：FAIL，并提示缺少 `PortfolioState`

- [ ] **步骤 3：实现核心数据结构，并扩展候选股追踪字段**

```python
@dataclass
class Position:
    code: str
    entry_date: str
    entry_price: float
    weight: float
```

- [ ] **步骤 4：再次运行测试，确认数据结构可用**

运行：`pytest tests/trading/test_portfolio.py -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add trading/__init__.py trading/schemas.py pipeline/schemas.py pipeline/pipeline_io.py tests/trading/test_portfolio.py
git commit -m "feat: add trading state dataclasses"
```

### 任务 8：实现次日开盘订单与撮合规则

**文件：**
- 新建：`trading/orders.py`
- 测试：`tests/trading/test_orders.py`

- [ ] **步骤 1：先写一组会失败的涨跌停撮合测试**

```python
def test_buy_order_skips_one_word_limit_up():
    fill = simulate_open_fill(order, open_price=10, high=10, low=10, is_limit_up=True)
    assert fill is None
```

```python
def test_sell_order_rolls_when_one_word_limit_down():
    fill = simulate_open_fill(order, open_price=8, high=8, low=8, is_limit_down=True)
    assert fill is None
```

- [ ] **步骤 2：运行测试，确认它们先失败**

运行：`pytest tests/trading/test_orders.py -v`  
预期：FAIL，并提示缺少撮合函数

- [ ] **步骤 3：实现订单生成和开盘撮合**

```python
def generate_rebalance_orders(...): ...
def simulate_open_fill(...): ...
```

- [ ] **步骤 4：再次运行测试，确认撮合逻辑通过**

运行：`pytest tests/trading/test_orders.py -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add trading/orders.py tests/trading/test_orders.py
git commit -m "feat: simulate next-open order fills"
```

### 任务 9：实现动态基准与风险状态机

**文件：**
- 新建：`trading/benchmark.py`
- 新建：`trading/risk.py`
- 测试：`tests/trading/test_benchmark.py`
- 测试：`tests/trading/test_risk.py`

- [ ] **步骤 1：先写会失败的动态基准与风险状态测试**

```python
def test_dynamic_benchmark_uses_position_weights():
    returns = compute_dynamic_benchmark_return(...)
    assert returns.loc["2026-01-02"] == pytest.approx(0.01)
```

```python
def test_risk_off_blocks_new_positions_when_proxy_breaks():
    state = evaluate_risk_state(...)
    assert state.mode == "risk_off"
    assert state.allow_new_entries is False
```

- [ ] **步骤 2：运行测试，确认它们先失败**

运行：`pytest tests/trading/test_benchmark.py tests/trading/test_risk.py -v`  
预期：FAIL，并提示缺少模块

- [ ] **步骤 3：实现基准计算器与组合风险状态机**

```python
def pick_primary_index(...): ...
def compute_dynamic_benchmark_return(...): ...
def evaluate_risk_state(...): ...
```

- [ ] **步骤 4：再次运行测试，确认逻辑通过**

运行：`pytest tests/trading/test_benchmark.py tests/trading/test_risk.py -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add trading/benchmark.py trading/risk.py tests/trading/test_benchmark.py tests/trading/test_risk.py
git commit -m "feat: add benchmark mapping and portfolio risk state"
```

### 任务 10：实现前 10 只等权组合构建

**文件：**
- 新建：`trading/portfolio.py`
- 修改：`trading/schemas.py`
- 测试：`tests/trading/test_portfolio.py`

- [ ] **步骤 1：先写一个会失败的前 10 只等权测试**

```python
def test_select_top_candidates_assigns_equal_weights():
    positions = build_target_positions(candidates, max_positions=10)
    assert len(positions) == 10
    assert {p.weight for p in positions} == {0.1}
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`pytest tests/trading/test_portfolio.py -k equal_weights -v`  
预期：FAIL，并提示缺少组合构建函数

- [ ] **步骤 3：实现目标持仓和调仓辅助逻辑**

```python
def build_target_positions(...): ...
def apply_sell_decisions(...): ...
```

- [ ] **步骤 4：再次运行测试，确认组合规则通过**

运行：`pytest tests/trading/test_portfolio.py -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add trading/portfolio.py trading/schemas.py tests/trading/test_portfolio.py
git commit -m "feat: add equal-weight portfolio construction"
```

### 任务 11：实现日频回测主循环

**文件：**
- 新建：`backtest/__init__.py`
- 新建：`backtest/engine.py`
- 新建：`config/backtest.yaml`
- 测试：`tests/backtest/test_engine.py`

- [ ] **步骤 1：先写一个会失败的单日回测集成测试**

```python
def test_engine_runs_close_to_next_open_cycle(backtest_inputs):
    result = run_backtest(backtest_inputs)
    assert len(result.daily_snapshots) >= 1
    assert result.trades
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`pytest tests/backtest/test_engine.py::test_engine_runs_close_to_next_open_cycle -v`  
预期：FAIL，并提示缺少回测引擎

- [ ] **步骤 3：实现回测编排主循环**

```python
def run_backtest(config: dict, data_bundle: dict) -> BacktestResult: ...
```

- [ ] **步骤 4：再次运行测试，确认主循环通过**

运行：`pytest tests/backtest/test_engine.py -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add backtest/__init__.py backtest/engine.py config/backtest.yaml tests/backtest/test_engine.py
git commit -m "feat: add daily backtest engine"
```

## Chunk 4：报表、CLI 与最终接线

### 任务 12：输出回测报表与次日信号单

**文件：**
- 新建：`backtest/reporting.py`
- 测试：`tests/backtest/test_reporting.py`

- [ ] **步骤 1：先写一个会失败的信号单生成测试**

```python
def test_build_signal_sheet_splits_buy_and_sell_actions(backtest_result):
    sheet = build_signal_sheet(backtest_result)
    assert {"buy_list", "sell_list"} <= set(sheet)
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`pytest tests/backtest/test_reporting.py -v`  
预期：FAIL，并提示缺少报表函数

- [ ] **步骤 3：实现统计汇总与信号单生成**

```python
def summarize_backtest(...): ...
def build_signal_sheet(...): ...
```

- [ ] **步骤 4：再次运行测试，确认报表输出通过**

运行：`pytest tests/backtest/test_reporting.py -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add backtest/reporting.py tests/backtest/test_reporting.py
git commit -m "feat: add backtest reports and signal sheet"
```

### 任务 13：增加回测 CLI 并接入现有入口

**文件：**
- 新建：`backtest/cli.py`
- 修改：`run_all.py`
- 修改：`README.md`
- 测试：`tests/backtest/test_engine.py`

- [ ] **步骤 1：先写一个会失败的 CLI 参数解析测试**

```python
def test_backtest_cli_parses_quant_plus_ai_mode():
    parser = build_parser()
    args = parser.parse_args(["--mode", "quant_plus_ai"])
    assert args.mode == "quant_plus_ai"
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`pytest tests/backtest/test_engine.py -k parses_quant_plus_ai_mode -v`  
预期：FAIL，并提示缺少 CLI 解析器

- [ ] **步骤 3：实现 CLI 与接线入口**

```python
def build_parser() -> argparse.ArgumentParser: ...
def main() -> None: ...
```

- [ ] **步骤 4：再次运行相关测试，确认接线通过**

运行：`pytest tests/backtest/test_engine.py -v`  
预期：PASS

- [ ] **步骤 5：提交本任务**

```bash
git add backtest/cli.py run_all.py README.md tests/backtest/test_engine.py
git commit -m "feat: add backtest cli and docs"
```

### 任务 14：跑完整测试并做一次样例研究运行

**文件：**
- 修改：`README.md`
- 测试：`tests/`

- [ ] **步骤 1：先跑完整测试套件**

运行：`pytest tests -v`  
预期：PASS

- [ ] **步骤 2：跑一个纯量化短区间冒烟回测**

运行：`python -m backtest.cli --config config/backtest.yaml --mode quant_only --start 2026-01-01 --end 2026-01-31`  
预期：完成运行，并产生日报与统计输出

- [ ] **步骤 3：跑一个带缓存的 AI 冒烟回测**

运行：`python -m backtest.cli --config config/backtest.yaml --mode quant_plus_ai --start 2026-03-01 --end 2026-03-10`  
预期：完成运行，写入缓存，并生成次日信号单

- [ ] **步骤 4：把最终命令与排障说明补进 README**

运行：`pytest tests -v`  
预期：PASS，文档更新不影响测试

- [ ] **步骤 5：提交本任务**

```bash
git add README.md
git commit -m "docs: finalize backtest workflow guide"
```

## 默认假设与实现约束

- 股票到指数的映射允许来自本地快照或 Tushare 导出的成员数据，第一阶段不要求实时在线查询接口。
- 海外市场和宏观风险代理若无法统一从同一数据源获取，可以先按“标准化日线 CSV 输入”接入，只要回测层读取接口保持统一即可。
- `agent/gemini_review.py` 在迁移期间可以保留为兼容包装器，但新的研究闭环代码应优先调用 `agent/buy_review.py`。
- AI 评审使用的静态图渲染应从慢速 Plotly/Kaleido 批量导图迁出；交互式 dashboard 仍可保留现有 Plotly 图。
- 第一阶段只交付研究闭环和人工执行清单，不接券商接口，不做自动下单。
