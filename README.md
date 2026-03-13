# Solana RSI 发现与信号程序（CoinGecko Pro Onchain）

本程序**不负责实际下单交易**。它负责：

1. 每 15 分钟扫描并发现适合交易的币
2. 生成并更新白名单（默认保留前 40，可配）
3. 监控 K 线并跑 RSI 信号策略（5m 主周期）
4. 通过 webhook 发送买卖信号
5. 币种退出白名单时，优先发送 SELL 退出信号
6. Dashboard 可视化白名单状态

## 功能概览

- 数据源：CoinGecko Pro Onchain（GeckoTerminal 数据）
- 候选来源：`trending_pools`、`new_pools`、`megafilter`
- 硬过滤：仅保留 FDV 50,000~5,000,000、LP>50,000、24h成交额>300,000、池龄>48h
- 白名单规则：默认保留前 `40`（`TOP_N` 默认值，可调整）
- 白名单输出：`whitelist.json`
- 信号输出：基于 RSI 的 BUY/SELL webhook 消息（仅信号，不交易）
- 开单条件：15m K线下 EMA9 > EMA20 才允许 BUY
- 15 分钟周期更新：退出白名单的币会优先发送 `SELL + EXIT_WHITELIST`

## CLI

- 启动 Dashboard：

```bash
DASHBOARD_PORT=4173 npm run run:dashboard
```


- 生成白名单：

```bash
GECKO_API_KEY=your_key npm run build:whitelist
```

- 读取白名单（给下游程序直接消费）：

```bash
npm run read:whitelist
```

- 扫描 K 线并发 webhook 信号：

```bash
GECKO_API_KEY=your_key SIGNAL_AGGREGATE=5 TREND_AGGREGATE=15 WEBHOOK_URL=https://your-webhook.endpoint npm run run:signals
```

- 运行回测/盈亏统计（按每次 BUY=1 SOL，可连续加仓 1 SOL）：

```bash
npm run run:backtest
```

- 每 15 分钟完整周期（更新白名单 + 退出币优先发 SELL）：

```bash
GECKO_API_KEY=your_key WEBHOOK_URL=https://your-webhook.endpoint npm run run:cycle
```

## 主要环境变量（白名单构建）

- `TOP_N`（默认 `40`）
- `MIN_POOL_AGE_HOURS`（默认 `48`）
- `MAX_POOL_AGE_HOURS`（默认 `Infinity`，默认不启用池龄上限）
- `MIN_LIQUIDITY_USD`（默认 `50000`）
- `MIN_VOLUME_24H_USD`（默认 `300000`）
- `MIN_FDV_USD`（默认 `50000`）
- `MAX_FDV_USD`（默认 `Infinity`，默认不启用）
- `MIN_VOLUME_LIQUIDITY_RATIO`（默认 `3`）
- `MIN_AVG_RANGE_5M`（默认 `0.025`）
- `MIN_RSI_SWING`（默认 `28`）
- `MIN_REVERSALS_5M`（默认 `6`）
- `MIN_P90_RANGE_PCT_5M`（默认 `0.03`）
- `MIN_AVG_RANGE_1M`（默认 `0`，可选 1m 振幅过滤，建议从 `0.012` 开始）
- `FILTER_DEBUG`（默认 `false`，开启后输出各过滤条件淘汰计数，便于定位“只筛到少量币”的瓶颈）
- 指标处理：除上述4个基础条件外，其它指标不做硬过滤，仅用于 Volatility Score 排名
- 其他：`GECKO_API_KEY`、`GECKO_AUTH_MODE`、`NETWORK`、`OUTPUT_PATH`、`BLACKLIST_MINTS`、`QUOTE_MINT`

## 主要环境变量（信号 / 周期）

- `WHITELIST_PATH`（默认 `whitelist.json`）
- `SIGNAL_TIMEFRAME`（默认 `minute`）
- `SIGNAL_AGGREGATE`（默认 `5`，即 5m 主策略 K 线）
- `SIGNAL_LIMIT`（默认 `120`）
- `TREND_TIMEFRAME`（默认 `minute`）
- `TREND_AGGREGATE`（默认 `15`，开单过滤 K 线）
- `TREND_LIMIT`（默认 `120`）
- `ENTRY_EMA_FAST`（默认 `9`）
- `ENTRY_EMA_SLOW`（默认 `20`）
- `RSI_PERIOD`（默认 `14`）
- `RSI_OVERSOLD`（默认 `30`）
- `RSI_OVERBOUGHT`（默认 `70`）
- `WEBHOOK_URL`（买卖信号接收地址）
- `WEBHOOK_AUTH_HEADER` / `WEBHOOK_AUTH_TOKEN`（可选 webhook 鉴权）
- `DRY_RUN=true`（只输出信号，不发送 webhook）
- `SIGNAL_LOG_PATH`（默认 `signal-events.jsonl`，记录所有信号发送结果）

