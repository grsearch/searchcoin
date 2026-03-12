# Solana RSI 发现与信号程序（CoinGecko Pro Onchain）

本程序**不负责实际下单交易**。它负责：

1. 每 6 小时扫描并发现适合交易的币
2. 生成并更新白名单（仅保留前 20）
3. 监控 K 线并跑 RSI 信号策略（5m 主周期）
4. 通过 webhook 发送买卖信号
5. 币种退出白名单时，优先发送 SELL 退出信号
6. Dashboard 可视化白名单状态

## 功能概览

- 数据源：CoinGecko Pro Onchain（GeckoTerminal 数据）
- 候选来源：`trending_pools`、`new_pools`、`megafilter`
- 硬过滤：池龄、流动性、24h 成交额、24h 交易笔数、FDV 区间、黑名单
- 白名单规则：默认只保留前 `20`（`TOP_N` 默认值）
- 白名单输出：`whitelist.json`
- 信号输出：基于 RSI 的 BUY/SELL webhook 消息（仅信号，不交易）
- 开单条件：15m K线下 EMA9 > EMA20 才允许 BUY
- 6 小时周期更新：退出白名单的币会优先发送 `SELL + EXIT_WHITELIST`

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

- 每 6 小时完整周期（更新白名单 + 退出币优先发 SELL）：

```bash
GECKO_API_KEY=your_key WEBHOOK_URL=https://your-webhook.endpoint npm run run:cycle
```

## 主要环境变量（白名单构建）

- `TOP_N`（默认 `20`）
- `MIN_POOL_AGE_HOURS`（默认 `48`）
- `MAX_POOL_AGE_HOURS`（默认 `8760`，约 1 年）
- `MIN_LIQUIDITY_USD`（默认 `100000`）
- `MIN_VOLUME_24H_USD`（默认 `500000`）
- `MIN_TX_COUNT_24H`（默认 `10000`）
- `MIN_FDV_USD`（默认 `1000000`）
- `MAX_FDV_USD`（默认 `8000000`）
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

## OpenClaw 部署建议

1. 每 6 小时运行一次完整周期：

```bash
0 */6 * * * cd /path/to/searchcoin && GECKO_API_KEY=xxx WEBHOOK_URL=https://xxx /usr/bin/env npm run run:cycle
```

2. 可选：更高频运行 RSI 监控（例如 5 分钟一次）

```bash
*/5 * * * * cd /path/to/searchcoin && GECKO_API_KEY=xxx WEBHOOK_URL=https://xxx /usr/bin/env npm run run:signals
```

3. 你的交易执行程序只消费 webhook 信号，本仓库不执行交易下单。


## Dashboard

新增本地 Dashboard（参考你给的方向，结合当前仓库实现）：

- 页面地址：`/`
- API：`/api/whitelist`、`/api/health`
- 展示内容：白名单数量、可交易数量、TopN、生成时间、币种列表

你可以把该页面接入 OpenClaw 面板或反向代理到公网。
