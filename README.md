# AgentTrader

一个面向 A 股的半自动选股项目：

- 使用 Tushare 拉取股票日线数据
- 用量化规则做初选（目前只实现了B1选股）
- 导出候选股票 K 线图
- 调用 Gemini 对图表进行 AI 复评打分

---

## 更新说明

- 推翻了旧版选股模式（各式各样的B1太麻烦了）
- 新加入了AI看图打分精选功能（是的，不用再自己看图了）
- 目前只支持B1选股，后续Z哥讲了砖型图10张图后，会更新砖型图精选

---

## 1. 项目流程

完整流程对应 [run_all.py](run_all.py)：

1. 下载 K 线数据（pipeline.fetch_kline）
2. 量化初选（pipeline.cli preselect）
3. 导出候选图表（dashboard/export_kline_charts.py）
4. Gemini 复评（agent/gemini_review.py）
5. 打印推荐结果（读取 suggestion.json）

输出主链路：

- data/raw：原始日线 CSV
- data/candidates：初选候选列表
- data/kline/日期：候选图表
- data/review/日期：AI 单股评分与汇总建议

---

## 2. 目录说明

- [pipeline](pipeline)：数据抓取与量化初选
- [dashboard](dashboard)：看盘界面与图表导出
- [agent](agent)：LLM 评审逻辑（Gemini）
- [config](config)：抓取、初选、Gemini 复评配置
- [data](data)：运行数据与结果
- [run_all.py](run_all.py)：全流程一键入口

补充说明：

- [config/reference_data.yaml](config/reference_data.yaml)：动态基准指数优先级和风险代理数据配置
- [config/backtest.yaml](config/backtest.yaml)：回测参数、成本和输出目录配置
- `python -m pipeline.fetch_reference_data`：参考数据入口（基准指数与风险代理）
- `python -m backtest.cli --mode quant_only`：研究闭环回测入口

---

## 3. 快速开始（一键跑通）

### 3.1 Clone 项目

~~~bash
git clone https://github.com/SebastienZh/StockTradebyZ
cd StockTradebyZ
~~~

### 3.2 安装依赖

~~~bash
uv venv -p 3.12 --clear
source .venv/bin/activate
uv pip install -r requirements.txt
~~~

Windows PowerShell:

~~~powershell
uv venv -p 3.12 --clear
.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
~~~

如需运行测试：

~~~bash
uv pip install -r requirements-dev.txt
pytest tests -v
~~~

### 3.3 设置环境变量

推荐使用配置文件（`.env`）管理密钥，在项目根目录新建 `.env`：

~~~dotenv
TUSHARE_TOKEN=你的TushareToken
GEMINI_API_KEY=你的GeminiApiKey
~~~

macOS / Linux（每次新开终端后执行一次）：

~~~bash
set -a
source .env
set +a
~~~

Windows PowerShell：

~~~powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
    [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
  }
}
~~~

`.env` 已在 `.gitignore` 中，默认不会被提交到仓库。

### 3.4 运行一键脚本

在项目根目录执行：

~~~bash
python run_all.py
~~~

常用参数：

~~~bash
python run_all.py --skip-fetch
python run_all.py --start-from 3
~~~

参数说明：

- --skip-fetch：跳过数据下载，直接进入初选
- --start-from N：从第 N 步开始执行（1 到 4）

---

## 4. 分步运行攻略

### 步骤 1：拉取 K 线

~~~bash
python -m pipeline.fetch_kline
~~~

配置见 [config/fetch_kline.yaml](config/fetch_kline.yaml)：

- start、end：抓取区间
- stocklist：股票池文件
- exclude_boards：排除板块（gem、star、bj）
- out：输出目录（默认 data/raw）
- workers：并发线程数

### 步骤 2：量化初选

~~~bash
python -m pipeline.cli preselect
~~~

可选参数示例：

~~~bash
python -m pipeline.cli preselect --date 2026-03-13
python -m pipeline.cli preselect --config config/rules_preselect.yaml --data data/raw
~~~

规则配置见 [config/rules_preselect.yaml](config/rules_preselect.yaml)。

### 步骤 3：导出候选图表

~~~bash
python dashboard/export_kline_charts.py
~~~

输出到 data/kline/选股日期，图像命名为 代码_day.jpg。

### 步骤 4：Gemini 图表复评

~~~bash
python agent/gemini_review.py
python -m agent.buy_review
python -m agent.sell_review
~~~

可选参数示例：

~~~bash
python agent/gemini_review.py --config config/gemini_review.yaml
python -m agent.buy_review --input data/candidates/candidates_latest.json
python -m agent.sell_review --config config/gemini_sell_review.yaml
python -m agent.sell_review --input data/backtest/quant_only/2026-03-17_2026-03-17/holdings_snapshot.json
~~~

配置见 [config/gemini_review.yaml](config/gemini_review.yaml) 和 [config/gemini_sell_review.yaml](config/gemini_sell_review.yaml)。

其中卖出复评的 `candidates` 参数除了支持普通候选池 JSON，也支持直接指向回测产出的 `holdings_snapshot.json`，方便把当前持仓直接送入出场评估。

读取候选与图表后，输出：

