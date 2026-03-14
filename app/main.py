import asyncio
import time

import httpx
from html import escape

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.dashboard import dashboard_json_payload, load_dashboard, token_gmgn_url, wallet_gmgn_url
from app.models import AggregatedTokenResponse
from app.services import (
    ServiceClients,
    UpstreamError,
    parse_birdeye_price,
    parse_helius_asset,
    parse_jupiter_quote,
    validate_mint,
)
from app.smart_wallets import smart_wallet_report
from app.engine import SignalEngine, WalletTradeEvent
from app.discovery import SmartWalletDiscovery
from app.cluster import (
    append_trader_signal,
    auth_ok,
    load_strategy_wallets,
    load_trader_signals,
    normalize_server_role,
    role_enabled,
    save_strategy_wallets,
)


class WalletEventIn(BaseModel):
    wallet: str
    token_mint: str
    side: str = Field(pattern="^(buy|sell)$")
    amount_token: float
    amount_usd: float
    ts: float | None = None


class EvaluateRequest(BaseModel):
    token_mint: str


class SmartWalletBatchIn(BaseModel):
    wallets: list[dict]
    source: str = "scanner"


class TraderSignalIn(BaseModel):
    token_mint: str
    signal: str
    reason: str = ""
    score: float = 0.0
    contributors: list[str] = Field(default_factory=list)


app = FastAPI(title="SearchCoin Aggregator", version="0.8.0")
clients = ServiceClients()
engine = SignalEngine(clients)
discovery = SmartWalletDiscovery()

refresh_state: dict[str, object] = {
    "last_run_ts": None,
    "last_result": None,
    "runs": 0,
}

role = normalize_server_role(settings.server_role)
start_time = int(time.time())


async def _relay_json(url: str, payload: dict) -> dict:
    if not url:
        return {"ok": False, "error": "target url not configured"}
    headers = {}
    if settings.inter_server_shared_token.strip():
        headers["x-inter-server-token"] = settings.inter_server_shared_token.strip()
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)
            text = resp.text
            if resp.status_code >= 400:
                return {"ok": False, "status": resp.status_code, "body": text}
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                data = {"raw": text}
            return {"ok": True, "status": resp.status_code, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}



def _refresh_state_snapshot() -> dict:
    return {
        "last_run_ts": refresh_state.get("last_run_ts"),
        "last_result": refresh_state.get("last_result"),
        "runs": refresh_state.get("runs", 0),
    }


async def _refresh_smart_wallet_candidates(persist: bool = True) -> dict:
    result = await discovery.refresh_candidates(persist=persist)
    refresh_state["last_run_ts"] = time.time()
    refresh_state["last_result"] = result
    refresh_state["runs"] = int(refresh_state.get("runs", 0)) + 1
    return result


async def _discovery_scheduler() -> None:
    while True:
        await _refresh_smart_wallet_candidates(persist=True)
        await asyncio.sleep(max(60, settings.smart_wallet_refresh_interval_seconds))


