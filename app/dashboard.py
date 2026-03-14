import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings


@dataclass
class WalletItem:
    address: str
    total_asset_usd: float
    label: str = ""


@dataclass
class PositionItem:
    wallet_address: str
    symbol: str
    token_mint: str
    quantity: float
    avg_buy_price_usd: float
    current_price_usd: float
    signal_rule: str = "signal"

    @property
    def market_value_usd(self) -> float:
        return self.quantity * self.current_price_usd

    @property
    def cost_basis_usd(self) -> float:
        return self.quantity * self.avg_buy_price_usd

    @property
    def pnl_usd(self) -> float:
        return self.market_value_usd - self.cost_basis_usd

    @property
    def pnl_percent(self) -> float:
        if self.cost_basis_usd == 0:
            return 0.0
        return self.pnl_usd / self.cost_basis_usd * 100


DEFAULT_DASHBOARD_DATA = {"wallets": [], "positions": []}



def wallet_gmgn_url(address: str) -> str:
    return f"https://gmgn.ai/sol/address/{address}"


def token_gmgn_url(token_mint: str) -> str:
    return f"https://gmgn.ai/sol/token/{token_mint}"


def _load_raw_dashboard_data() -> dict[str, Any]:
    data_file = Path(settings.dashboard_data_file)
    if data_file.exists():
        try:
            with data_file.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
    return DEFAULT_DASHBOARD_DATA


def load_dashboard() -> dict[str, Any]:
    raw = _load_raw_dashboard_data()

    wallets = [
        WalletItem(
            address=str(item.get("address", "")).strip(),
            total_asset_usd=float(item.get("total_asset_usd", 0.0)),
            label=str(item.get("label", "")).strip(),
        )
        for item in raw.get("wallets", [])
        if str(item.get("address", "")).strip()
    ]

    positions = [
        PositionItem(
            wallet_address=str(item.get("wallet_address", "")).strip(),
            symbol=str(item.get("symbol", "")).strip(),
            token_mint=str(item.get("token_mint", "")).strip(),
            quantity=float(item.get("quantity", 0.0)),
            avg_buy_price_usd=float(item.get("avg_buy_price_usd", 0.0)),
            current_price_usd=float(item.get("current_price_usd", 0.0)),
            signal_rule=(
                str(item.get("signal_rule", item.get("buy_reason", "signal"))).strip()
                or "signal"
            ),
        )
        for item in raw.get("positions", [])
        if str(item.get("wallet_address", "")).strip() and str(item.get("token_mint", "")).strip()
    ]

    wallet_total_usd = sum(wallet.total_asset_usd for wallet in wallets)
    positions_market_value_usd = sum(position.market_value_usd for position in positions)
    positions_pnl_usd = sum(position.pnl_usd for position in positions)

    return {
        "wallets": wallets,
        "positions": positions,
        "wallet_total_usd": wallet_total_usd,
        "positions_market_value_usd": positions_market_value_usd,
        "positions_pnl_usd": positions_pnl_usd,
    }


def dashboard_json_payload() -> dict[str, Any]:
    data = load_dashboard()

    wallets = [
        {
            "address": wallet.address,
            "label": wallet.label,
            "total_asset_usd": wallet.total_asset_usd,
            "gmgn_url": wallet_gmgn_url(wallet.address),
        }
        for wallet in data["wallets"]
    ]

    positions = [
        {
            "wallet_address": position.wallet_address,
            "wallet_gmgn_url": wallet_gmgn_url(position.wallet_address),
            "symbol": position.symbol,
            "token_mint": position.token_mint,
            "token_gmgn_url": token_gmgn_url(position.token_mint),
            "quantity": position.quantity,
            "avg_buy_price_usd": position.avg_buy_price_usd,
            "current_price_usd": position.current_price_usd,
            "market_value_usd": position.market_value_usd,
            "pnl_usd": position.pnl_usd,
            "pnl_percent": position.pnl_percent,
            "signal_rule": position.signal_rule,
            "buy_reason": position.signal_rule,
        }
        for position in data["positions"]
    ]

    return {
        "wallet_total_usd": data["wallet_total_usd"],
        "positions_market_value_usd": data["positions_market_value_usd"],
        "positions_pnl_usd": data["positions_pnl_usd"],
        "wallets": wallets,
        "positions": positions,
    }
