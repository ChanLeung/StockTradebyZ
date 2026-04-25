# run_all.py 完整交易闭环入口设计

日期：2026-04-25

## 背景

当前 `run_all.py` 已经能完成买入推荐主线：

1. 拉取最新 K 线数据。
2. 执行量化初选。
3. 导出候选股 K 线图。
4. 执行买入双模型复评。
5. 打印买入推荐。

但它还不是完整交易闭环入口。卖出复评、持仓处理、次日执行信号单和研究回测仍需要手工分段调用。目标是把 `python run_all.py` 升级为日常交易闭环入口，同时保留 `python run_all.py backtest ...` 作为历史研究入口。

## 目标

默认执行：

```bash
python run_all.py
```

应完成一条日常交易闭环：

1. 更新行情。
2. 生成最新候选池。
3. 生成候选 K 线图。
4. 运行买入 AI 复评。
5. 打印买入推荐。
6. 定位当前持仓快照。
7. 对当前持仓运行卖出 AI 复评。
8. 生成次日执行信号单。
9. 打印执行卡片路径和重点动作摘要。

历史回测仍通过子命令执行：

```bash
python run_all.py backtest --start 2025-09-01 --end 2025-12-19
```

## 非目标

- 不接入券商自动下单。
- 不处理委托状态、撤单、成交回报和部分成交。
- 不重写回测引擎。
- 不批量补跑历史 AI 复评。
- 不删除 `quant_only`，它继续作为内部调试模式保留。

## 命令行接口

保留现有参数：

```bash
python run_all.py --skip-fetch
python run_all.py --start-from 3
python run_all.py backtest --start 2025-09-01 --end 2025-12-19
```

新增参数：

```bash
python run_all.py --holdings data/backtest/.../holdings_snapshot.json
python run_all.py --skip-sell-review
python run_all.py --skip-backtest-signal
python run_all.py --allow-empty-holdings
```

参数语义：

- `--holdings`：指定当前持仓快照，供卖出复评使用。
- `--skip-sell-review`：只做买入推荐，不执行卖出复评。
- `--skip-backtest-signal`：只跑买卖复评，不生成次日执行信号单。
- `--allow-empty-holdings`：没有持仓快照时允许继续，不把缺持仓视为错误。

默认行为：

- 未指定 `--holdings` 时，自动查找最近的 `data/backtest/**/holdings_snapshot.json`。
- 找不到持仓快照时，按空仓处理并跳过卖出复评。
- 第一次运行项目时允许空仓，不应阻断买入推荐。

## 持仓快照定位规则

按以下优先级定位持仓：

1. 命令行 `--holdings` 指定的文件。
2. 最近修改的 `data/backtest/**/holdings_snapshot.json`。
3. 找不到时返回空仓状态。

如果用户显式传入 `--holdings`，但文件不存在或格式错误，应立即失败并提示具体路径。

如果用户没有传入 `--holdings`，且自动查找不到持仓，应继续运行，但打印清晰提示：

```text
[WARN] 未找到持仓快照，本次跳过卖出复评，仅生成买入建议和空仓信号单。
```

## 日常闭环流程

### Step 1：行情更新

命令：

```bash
python -m pipeline.fetch_kline
```

受 `--skip-fetch` 和 `--start-from` 控制。

### Step 2：量化初选

命令：

```bash
python -m pipeline.cli preselect
```

输出：

- `data/candidates/candidates_latest.json`
- `data/candidates/candidates_<pick_date>.json`

### Step 3：导出买入候选 K 线图

命令：

```bash
python dashboard/export_kline_charts.py
```

输出：

- `data/kline/<pick_date>/<code>_day.jpg`

### Step 4：买入复评

命令：

```bash
python -m agent.buy_review
```

输出：

- `data/review/<pick_date>/<code>.json`
- `data/review/<pick_date>/suggestion.json`

买入复评继续使用配置文件中的失败重试策略。

### Step 5：打印买入推荐

读取：

- `data/review/<pick_date>/suggestion.json`

打印 PASS 推荐列表和模型分数。

### Step 6：卖出复评

如果存在持仓快照且未指定 `--skip-sell-review`，执行：

```bash
python -m agent.sell_review --input <holdings_snapshot>
```