@app.on_event("startup")
async def _startup_discovery() -> None:
    if role_enabled(role, "scanner"):
        if settings.smart_wallet_refresh_on_startup:
            await _refresh_smart_wallet_candidates(persist=True)
        if settings.smart_wallet_auto_refresh_enabled:
            asyncio.create_task(_discovery_scheduler())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "role": role, "uptime_seconds": int(time.time()) - start_time}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    data = load_dashboard()
    smart_report = smart_wallet_report()

    wallets_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(w.label) or '-'}</td>"
            f"<td><a href='{escape(wallet_gmgn_url(w.address))}' target='_blank' rel='noopener noreferrer'>{escape(w.address)}</a></td>"
            f"<td>${w.total_asset_usd:,.2f}</td>"
            "</tr>"
        )
        for w in data["wallets"]
    ) or "<tr><td colspan='3'>暂无监控钱包数据</td></tr>"

    positions_rows = "".join(
        (
            "<tr>"
            f"<td><a href='{escape(wallet_gmgn_url(p.wallet_address))}' target='_blank' rel='noopener noreferrer'>{escape(p.wallet_address)}</a></td>"
            f"<td>{escape(p.symbol) or '-'}</td>"
            f"<td><a href='{escape(token_gmgn_url(p.token_mint))}' target='_blank' rel='noopener noreferrer'>{escape(p.token_mint)}</a></td>"
            f"<td>{p.quantity:,.4f}</td>"
            f"<td>${p.avg_buy_price_usd:,.6f}</td>"
            f"<td>${p.current_price_usd:,.6f}</td>"
            f"<td>${p.market_value_usd:,.2f}</td>"
            f"<td style='color:{'#16a34a' if p.pnl_usd >= 0 else '#dc2626'}'>${p.pnl_usd:,.2f} ({p.pnl_percent:,.2f}%)</td>"
            f"<td>{escape(p.signal_rule)}</td>"
            "</tr>"
        )
        for p in data["positions"]
    ) or "<tr><td colspan='9'>暂无信号持仓数据</td></tr>"

    smart_wallet_rows = "".join(
        (
            "<tr>"
            f"<td><a href='{escape(w['gmgn_url'])}' target='_blank' rel='noopener noreferrer'>{escape(w['address'])}</a></td>"
            f"<td>{w['score']:.2f}</td>"
            f"<td>{w['wallet_weight']}</td>"
            f"<td>{w['pnl_score']:.0f}</td>"
            f"<td>{w['winrate_score']:.0f}</td>"
            f"<td>{w['activity_score']:.0f}</td>"
            f"<td>{w['wallet_size_score']:.0f}</td>"
            f"<td>{w['timing_score']:.0f}</td>"
            "</tr>"
        )
        for w in smart_report["smart_wallets"]
    ) or "<tr><td colspan='8'>暂无 Smart Wallet 白名单</td></tr>"

    total_pnl_color = "#16a34a" if data["positions_pnl_usd"] >= 0 else "#dc2626"

    return f"""
    <html>
      <head>
        <meta charset='utf-8' />
        <meta name='viewport' content='width=device-width, initial-scale=1' />
        <title>SearchCoin Dashboard</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 24px; background: #f8fafc; color: #0f172a; }}
          h1 {{ margin-bottom: 8px; }}
          .cards {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }}
          .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 14px; min-width: 220px; }}
          table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e2e8f0; margin-bottom: 18px; }}
          th, td {{ border-bottom: 1px solid #e2e8f0; padding: 8px 10px; text-align: left; font-size: 14px; }}
          th {{ background: #f1f5f9; }}
          a {{ color: #2563eb; text-decoration: none; }}
          a:hover {{ text-decoration: underline; }}
          .section-title {{ margin-top: 24px; }}
          .hint {{ color: #475569; font-size: 13px; }}
        </style>
      </head>
      <body>
        <h1>SearchCoin 监控 Dashboard</h1>
        <p>展示监控钱包、信号持仓盈亏，以及 Smart Wallet 评分白名单。</p>

        <div class='cards'>
          <div class='card'><strong>监控钱包总资产</strong><br/>${data['wallet_total_usd']:,.2f}</div>
          <div class='card'><strong>信号持仓市值</strong><br/>${data['positions_market_value_usd']:,.2f}</div>
          <div class='card'><strong>信号持仓总盈亏</strong><br/><span style='color:{total_pnl_color}'>${data['positions_pnl_usd']:,.2f}</span></div>
          <div class='card'><strong>Smart Wallet 白名单数</strong><br/>{smart_report['count_whitelisted']}</div>
        </div>

        <h2 class='section-title'>正在监控的钱包地址</h2>
        <table>
          <thead><tr><th>备注</th><th>钱包地址（点击跳转 GMGN）</th><th>钱包总资产 (USD)</th></tr></thead>
          <tbody>{wallets_rows}</tbody>
        </table>

        <h2 class='section-title'>按系统信号买入的当前持仓</h2>
        <table>
          <thead>
            <tr>
              <th>钱包地址</th><th>Symbol</th><th>合约地址（点击跳转 GMGN）</th><th>持仓数量</th>
              <th>买入均价</th><th>现价</th><th>市值</th><th>盈亏</th><th>触发买入信号规则</th>
            </tr>
          </thead>
          <tbody>{positions_rows}</tbody>
        </table>

        <h2 class='section-title'>Smart Wallet 白名单（Score ≥ 80）</h2>
        <table>
          <thead>
            <tr>
              <th>钱包地址</th><th>综合分</th><th>权重</th><th>PnL</th><th>Winrate</th>
              <th>Activity</th><th>Wallet Size</th><th>Timing</th>
            </tr>
          </thead>
          <tbody>{smart_wallet_rows}</tbody>
        </table>

        <p class='hint'>评分模型: 0.30*PnL + 0.20*Winrate + 0.20*Activity + 0.15*WalletSize + 0.15*Timing，且最近10笔亏损占比>50%将黑名单剔除。</p>
      </body>
    </html>
    """


@app.get("/api/dashboard")
async def dashboard_data() -> dict:
    payload = dashboard_json_payload()
    payload["smart_wallet_report"] = smart_wallet_report()
    return payload


@app.get("/api/smart-wallets")
async def api_smart_wallets() -> dict:
    return smart_wallet_report()




@app.get("/discovery/candidates")
@app.get("/api/discovery/candidates")
async def discovery_candidates(limit: int = 20) -> dict:
    result = await discovery.preview_candidates(limit=limit)
    return {"result": result, "refresh_state": _refresh_state_snapshot()}


@app.post("/api/smart-wallets/refresh")
async def api_refresh_smart_wallets(persist: bool = True) -> dict:
    result = await _refresh_smart_wallet_candidates(persist=persist)
    report = smart_wallet_report() if result.get("ok") else None
    return {"result": result, "report": report, "refresh_state": _refresh_state_snapshot()}

@app.get("/api/smart-wallets/refresh-state")
async def api_smart_wallets_refresh_state() -> dict:
    return _refresh_state_snapshot()


@app.get("/api/engine/state")
async def engine_state() -> dict:
    return engine.snapshot()


