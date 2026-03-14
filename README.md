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
- `POST /api/smart-wallets/refresh`：自动发现候选钱包并刷新 smart_wallets 数据（可落盘，返回 result + refresh_state；包含 real_stats_rows/proxy_stats_rows）
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
- `SMART_WALLET_WHITELIST_SCORE`（默认 `80`，白名单阈值）
- `SMART_WALLET_MIN_WHITELIST_COUNT`（默认 `0`，当真实评分过严时可用兜底保底数量）
- `SMART_WALLET_MIN_PROXY_SCORE`（默认 `65`，仅对兜底补位生效）
- `SMART_WALLET_AUTO_REFRESH_ENABLED`（默认 `true`）
- `SMART_WALLET_REFRESH_INTERVAL_SECONDS`（默认 `3600`）
- `SMART_WALLET_REFRESH_ON_STARTUP`（默认 `true`）
- `JUPITER_BASE_URL`（默认 `https://api.jup.ag`）

### 3) 维护 Dashboard 数据

编辑 `data/dashboard.json`（默认空，避免展示示例钱包）：

```json
{
  "wallets": [],
  "positions": []
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




## 三服务器部署模式（24小时稳定运行推荐）

可将系统拆成 3 个角色分别部署：

1. **Scanner 服务器**（`SERVER_ROLE=scanner`）
   - 负责 `smart-wallet` 发现与评分
   - 定时执行发现流程
   - 调用 `POST /api/scanner/run-once`
   - 可把白名单转发到策略服（`STRATEGY_INGEST_URL`）

2. **Strategy 服务器**（`SERVER_ROLE=strategy`）
   - 接收白名单：`POST /api/strategy/smart-wallets/ingest`
   - 监控事件并判定信号：`POST /api/strategy/evaluate-and-forward`
   - 可将买卖信号转发到交易服（`TRADER_SIGNAL_URL`）

3. **Trader 服务器**（`SERVER_ROLE=trader`）
   - 接收策略信号：`POST /api/trader/signal`
   - 查询最近信号：`GET /api/trader/signals`

> 现在代码已经按角色做了运行时隔离：
> - scanner 只负责发现流程；
> - strategy 只负责接收钱包与策略评估；
> - trader 只负责接收/记录交易信号。
>   若调用了不属于当前角色的端点，会返回 `{"ok": false, "error": "role=... does not run ..."}`。

> 如果扫描服出现“全是 proxy_stats 且白名单为空”，可先在 scanner 机器调整：
> - `SMART_WALLET_WHITELIST_SCORE=75`
> - `SMART_WALLET_MIN_WHITELIST_COUNT=10`
> - `SMART_WALLET_MIN_PROXY_SCORE=65`
>
> 这样即使 Birdeye 真实 PnL 端点临时不可用，也能先产出可监控的候选白名单。

跨服务器认证：

- 在三台服务器统一设置 `INTER_SERVER_SHARED_TOKEN`
- 转发时自动带 `x-inter-server-token` 请求头

### 给 3 个 OpenClaw 的最简安装方式

仓库里已提供三套模板和启动脚本：

- `deploy/.env.scanner.example` + `./run_scanner.sh`
- `deploy/.env.strategy.example` + `./run_strategy.sh`
- `deploy/.env.trader.example` + `./run_trader.sh`

你可以在三台机器各自执行：

```bash
cp deploy/.env.scanner.example deploy/.env.scanner
./run_scanner.sh
```

```bash
cp deploy/.env.strategy.example deploy/.env.strategy
./run_strategy.sh
```

```bash
cp deploy/.env.trader.example deploy/.env.trader
./run_trader.sh
```

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


### Discovery 端点变更兼容说明

当 Birdeye 的 `wallet/v2/pnl/multiple` 返回 404 时，系统会自动切换到回退模式：

1. 尝试 `wallet/v2/pnl`（按钱包查询）
2. 尝试 `wallet/v2/balance-change` 提取活跃度
3. 若仍缺失统计，则自动填充 proxy 统计（可评分），并在刷新结果中标记 `proxy_stats_rows`

这样可以保证“发现 -> 排名 -> 白名单”流程不中断。
发现逻辑说明（已修正）：

- 仅从钱包语义字段提取候选地址（如 `wallet`/`owner`/`trader`/`maker`），不再把 token mint 字段当作钱包。
- 自动过滤典型 Pump.fun mint（`...pump`）以降低误识别。
- 对 `address` 字段采用上下文判断：若同一对象包含交易/收益指标（如 pnl/tradeCount/volume），会识别为钱包；若是 token 元数据（如 symbol/mint）则忽略。
- 若直连 smart-wallet 接口无钱包数据，系统会自动走“token list -> top traders”二级回退来提取钱包候选。
- token seed 提取支持 `data[].token`（如 `smart-money/v1/token/list` 返回结构）以及 `mint/token_address/address` 变体。
- top traders 查询默认使用文档主参数 `address`（并带 `limit`），避免错误参数造成 400。
- `GET /discovery/candidates` 与 `POST /api/smart-wallets/refresh` 会返回 `discovery_debug`，可直接看到每个上游端点状态码与每一步提取数量，便于定位“权限问题 / 空数据窗口 / 字段变更”。
- `discovery_debug` 里还会包含 `raw_data_type/raw_data_len/sample_keys/sample_token` 以及 `rows_seen/tokens_extracted/accepted_mints/rejected_non_base58`，用于判断“提取失败”还是“被校验过滤”。
- `token_seed_endpoint` 还会输出 `sample_row_keys/sample_row_token/sample_row_mint/sample_candidate`，可直接验证候选字段是否被正确读取。
- scanner 角色每次刷新也会把 `discovery_debug` 关键字段打到日志，便于用 `journalctl -u searchcoin-scanner -f` 实时排障。

此外，`/token/{mint}` 的 Birdeye 价格请求现在严格使用 `BIRDEYE_BASE_URL`（默认 `https://public-api.birdeye.so`）拼接 `/defi/price`，避免环境里误用旧域名。
