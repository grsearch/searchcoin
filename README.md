# Solana RSI 发现与信号程序（CoinGecko Pro Onchain）

本程序**不负责实际下单交易**。它负责：

1. 发现适合交易的币（生成白名单）
2. 监控 K 线
3. 跑 RSI 信号策略
4. 通过 webhook 发送买卖信号

## 功能概览

- 数据源：CoinGecko Pro Onchain（GeckoTerminal 数据）
- 候选来源：`trending_pools`、`new_pools`、`megafilter`
- 硬过滤：池龄、流动性、24h 成交额、24h 交易笔数、FDV 区间、黑名单
- 波动指标：ATR%、realized volatility、平均振幅、wick 比例
- 打分模型：
  - `score = 0.35*ATR_rank + 0.30*RV_rank + 0.20*Range_rank + 0.15*VolLiq_rank`
  - `penalty = 0.15*wick_rank + 0.10*(1-bodyBarsRatio)`
  - `final_score = score - penalty`
- 白名单输出：`whitelist.json`
- 信号输出：基于 RSI 的 BUY/SELL webhook 消息（仅信号，不交易）

## CLI

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
GECKO_API_KEY=your_key WEBHOOK_URL=https://your-webhook.endpoint npm run run:signals
```

## 主要环境变量（白名单构建）

- `GECKO_BASE_URL`（默认 `https://pro-api.coingecko.com/api/v3/onchain`）
- `GECKO_API_KEY`（CoinGecko Pro key）
- `GECKO_AUTH_MODE`（`header` 或 `query`）
- `NETWORK`（默认 `solana`）
- `TOP_N`（默认 `30`）
- `OUTPUT_PATH`（默认 `whitelist.json`）
- `MIN_POOL_AGE_HOURS`（默认 `48`）
- `MAX_POOL_AGE_HOURS`（默认 `8760`，约 1 年）
- `MIN_LIQUIDITY_USD`（默认 `100000`）
- `MIN_VOLUME_24H_USD`（默认 `500000`）
- `MIN_TX_COUNT_24H`（默认 `10000`）
- `MIN_FDV_USD`（默认 `1000000`）
- `MAX_FDV_USD`（默认 `8000000`）
- `MIN_ATR_PCT_5M14`（默认 `0.025`）
- `MIN_AVG_RANGE_PCT_5M_24H`（默认 `0.012`）
- `BLACKLIST_MINTS`（逗号分隔 token mint）
- `JUPITER_URL`（默认 `https://api.jup.ag/swap/v1/quote`，仅用于可路由性检查）
- `JUPITER_API_KEY`（可选，Jupiter Pro key）
- `JUPITER_AUTH_MODE`（`header` 或 `query`，默认 `header`）
- `QUOTE_MINT`（默认 Solana wSOL mint）

## 主要环境变量（信号引擎）

- `WHITELIST_PATH`（默认 `whitelist.json`）
- `KLINE_TIMEFRAME`（默认 `minute`）
- `KLINE_AGGREGATE`（默认 `5`）
- `KLINE_LIMIT`（默认 `120`）
- `RSI_PERIOD`（默认 `14`）
- `RSI_OVERSOLD`（默认 `30`）
- `RSI_OVERBOUGHT`（默认 `70`）
- `WEBHOOK_URL`（买卖信号接收地址）
- `WEBHOOK_AUTH_HEADER` / `WEBHOOK_AUTH_TOKEN`（可选 webhook 鉴权）
- `DRY_RUN=true`（只输出信号，不发送 webhook）

## 白名单直连（替代“接收白名单 webhook”）

交易程序或信号程序应直接读取本地 `whitelist.json`（或通过 `npm run read:whitelist` 读取 stdout），不再依赖外部 webhook 推送白名单。

## OpenClaw 部署建议

1. 每日生成白名单：

```bash
0 1 * * * cd /path/to/searchcoin && GECKO_API_KEY=xxx /usr/bin/env npm run build:whitelist
```

2. 每 1~5 分钟跑一次信号扫描：

```bash
*/5 * * * * cd /path/to/searchcoin && GECKO_API_KEY=xxx WEBHOOK_URL=https://xxx /usr/bin/env npm run run:signals
```

3. 你的交易执行程序只消费 webhook 信号，本仓库不执行交易下单。