@app.post("/api/engine/event")
async def engine_ingest_event(payload: WalletEventIn) -> dict:

    event = WalletTradeEvent(
        wallet=payload.wallet,
        token_mint=payload.token_mint,
        side=payload.side,
        amount_token=payload.amount_token,
        amount_usd=payload.amount_usd,
        ts=payload.ts or time.time(),
    )
    engine.ingest_event(event)
    return {"ok": True, "event": event.__dict__}


@app.post("/api/engine/evaluate")
@app.post("/engine/evaluate")
async def engine_evaluate(payload: EvaluateRequest) -> dict:
    decision = await engine.evaluate_token(payload.token_mint)
    return decision.__dict__




@app.post("/api/engine/run-once")
async def engine_run_once() -> dict:
    decisions = await engine.evaluate_all_active_tokens()
    return {
        "smart_wallets": smart_wallet_report()["smart_wallets"],
        "decisions": decisions,
    }



@app.post("/api/scanner/run-once")
async def scanner_run_once() -> dict:
    if not role_enabled(role, "scanner"):
        return {"ok": False, "error": f"role={role} does not run scanner"}

    refreshed = await _refresh_smart_wallet_candidates(persist=True)
    report = smart_wallet_report() if refreshed.get("ok") else None

    relay = None
    if report is not None and settings.strategy_ingest_url.strip():
        relay = await _relay_json(
            settings.strategy_ingest_url.strip(),
            {"wallets": report.get("smart_wallets", []), "source": "scanner"},
        )

    return {
        "ok": bool(refreshed.get("ok")),
        "refreshed": refreshed,
        "relay": relay,
        "report": report,
    }


@app.post("/api/strategy/smart-wallets/ingest")
async def strategy_ingest_smart_wallets(payload: SmartWalletBatchIn, x_inter_server_token: str | None = Header(default=None)) -> dict:
    if not auth_ok(x_inter_server_token):
        raise HTTPException(status_code=401, detail="invalid inter-server token")
    save_strategy_wallets(payload.wallets, source=payload.source)
    return {"ok": True, "count": len(payload.wallets), "source": payload.source}


@app.get("/api/strategy/smart-wallets")
async def strategy_get_smart_wallets() -> dict:
    wallets = load_strategy_wallets()
    return {"ok": True, "count": len(wallets), "wallets": wallets}


@app.post("/api/strategy/evaluate-and-forward")
async def strategy_evaluate_and_forward(payload: EvaluateRequest) -> dict:
    if not role_enabled(role, "strategy"):
        return {"ok": False, "error": f"role={role} does not run strategy"}

    decision = await engine.evaluate_token(payload.token_mint)
    relay = None
    if decision.signal in {"buy", "sell"} and settings.trader_signal_url.strip():
        relay = await _relay_json(
            settings.trader_signal_url.strip(),
            {
                "token_mint": decision.token_mint,
                "signal": decision.signal,
                "reason": decision.reason,
                "score": decision.score,
                "contributors": decision.contributors,
            },
        )

    return {"ok": True, "decision": decision.__dict__, "relay": relay}


@app.post("/api/trader/signal")
async def trader_signal(payload: TraderSignalIn, x_inter_server_token: str | None = Header(default=None)) -> dict:
    if not auth_ok(x_inter_server_token):
        raise HTTPException(status_code=401, detail="invalid inter-server token")
    signal = payload.model_dump()
    signal["received_at"] = int(time.time())
    append_trader_signal(signal)
    return {"ok": True, "signal": signal}


@app.get("/api/trader/signals")
async def trader_signals() -> dict:
    signals = load_trader_signals()
    return {"ok": True, "count": len(signals), "signals": signals[-100:]}

@app.get("/token/{mint}", response_model=AggregatedTokenResponse)
async def token_summary(mint: str) -> AggregatedTokenResponse:
    if not validate_mint(mint):
        raise HTTPException(status_code=400, detail="Invalid Solana mint address format")

    errors: dict[str, str] = {}
    sources = {"helius": False, "birdeye": False, "jupiter": False}
    payload: dict[str, object] = {"mint": mint}

    decimals = 9

    try:
        helius_raw = await clients.helius_asset(mint)
        payload.update(parse_helius_asset(helius_raw))
        sources["helius"] = True
        if isinstance(payload.get("decimals"), int):
            decimals = int(payload["decimals"])
    except (UpstreamError, ValueError, TypeError) as exc:
        errors["helius"] = str(exc)

    try:
        birdeye_raw = await clients.birdeye_price(mint)
        payload.update(parse_birdeye_price(birdeye_raw))
        sources["birdeye"] = True
    except (UpstreamError, ValueError, TypeError) as exc:
        errors["birdeye"] = str(exc)

    try:
        jupiter_raw = await clients.jupiter_quote(mint, input_amount=10**decimals)
        payload["jupiter_quote"] = parse_jupiter_quote(jupiter_raw, input_decimals=decimals)
        sources["jupiter"] = True
    except (UpstreamError, ValueError, TypeError) as exc:
        errors["jupiter"] = str(exc)

    payload["sources"] = sources
    payload["errors"] = errors

    return AggregatedTokenResponse(**payload)
