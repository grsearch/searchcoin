import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


class UpstreamError(Exception):
    pass


def validate_mint(mint: str) -> bool:
    return bool(BASE58_RE.match(mint))


def _require_api_key(service_name: str, key: str) -> None:
    if not key:
        raise UpstreamError(f"{service_name} API key is not configured")


@dataclass
class ServiceClients:
    timeout: float = settings.request_timeout_seconds

    async def helius_asset(self, mint: str) -> dict[str, Any]:
        _require_api_key("Helius", settings.helius_api_key)

        url = f"https://mainnet.helius-rpc.com/?api-key={settings.helius_api_key}"
        payload = {
            "jsonrpc": "2.0",
            "id": "searchcoin",
            "method": "getAsset",
            "params": {"id": mint},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        result = data.get("result")
        if not result:
            raise UpstreamError("Helius returned empty result")
        return result

    async def birdeye_price(self, mint: str) -> dict[str, Any]:
        _require_api_key("Birdeye", settings.birdeye_api_key)

        url = "https://public-api.birdeye.so/defi/price"
        headers = {
            "X-API-KEY": settings.birdeye_api_key,
            "x-chain": "solana",
        }
        params = {"address": mint}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
        if not data.get("success"):
            raise UpstreamError(f"Birdeye request failed: {data}")
        value = data.get("data")
        if value is None:
            raise UpstreamError("Birdeye returned empty data")
        return value

    async def jupiter_quote(self, mint: str, input_amount: int) -> dict[str, Any]:
        url = "https://quote-api.jup.ag/v6/quote"
        params = {
            "inputMint": mint,
            "outputMint": settings.usdc_mint,
            "amount": input_amount,
            "slippageBps": 50,
            "onlyDirectRoutes": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        if data.get("error"):
            raise UpstreamError(str(data["error"]))
        return data


def parse_helius_asset(data: dict[str, Any]) -> dict[str, Any]:
    content = data.get("content", {})
    metadata = content.get("metadata", {})
    token_info = data.get("token_info", {})

    return {
        "symbol": metadata.get("symbol") or token_info.get("symbol"),
        "name": metadata.get("name"),
        "image_url": content.get("links", {}).get("image"),
        "supply": token_info.get("supply"),
        "decimals": token_info.get("decimals"),
    }


def parse_birdeye_price(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "price_usd": data.get("value"),
        "price_change_24h_percent": data.get("priceChange24h"),
    }


def parse_jupiter_quote(data: dict[str, Any], input_decimals: int, output_decimals: int = 6) -> dict[str, Any]:
    out_amount = data.get("outAmount")
    in_amount = data.get("inAmount")
    est = None
    if out_amount and in_amount:
        try:
            normalized_out = int(out_amount) / (10**output_decimals)
            normalized_in = int(in_amount) / (10**input_decimals)
            est = normalized_out / normalized_in if normalized_in else None
        except (TypeError, ValueError, ZeroDivisionError):
            est = None

    return {
        "in_amount": in_amount,
        "out_amount": out_amount,
        "price_usd_estimate": est,
        "route": {
            "swapMode": data.get("swapMode"),
            "slippageBps": data.get("slippageBps"),
        },
    }