- data/review/日期/代码.json
- data/review/日期/suggestion.json
- data/review_sell/日期/代码.json
- data/review_sell/日期/suggestion.json

### 步骤 5：研究闭环回测

~~~bash
python -m backtest.cli --config config/backtest.yaml --mode quant_only --start 2026-01-01 --end 2026-01-31
python -m backtest.cli --config config/backtest.yaml --mode quant_plus_ai --start 2026-03-01 --end 2026-03-10
~~~

也可以通过统一入口转发：

~~~bash
python run_all.py backtest --mode quant_only --start 2026-01-01 --end 2026-01-31
~~~

当前回测 CLI 默认生成一份合成研究数据，用来验证“收盘出信号、次日开盘成交、输出报表与信号单”这条主链路是否通畅。输出目录默认是 `data/backtest/<mode>/<start>_<end>/`，其中包含：

- `summary.json`：快照数、成交数、平均持仓数、动态基准累计收益等摘要
- `signal_sheet.json`：次日人工执行清单，包含当前持仓、执行后持仓、风险状态、持仓天数、盈亏、目标仓位、风险摘要以及重点复核股票列表
- `signal_sheet_actions.csv`：按动作展开的一行一条执行清单，含信号日期、执行日期、风险模式、优先级分数等上下文字段，便于人工下单或导入表格复核
- `daily_snapshots.json`：逐日现金、持仓数、账户权益和基准收益明细

`summary.json` 当前会包含：

- `final_cash`：期末现金
- `ending_equity`：期末账户权益
- `total_return`：策略总收益率
- `cumulative_benchmark_return`：动态基准累计收益
- `excess_return`：策略相对动态基准的超额收益
- `max_drawdown`：基于账户权益曲线计算的最大回撤

`config/backtest.yaml` 里当前已经支持：

- `initial_cash`：回测初始现金
- `costs.commission_bps`：双边佣金
- `costs.stamp_duty_bps`：卖出印花税
- `costs.slippage_bps`：开盘成交滑点

现在的行为是：

- 如果区间内存在 `data/candidates/candidates_YYYY-MM-DD.json`，CLI 会优先读取本地历史候选文件
- `quant_plus_ai` 模式会继续尝试读取 `data/review/<pick_date>/<code>.json` 中的历史 AI 评分
- 如果存在 `data/review_sell/<pick_date>/<code>.json`，回测会把其中的 `hold/sell` 决策注入卖出路径
- 如果存在 `data/reference/index_membership.json`，股票会按 [config/reference_data.yaml](config/reference_data.yaml) 的优先级映射到主基准指数
- 如果存在 `data/reference/risk_proxies/*.csv`，回测会按 [config/reference_data.yaml](config/reference_data.yaml) 里的阈值生成 `macro_risk`
- 当系统进入 `risk_off` 时，回测现在不仅会禁止开新仓，还会按最大总暴露比例主动裁减已有持仓
- 每次回测结束后，输出目录还会写出 `holdings_snapshot.json`，可直接作为后续卖出复评或人工执行的标准化持仓输入
- 如果本地没有可用的历史候选归档，CLI 才会回退到内置 demo 数据
- 如果本地没有准备基准指数 CSV，动态基准会先用 `ALLA=0` 的兜底收益跑通主链路

---

## 5. 关键配置建议

### 6.1 抓取层

- 首次全量抓取建议 workers 设小一些（如 4 到 8）
- 若遇到频率限制，降低并发并重试

### 6.2 初选层

- top_m 决定流动性股票池大小
- b1.enabled、brick.enabled 控制策略开关
- 可先只开一个策略做回放验证

### 6.3 复评层

在 [config/gemini_review.yaml](config/gemini_review.yaml) 中可调整：

- model：模型名称
- request_delay：调用间隔（防限流）
- skip_existing：是否按缓存键断点续跑；只有 `review_type + model + 日期 + 股票 + prompt` 都一致时才复用旧结果
- suggest_min_score：推荐分数门槛

---

## 6. 输出结果解读

### 候选文件

[data/candidates/candidates_latest.json](data/candidates/candidates_latest.json)

- pick_date：选股日期
- candidates：候选列表（含 code、strategy、close 等）

### 复评汇总

data/review/日期/suggestion.json

- recommendations：最终推荐（按分数排序）
- excluded：未达门槛代码
- min_score_threshold：推荐门槛

---

## 7. 常见问题

### Q1：fetch_kline 报 token 错误

- 检查 TUSHARE_TOKEN 是否已设置
- 确认 token 有效且账号权限正常

### Q2：导出图表时报 write_image 错误

- 确认已安装 kaleido
- 重新安装：uv pip install -U kaleido

### Q3：Gemini 运行失败

- 检查 GEMINI_API_KEY 是否设置
- 观察是否命中限流，可提高 request_delay

### Q4：没有候选股票

- 检查 data/raw 是否有最新数据
- 放宽初选阈值（如 B1 或 Brick 参数）
- 检查 pick_date 是否在有效交易日

---

## License

本项目采用 [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) 协议发布。

- 允许：学习、研究、非商业用途的使用与分发
- 禁止：任何形式的商业使用、出售或以盈利为目的的部署
- 要求：转载或引用须注明原作者与来源

Copyright © 2026 SebastienZh. All rights reserved.
