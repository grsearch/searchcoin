import asyncio
import time

from app.engine import SignalEngine, WalletTradeEvent


class DummyClients:
    async def birdeye_price(self, mint: str):
        return {"priceChange24h": 5.0, "holderTop10Ratio": 0.4}

    async def jupiter_quote(self, mint: str, input_amount: int):
        return {"inAmount": str(input_amount), "outAmount": "100", "swapMode": "ExactIn"}


def test_engine_sell_signal_from_two_wallets():
    engine = SignalEngine(DummyClients(), auto_trade_enabled=False)
    # Patch smart-wallet weights directly.
    engine._smart_wallet_weights = lambda: {"w1": 2, "w2": 1}  # type: ignore[method-assign]

    now = time.time()
    engine.ingest_event(WalletTradeEvent("w1", "mint", "sell", 10, 100, now))
    engine.ingest_event(WalletTradeEvent("w2", "mint", "sell", 15, 120, now))

    decision = asyncio.run(engine.evaluate_token("mint"))
    assert decision.signal == "sell"


def test_engine_buy_signal_with_auto_trade():
    engine = SignalEngine(DummyClients(), auto_trade_enabled=True, auto_trade_dry_run=True)
    engine._smart_wallet_weights = lambda: {"w1": 2, "w2": 1}  # type: ignore[method-assign]

    now = time.time()
    engine.ingest_event(WalletTradeEvent("w1", "mint", "buy", 10, 1200, now))

    decision = asyncio.run(engine.evaluate_token("mint"))
    assert decision.signal == "buy"
    assert decision.action is not None
    assert decision.action["dry_run"] is True
