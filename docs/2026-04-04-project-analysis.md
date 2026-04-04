# 项目分析结论

更新日期：2026-04-04

基于当前仓库代码结构、配置文件、测试用例和本地验证整理。
本地测试结果：`78 passed`

## 一句话结论

这个项目本质上不是“全自动交易程序”，而是一个面向 A 股的半自动研究交易系统：

- 前半段做量化初筛
- 中间用 AI 看图复评
- 后半段生成次日执行清单和回测报表
- 真正下单目前仍然偏人工执行，不是自动报单

## 项目两条主线

### 1. 买入推荐主线

统一入口在 `run_all.py`，流程是：

1. 抓取日线数据
2. 量化初选
3. 导出 K 线图
4. AI 买入复评
5. 输出推荐结果

推荐结果最终落到：

- `data/review/<pick_date>/suggestion.json`

### 2. 研究回测主线

入口在 `backtest/cli.py`，逻辑是：

1. 读取历史候选池
2. 读取买入 AI 评分
3. 读取卖出复评
4. 加入风险信号
5. 按“收盘出信号、次日开盘成交”做模拟
6. 输出摘要、执行清单、持仓快照和 Markdown 卡片

## 关键模块分工

### 量化初选

- `pipeline/select_stock.py`
- `run_preselect()` 负责总流程
- `run_b1()` 负责 B1 策略
- `run_brick()` 负责砖型图策略

当前配置状态：

- B1 开启
- 砖型图关闭

### 图表导出

- `dashboard/export_kline_charts.py`

当前实际只导出日线图。
周线导出代码仍保留，但处于注释状态。

### AI 复评

公共框架在：

- `agent/base_reviewer.py`

作用包括：

- 读取候选池或持仓快照
- 查找本地图表
- 调用具体模型 reviewer
- 写入单股 JSON 和汇总 suggestion

### 买入复评

真实实现：

- `agent/buy_review.py`

兼容旧入口：

- `agent/gemini_review.py`

Gemini provider：

- `agent/gemini_provider.py`

OpenAI reviewer：

- `agent/openai_review.py`

买入评分聚合：

- `agent/review_types.py`

当前买入复评已经是双模型：

- Gemini：`gemini-3.1-flash-lite-preview`
- OpenAI：`gpt-5.4`
- 默认权重：`0.5 / 0.5`

### 卖出复评

当前实现：

- `agent/sell_review.py`
- `agent/openai_review.py`

当前状态：

- 已经是 Gemini + OpenAI 5.4 双模型
- 卖出主协议与买入对齐为 `total_score / verdict / signal_type / comment`
- 为兼容回测，顶层仍同步输出 `decision / reasoning / risk_flags / confidence`

### 回测与执行清单

核心执行：

- `backtest/engine.py`

报表与执行卡片：

- `backtest/reporting.py`

风险控制：

- `trading/risk.py`

目标持仓生成：

- `trading/portfolio.py`

## 当前最关键的 7 个事实

### 1. 买入链路已经完成双模型化

当前买入复评是 Gemini 和 OpenAI 5.4 共同打分，加权后输出：

- `total_score`
- `verdict`
- `signal_type`
- `comment`

### 2. 卖出链路已经完成双模型化

当前卖出复评也已经是 Gemini 和 OpenAI 5.4 共同打分，并保留了旧回测字段兼容层。

### 3. `run_all.py` 只覆盖买入推荐主线

它不是完整交易闭环入口。
卖出复评和回测都需要单独执行。

### 4. 回测优先读取本地真实历史数据，但缺数据时会回退到 demo 数据

这说明“回测能跑通”不一定等于“真实历史数据研究链路已经全部打通”。

### 5. `hold_limit_days` 目前属于配置预留项

它存在于 `config/backtest.yaml`，但当前执行逻辑里没有真正使用。

### 6. `risk_off_exposure` 目前配置和实现没有完全打通

配置文件里有该项，但当前风险逻辑里实际是硬编码 `0.5`。

### 7. 回测仓位模拟目前是简化版

虽然系统会计算目标权重，但实际买卖撮合中：

- 买入固定 `100` 股
- 卖出固定 `100` 股

当前更像研究回测骨架，而不是严格按资金和仓位约束运行的完整仿真器。

## 项目当前所处阶段

如果一句话概括：

- 量化初筛已经能用
- 买入 AI 复评已经比较成型
- 回测闭环已经能跑并能输出盘前执行材料
- 仓位 sizing、配置落地一致性，这两块还明显在持续演进

所以它现在更像一个“研究和辅助决策平台”，不是已经完全定型的交易系统。

## 建议优先级

建议后续按下面顺序推进：

1. 把回测改成按现金和目标权重真实下单，不再固定 `100` 股
2. 把 `hold_limit_days`、`risk_off_exposure` 等配置真正接入执行逻辑
3. 继续收敛旧兼容命名和旧配置文件，逐步减少 `gemini_*` 别名暴露
4. 视需要把买卖 reviewer 的 provider 封装进一步统一

## 适合继续深挖的方向

如果后续要继续分析或重构，最值得先看的模块是：

1. `agent/sell_review.py`
2. `agent/review_types.py`
3. `backtest/engine.py`
4. `trading/portfolio.py`
5. `trading/risk.py`
