from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

from app.services import ServiceClients
from app.smart_wallets import smart_wallet_report


@dataclass
class WalletTradeEvent:
    wallet: str
    token_mint: str
    side: str  # buy | sell
    amount_token: float
    amount_usd: float
    ts: float


@dataclass
class SignalDecision:
    signal: str  # buy | sell | none
    token_mint: str
    reason: str
    score: float
    contributors: list[str]
    action: dict[str, Any] | None


class SignalEngine:
    def __init__(
        self,
        clients: ServiceClients,
        *,
        window_seconds: int = 10,
        high_weight_buy_usd: float = 1000.0,
        min_trade_boost_24h: float = 1.0,
        max_holder_top10_ratio: float = 0.80,
        auto_trade_enabled: bool = False,
        auto_trade_dry_run: bool = True,
    ):
        self.clients = clients
        self.window_seconds = window_seconds
        self.high_weight_buy_usd = high_weight_buy_usd
        self.min_trade_boost_24h = min_trade_boost_24h
        self.max_holder_top10_ratio = max_holder_top10_ratio
        self.auto_trade_enabled = auto_trade_enabled
        self.auto_trade_dry_run = auto_trade_dry_run
        self._events: deque[WalletTradeEvent] = deque(maxlen=5000)

    def ingest_event(self, event: WalletTradeEvent) -> None:
        self._events.append(event)

    def _active_window_events(self, now_ts: float) -> list[WalletTradeEvent]:
        threshold = now_ts - self.window_seconds
        return [e for e in self._events if e.ts >= threshold]

    def _smart_wallet_weights(self) -> dict[str, int]:
        report = smart_wallet_report()
        mapping: dict[str, int] = {}
        for item in report["smart_wallets"]:
            mapping[item["address"]] = int(item["wallet_weight"])
        return mapping

    async def evaluate_token(self, token_mint: str) -> SignalDecision:
        now_ts = time.time()
        weights = self._smart_wallet_weights()

        window_events = [e for e in self._active_window_events(now_ts) if e.token_mint == token_mint]
        smart_events = [e for e in window_events if weights.get(e.wallet, 0) > 0]

        buy_events = [e for e in smart_events if e.side == "buy"]
        sell_events = [e for e in smart_events if e.side == "sell"]

        # --- Sell signal (fast risk-off): at least 2 whitelisted wallets selling same token in window.
        sell_wallets = sorted({e.wallet for e in sell_events})
        if len(sell_wallets) >= 2:
            sell_weight = sum(weights.get(w, 0) for w in sell_wallets)
            action: dict[str, Any] | None = None
            if self.auto_trade_enabled:
                action = {
                    "type": "sell",
                    "provider": "jupiter",
                    "dry_run": self.auto_trade_dry_run,
                    "note": "execution adapter placeholder: call /swap/v1/swap with signed tx",
                }
            return SignalDecision(
                signal="sell",
                token_mint=token_mint,
                reason=">=2 smart wallets are selling in time window",
                score=float(sell_weight),
                contributors=sell_wallets,
                action=action,
            )

        # --- Buy signal
        unique_wallets = sorted({e.wallet for e in buy_events})
        signal_weight = sum(weights.get(w, 0) for w in unique_wallets)

        high_weight_large_buy = any(
            weights.get(e.wallet, 0) >= 2 and e.amount_usd >= self.high_weight_buy_usd for e in buy_events
        )
        two_wallet_same_token = len(unique_wallets) >= 2

        if not (two_wallet_same_token or high_weight_large_buy):
            return SignalDecision(
                signal="none",
                token_mint=token_mint,
                reason="wallet conditions not met",
                score=float(signal_weight),
                contributors=unique_wallets,
                action=None,
            )

        # Birdeye confirmation: use priceChange24h as lightweight activity proxy (MVP).
        birdeye_data = await self.clients.birdeye_price(token_mint)
        trade_boost = abs(float(birdeye_data.get("priceChange24h", 0.0) or 0.0))

        # Holder concentration placeholder: if unavailable from current endpoint, keep permissive default.
        holder_top10_ratio = float(birdeye_data.get("holderTop10Ratio", 0.5) or 0.5)

        if trade_boost < self.min_trade_boost_24h:
            return SignalDecision(
                signal="none",
                token_mint=token_mint,
                reason="token activity confirmation not met",
                score=float(signal_weight),
                contributors=unique_wallets,
                action=None,
            )

        if holder_top10_ratio > self.max_holder_top10_ratio:
            return SignalDecision(
                signal="none",
                token_mint=token_mint,
                reason="holder concentration too high",
                score=float(signal_weight),
                contributors=unique_wallets,
                action=None,
            )

        action = None
        if self.auto_trade_enabled:
            quote = await self.clients.jupiter_quote(token_mint, input_amount=10**9)
            action = {
                "type": "buy",
                "provider": "jupiter",
                "dry_run": self.auto_trade_dry_run,
                "quote": {
                    "inAmount": quote.get("inAmount"),
                    "outAmount": quote.get("outAmount"),
                    "swapMode": quote.get("swapMode"),
                },
            }

        return SignalDecision(
            signal="buy",
            token_mint=token_mint,
            reason="smart wallets + token confirmation",
            score=float(signal_weight),
            contributors=unique_wallets,
            action=action,
        )

    async def evaluate_all_active_tokens(self) -> list[dict[str, Any]]:
        now_ts = time.time()
        active_tokens = sorted({e.token_mint for e in self._active_window_events(now_ts)})
        decisions: list[dict[str, Any]] = []
        for token in active_tokens:
            decisions.append((await self.evaluate_token(token)).__dict__)
        return decisions

    def snapshot(self) -> dict[str, Any]:
        return {
            "window_seconds": self.window_seconds,
            "events_in_memory": len(self._events),
            "auto_trade_enabled": self.auto_trade_enabled,
            "auto_trade_dry_run": self.auto_trade_dry_run,
            "high_weight_buy_usd": self.high_weight_buy_usd,
            "min_trade_boost_24h": self.min_trade_boost_24h,
            "max_holder_top10_ratio": self.max_holder_top10_ratio,
            "recent_events": [asdict(e) for e in list(self._events)[-20:]],
        }
