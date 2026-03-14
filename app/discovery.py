import json
import re
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _extract_base58_wallets(payload: Any, out: set[str]) -> None:
    if isinstance(payload, dict):
        for _, value in payload.items():
            _extract_base58_wallets(value, out)
        return

    if isinstance(payload, list):
        for item in payload:
            _extract_base58_wallets(item, out)
        return

    if isinstance(payload, str):
        value = payload.strip()
        if BASE58_RE.match(value):
            out.add(value)


class SmartWalletDiscovery:
    def __init__(self, timeout: float = settings.request_timeout_seconds):
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not settings.birdeye_api_key:
            raise RuntimeError("BIRDEYE_API_KEY is required for discovery")
        return {
            "X-API-KEY": settings.birdeye_api_key,
            "x-chain": "solana",
        }

    async def fetch_candidate_wallets(self, limit: int = 200) -> list[str]:
        """Discover candidate wallets from Birdeye smart-money token list payloads."""
        url = f"{settings.birdeye_base_url.rstrip('/')}/smart-money/v1/token/list"
        params = {"limit": max(1, min(limit, 1000))}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers=self._headers(), params=params)
            resp.raise_for_status()
            data = resp.json()

        wallets: set[str] = set()
        _extract_base58_wallets(data, wallets)
        return sorted(wallets)[: settings.discovery_max_wallets]

    async def fetch_wallet_stats(self, wallets: list[str]) -> dict[str, dict[str, Any]]:
        if not wallets:
            return {}

        headers = self._headers()
        base = settings.birdeye_base_url.rstrip("/")

        stats: dict[str, dict[str, Any]] = {w: {"address": w} for w in wallets}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # wallet/v2/pnl/multiple
            pnl_url = f"{base}/wallet/v2/pnl/multiple"
            pnl_resp = await client.post(pnl_url, headers=headers, json={"wallets": wallets})
            pnl_resp.raise_for_status()
            pnl_data = pnl_resp.json()

            for row in pnl_data.get("data", []) if isinstance(pnl_data, dict) else []:
                address = str(row.get("wallet") or row.get("address") or "").strip()
                if not address:
                    continue
                stats.setdefault(address, {"address": address}).update(
                    {
                        "pnl_30d": float(row.get("pnl30d", row.get("pnl_30d", 0.0)) or 0.0),
                        "pnl_7d": float(row.get("pnl7d", row.get("pnl_7d", 0.0)) or 0.0),
                        "profitable_trades": int(row.get("profitableTrades", row.get("profitable_trades", 0)) or 0),
                        "total_trades": int(row.get("totalTrades", row.get("total_trades", 0)) or 0),
                        "tx_last_7d": int(row.get("txLast7d", row.get("tx_last_7d", 0)) or 0),
                        "tx_last_3d": int(row.get("txLast3d", row.get("tx_last_3d", 0)) or 0),
                    }
                )

            # wallet/v2/current-net-worth per wallet
            net_url = f"{base}/wallet/v2/current-net-worth"
            for wallet in wallets:
                r = await client.get(net_url, headers=headers, params={"wallet": wallet})
                if r.status_code >= 400:
                    continue
                payload = r.json() if r.text else {}
                value = 0.0
                if isinstance(payload, dict):
                    data = payload.get("data", {})
                    if isinstance(data, dict):
                        value = float(data.get("totalUsd", data.get("total_usd", 0.0)) or 0.0)
                stats.setdefault(wallet, {"address": wallet})["net_worth_usd"] = value

        return stats

    def _build_candidate_rows(self, stats: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for address, s in stats.items():
            rows.append(
                {
                    "address": address,
                    "pnl_30d": float(s.get("pnl_30d", 0.0)),
                    "pnl_7d": float(s.get("pnl_7d", 0.0)),
                    "profitable_trades": int(s.get("profitable_trades", 0)),
                    "total_trades": int(s.get("total_trades", 0)),
                    "tx_last_7d": int(s.get("tx_last_7d", 0)),
                    "tx_last_3d": int(s.get("tx_last_3d", 0)),
                    "net_worth_usd": float(s.get("net_worth_usd", 0.0)),
                    "avg_return_after_5m": float(s.get("avg_return_after_5m", 0.0)),
                    "recent_10_loss_ratio": float(s.get("recent_10_loss_ratio", 0.0)),
                }
            )
        rows.sort(key=lambda x: x["pnl_30d"], reverse=True)
        return rows[: settings.discovery_max_wallets]

    async def refresh_candidates(self, persist: bool = True) -> dict[str, Any]:
        try:
            wallets = await self.fetch_candidate_wallets()
            stats = await self.fetch_wallet_stats(wallets)
            rows = self._build_candidate_rows(stats)

            if not rows:
                return {
                    "ok": False,
                    "error": "No candidate wallets discovered from upstream payloads",
                    "source": "birdeye",
                    "discovered_wallets": len(wallets),
                    "candidate_rows": 0,
                    "persisted": False,
                }

            payload = {"wallets": rows}
            if persist:
                path = Path(settings.smart_wallets_data_file)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            return {
                "ok": True,
                "source": "birdeye",
                "discovered_wallets": len(wallets),
                "candidate_rows": len(rows),
                "persisted": persist,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(exc),
                "hint": "Check Birdeye API key, endpoint availability, and network egress",
            }
