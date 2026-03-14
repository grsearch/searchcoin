# SearchCoin API Aggregator

一个可交给 OpenClaw 安装的轻量服务：输入 Solana 代币 mint 地址，聚合查询以下数据源：

- **Helius**：代币基础信息（符号、名称、图片、供应量等）
- **Birdeye**：当前 DeFi 价格与 24h 变化
- **Jupiter Pro**：用 1 个代币换 USDC 的路由报价（`https://api.jup.ag/swap/v1/quote` + `x-api-key`）

同时提供 Dashboard 页面，展示：

- 正在监控的钱包地址（可点击跳转 GMGN）
- 钱包总资产
- 按系统信号买入后，当前持仓币种、symbol、合约地址（可点击跳转 GMGN）与盈亏情况
- 每个持仓触发的买入信号规则（`signal_rule`）
- Smart Wallet 白名单（含评分与权重）

## 功能

- `GET /health`：健康检查
- `GET /token/{mint}`：聚合三方 API 响应，输出统一 JSON
- `GET /dashboard`：可视化看板（HTML）
- `GET /api/dashboard`：看板数据（JSON，含 smart wallet report）
- `GET /api/smart-wallets`：Smart Wallet 打分结果（JSON）
- `POST /api/smart-wallets/refresh`：自动发现候选钱包并刷新 smart_wallets 数据（可落盘）
- `GET /api/smart-wallets/refresh-state`：查看自动刷新任务最近状态（成功/失败/时间）
- `GET /discovery/candidates`：预览自动发现到的钱包候选
- `POST /engine/evaluate`：交易信号评估（兼容无 `/api` 前缀调用）
- `GET /api/engine/state`：信号引擎运行状态
- `POST /api/engine/event`：注入监听到的钱包交易事件（buy/sell）
- `POST /api/engine/evaluate`：评估单个 token 是否触发买卖信号
- `POST /api/engine/run-once`：对当前窗口内 token 批量评估并返回决策

## 快速开始

### 1) 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) 环境变量

复制并编辑：

```bash
cp .env.example .env
```

说明：

- `HELIUS_API_KEY`、`BIRDEYE_API_KEY`、`JUPITER_API_KEY` **用于 `/token/{mint}` 聚合接口**。
- Dashboard (`/dashboard`、`/api/dashboard`) 与 smart wallet scoring 可在无 API key 下工作（用本地 JSON）。

可选项：

- `HOST`（默认 `0.0.0.0`）
- `PORT`（默认 `8000`）
- `USDC_MINT`（默认 Solana 主网 USDC）
- `REQUEST_TIMEOUT_SECONDS`（默认 `10`）
- `DASHBOARD_DATA_FILE`（默认 `data/dashboard.json`）
- `SMART_WALLETS_DATA_FILE`（默认 `data/smart_wallets.json`）
- `BIRDEYE_BASE_URL`（默认 `https://public-api.birdeye.so`）
- `DISCOVERY_MAX_WALLETS`（默认 `100`）
- `SMART_WALLET_AUTO_REFRESH_ENABLED`（默认 `true`）
- `SMART_WALLET_REFRESH_INTERVAL_SECONDS`（默认 `3600`）
- `SMART_WALLET_REFRESH_ON_STARTUP`（默认 `true`）
- `JUPITER_BASE_URL`（默认 `https://api.jup.ag`）

### 3) 维护 Dashboard 数据

编辑 `data/dashboard.json`（默认空，避免展示示例钱包）：

```json
{
  "wallets": [
    {
      "address": "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2",
      "label": "主账户",
      "total_asset_usd": 12650.0
    }
  ],
  "positions": [
    {
      "wallet_address": "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2",
      "symbol": "PUMP",
      "token_mint": "DzMw8nmA5rnoRTTXGHCZaRp9EkMwG2anqY99XxiXpump",
      "quantity": 150000.0,
      "avg_buy_price_usd": 0.0042,
      "current_price_usd": 0.0056,
      "signal_rule": "breakout_v2"
    }
  ]
}
```

### 4) 维护 Smart Wallet 候选数据

编辑 `data/smart_wallets.json`（可来自 Birdeye wallet API 预处理）：

```json
{
  "wallets": [
    {
      "address": "DwBnz...",
      "pnl_30d": 128000,
      "pnl_7d": 22000,
      "profitable_trades": 78,
      "total_trades": 110,
      "tx_last_7d": 95,
      "tx_last_3d": 38,
      "net_worth_usd": 680000,
      "avg_return_after_5m": 0.16,
      "recent_10_loss_ratio": 0.2
    }
  ]
}
```