## OpenClaw 部署建议

1. 每 15 分钟运行一次完整周期：

```bash
*/15 * * * * cd /path/to/searchcoin && GECKO_API_KEY=xxx WEBHOOK_URL=https://xxx /usr/bin/env npm run run:cycle
```

2. 可选：更高频运行 RSI 监控（例如 5 分钟一次）

```bash
*/5 * * * * cd /path/to/searchcoin && GECKO_API_KEY=xxx WEBHOOK_URL=https://xxx /usr/bin/env npm run run:signals
```

3. 你的交易执行程序只消费 webhook 信号，本仓库不执行交易下单。


## Symbol 元数据

为避免 symbol 为空，程序会优先通过 CoinGecko Onchain Token Info 接口按合约地址补全：

- `/onchain/networks/{network}/tokens/multi/{addresses}`
- `/onchain/networks/{network}/tokens/{address}/info`（multi 未命中时逐个兜底）

## Dashboard

新增本地 Dashboard（参考你给的方向，结合当前仓库实现）：

- 页面地址：`/`
- API：`/api/whitelist`、`/api/signals`、`/api/pnl`、`/api/health`
- 展示内容：白名单数量、可交易数量、TopN、总盈亏（按 BUY=1 SOL）、24h 回测盈亏、生成时间、币种列表
- 合约地址可点击并跳转 GMGN（`https://gmgn.ai/sol/token/<token>`）
- 新增“信号发送记录”看板（来自 `signal-events.jsonl`）

你可以把该页面接入 OpenClaw 面板或反向代理到公网。




## Volatility Score v3（当前默认）

白名单采用“**基础过滤 + 评分排序**”模型：

- 基础过滤：`MIN_POOL_AGE_HOURS`、`MIN_LIQUIDITY_USD`、`MIN_VOLUME_24H_USD`、`MIN_FDV_USD`~`MAX_FDV_USD`
- 评分排序：按 `finalScore` 取前 `TOP_N`

评分公式：

```text
score =
0.30 * ATR
+ 0.25 * P90_RANGE
+ 0.20 * RSI_SWING
+ 0.15 * REVERSALS
+ 0.10 * VOL_LIQ
```

其中每项会先归一化到 `[0,1]`（可通过以下参数调节上限）：

- `VOL_SCORE_ATR_CAP`（默认 `0.10`，即 ATR%=10%）
- `VOL_SCORE_P90_CAP`（默认 `0.10`，即 P90%=10%）
- `VOL_SCORE_RSI_CAP`（默认 `100`）
- `VOL_SCORE_REVERSAL_CAP`（默认 `150`）
- `VOL_SCORE_VOL_LIQ_CAP`（默认 `30`）

## 5分钟高波动参数模板

如果你发现选出来的币 5m 波动不够，可以把阈值再拉高：

```bash
TOP_N=40 \
MIN_ATR_PCT_5M14=0.06 \
MIN_AVG_RANGE_5M=0.04 \
MIN_VOLUME_LIQUIDITY_RATIO=5 \
MIN_RSI_SWING=38 \
MIN_REVERSALS_5M=14 \
MIN_P90_RANGE_PCT_5M=0.045 \
npm run build:whitelist
```

建议先看 Dashboard 里的 `Vol/Liq`、`ATR%`、`P90 Range%`、`RSI Swing`、`Reversals` 五列，再逐步调参。

如果你遇到“只筛出 3 个币”，建议先用更宽松模板：

```bash
TOP_N=40 \
MIN_VOLUME_LIQUIDITY_RATIO=3 \
MIN_AVG_RANGE_5M=0.025 \
MIN_RSI_SWING=28 \
MIN_REVERSALS_5M=6 \
MIN_P90_RANGE_PCT_5M=0.03 \
FILTER_DEBUG=true \
npm run build:whitelist
```

开启 `FILTER_DEBUG=true` 后，`whitelist.json` 会附带 `debug.hardRejects` 和 `debug.metricRejects`，可快速看到是哪个条件在卡候选币。