卖出复评只针对持仓股票，不对当天候选池执行。

如果没有持仓快照，跳过卖出复评。

### Step 7：生成次日执行信号单

默认用 `candidates_latest.json` 的 `pick_date` 作为信号日：

```bash
python -m backtest.cli --mode quant_plus_ai --start <pick_date> --end <pick_date>
```

输出：

- `data/backtest/quant_plus_ai/<pick_date>_<pick_date>/summary.json`
- `data/backtest/quant_plus_ai/<pick_date>_<pick_date>/signal_sheet.json`
- `data/backtest/quant_plus_ai/<pick_date>_<pick_date>/signal_sheet_brief.md`
- `data/backtest/quant_plus_ai/<pick_date>_<pick_date>/holdings_snapshot.json`

### Step 8：打印执行摘要

读取 `signal_sheet_brief.md`，打印：

- 信号日期。
- 执行日期。
- 风险模式。
- 当前持仓数到目标持仓数。
- Top 重点动作。
- 文件路径。

## 数据流

```text
data/raw
  -> data/candidates/candidates_latest.json
  -> data/kline/<pick_date>/*.jpg
  -> data/review/<pick_date>/*.json
  -> data/review_sell/<pick_date>/*.json
  -> data/backtest/quant_plus_ai/<pick_date>_<pick_date>/*
```

`run_all.py` 只负责编排，不直接解析模型结果，不直接做交易决策。交易决策继续由 `agent.*`、`backtest.cli`、`trading.*` 模块负责。

## 错误处理

### 可继续的情况

- 没有持仓快照：跳过卖出复评。
- 空仓：继续生成买入建议和信号单。
- 没有 PASS 买入：继续生成空仓或保留现金信号单。
- 买入复评个别股票失败：沿用买入复评的重试和跳过机制。

### 应失败的情况

- 显式传入的 `--holdings` 文件不存在。
- 显式传入的 `--holdings` 文件格式不是持仓快照。
- `candidates_latest.json` 缺失或没有 `pick_date`。
- 买入复评没有任何可用结果。
- 生成信号单时缺少本地真实候选文件。

### demo fallback 保护

`run_all.py` 的日常闭环入口不应静默使用回测 demo 数据。

如果 `backtest.cli` 因本地候选缺失回退到 demo 数据，日常闭环应把它视为失败或打印强警告。推荐实现是在 `run_all.py` 调用回测前先确认：

- `data/candidates/candidates_<pick_date>.json` 存在。
- `data/review/<pick_date>/suggestion.json` 存在。

这样可以避免用户误把 demo 回测当作真实执行信号。

## 测试计划

新增或调整测试覆盖：

1. `run_all.py --help` 展示新参数。
2. `python run_all.py backtest ...` 仍按原样转发到 `backtest.cli`。
3. 没有持仓快照时，默认跳过卖出复评。
4. 显式传入 `--holdings` 时，会调用 `agent.sell_review --input <path>`。
5. 指定 `--skip-sell-review` 时，不调用卖出复评。
6. 指定 `--skip-backtest-signal` 时，不调用回测信号单。
7. 买入复评完成后，会用 `pick_date` 调用 `backtest.cli --mode quant_plus_ai --start <pick_date> --end <pick_date>`。
8. `candidates_latest.json` 缺少 `pick_date` 时，流程失败并给出中文错误。

## 验收标准

命令：

```bash
python run_all.py --skip-fetch
```

应能在已有行情数据的情况下完成日常闭环，并打印：

- 买入推荐。
- 是否执行卖出复评。
- 执行卡片路径。
- 次日重点动作摘要。

命令：

```bash
python run_all.py backtest --start 2025-09-01 --end 2025-09-05
```

应保持现有历史研究入口行为不变。

测试命令：

```bash
python -m pytest -q
```

应全部通过。

## 后续可选增强

- 为卖出复评默认增加失败重试轮次。
- 增加 `run_all.py review-sell --holdings ...` 独立子命令。
- 增加历史区间 AI 复评补跑编排。
- 在执行卡片中输出更短的盘前人工下单清单。
- 在回测 CLI 中增加显式 `--no-demo-fallback` 参数，进一步降低误用风险。