### 5) 运行

```bash
./run.sh
```

### 6) 调用示例

```bash
curl "http://localhost:8000/token/So11111111111111111111111111111111111111112"
curl "http://localhost:8000/api/dashboard"
curl "http://localhost:8000/api/smart-wallets"
curl "http://localhost:8000/discovery/candidates"
curl -X POST "http://localhost:8000/engine/evaluate" -H "Content-Type: application/json" -d '{"token_mint":"So11111111111111111111111111111111111111112"}'
```

浏览器打开：

- `http://localhost:8000/dashboard`



## 自动扫链/监控/信号/自动交易（MVP 流程）

当前实现的最小闭环：

1. **Smart Wallet 扫描**：通过 `smart_wallet_report()` 生成白名单与权重（可由 Birdeye 钱包数据每日更新）。
2. **实时监控输入**：上游监听器（建议 Helius WebSocket）把钱包买卖事件写入 `POST /api/engine/event`。
3. **信号引擎判定**：
   - 买入：10 秒内 2 个白名单钱包买同币，或 1 个高权重钱包大额买入；
   - 卖出：10 秒内 2 个白名单钱包卖同币；
   - 并结合 Birdeye 活跃度确认（MVP 用 `priceChange24h` 代理）与 holder 集中度阈值。
4. **自动交易执行**：当 `auto_trade_enabled=true` 时，调用 Jupiter quote 生成买/卖执行动作（默认 dry-run）。
5. **候选钱包自动刷新**：服务启动时会自动刷新一次（可配置），并按固定间隔定时刷新；也可手动调用 `POST /api/smart-wallets/refresh?persist=true`。
6. **去除默认样例钱包干扰**：若未发现候选钱包，系统不会再写入示例钱包，避免 dashboard 显示假数据。

> 说明：MVP 当前已完成“信号->动作”自动化闭环；生产环境可在此基础上补全签名、`/swap/v1/swap`、发送交易与仓位管理。

## Jupiter Pro I 关键配置

当前实现已切换到 Jupiter 新版 Pro 接口：

- Quote: `GET https://api.jup.ag/swap/v1/quote`
- Swap: `POST https://api.jup.ag/swap/v1/swap`（本仓库当前仅用 quote）
- 必须在请求头携带：`x-api-key: <JUPITER_API_KEY>`

如果你遇到域名解析错误，请先在服务器本机排查：

```bash
nslookup api.jup.ag
curl -I https://api.jup.ag/swap/v1/quote
```

判断：

- `nslookup` 失败：DNS 问题
- `nslookup` 成功但 `curl` 失败：出网/TLS/防火墙问题
- 两者都成功：通常是代码还在请求旧域名或没带 `x-api-key`

## Smart Wallet 评分模型（实战版）

总分：

```text
score =
0.30 * pnl_score
+ 0.20 * winrate_score
+ 0.20 * activity_score
+ 0.15 * wallet_size_score
+ 0.15 * timing_score
```

- **PnL**：基于 `pnl_30d`
- **Winrate**：`profitable_trades / total_trades`
- **Activity**：基于 `tx_last_7d`
- **Wallet Size**：基于 `net_worth_usd`
- **Timing**：基于 `avg_return_after_5m`

筛选规则：

- `score >= 80` 进入白名单 smart_wallets
- `score > 90 => weight=3`，`>85 => 2`，`>=80 => 1`
- `recent_10_loss_ratio > 0.5` 直接进黑名单并移出白名单

## 设计说明

1. **失败隔离**：任一上游 API 失败不会导致整体 500，响应中会给出 `errors` 字段。
2. **统一价格语义**：优先采用 Birdeye spot 价格，Jupiter 报价作为可执行路由参考。
3. **基础校验**：对 mint 做长度与字符集校验，避免无效请求打爆上游。
4. **可观测性**：每次请求包含 `sources` 结果与错误信息，便于排查。
5. **Dashboard 可配置**：监控钱包和持仓信息来自 JSON 文件，便于后续接入数据库或信号系统。
6. **信号规则可追溯**：每个持仓都标记 `signal_rule`，便于复盘策略表现。
7. **Smart Wallet 可程序化**：评分、权重、白名单和黑名单可每日批处理更新。
8. **可用性改进**：即使没配置 API key，也能先启动并查看 dashboard。
