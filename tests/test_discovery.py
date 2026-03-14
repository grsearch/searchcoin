import asyncio

from app.discovery import (
    SmartWalletDiscovery,
    _dict_looks_like_token_entity,
    _extract_base58_wallets,
    _extract_token_mints,
)


def test_extract_base58_wallets_from_nested_payload():
    out = set()
    payload = {
        "a": [
            {"wallet": "So11111111111111111111111111111111111111112"},
            {"address": "5dfHpiBxagAKGUMLpCM246qHb8i8gADE3xdpVnDKpump"},
            {"not_wallet": "hello"},
        ],
        "b": {"owner": "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2"},
    }
    _extract_base58_wallets(payload, out)
    assert "So11111111111111111111111111111111111111112" in out
    assert "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2" in out
    assert "5dfHpiBxagAKGUMLpCM246qHb8i8gADE3xdpVnDKpump" not in out


def test_extract_wallets_from_address_rows_with_metrics():
    out = set()
    payload = {
        "data": [
            {
                "address": "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2",
                "pnl_30d": 1234,
                "tradeCount": 9,
            },
            {
                "address": "So11111111111111111111111111111111111111112",
                "symbol": "SOL",
            },
        ]
    }
    _extract_base58_wallets(payload, out)
    assert "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2" in out
    assert "So11111111111111111111111111111111111111112" not in out


def test_extract_wallets_from_wallet_list_strings():
    out = set()
    payload = {
        "wallets": [
            "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2",
            "5dfHpiBxagAKGUMLpCM246qHb8i8gADE3xdpVnDKpump",
        ]
    }
    _extract_base58_wallets(payload, out)
    assert "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2" in out
    assert "5dfHpiBxagAKGUMLpCM246qHb8i8gADE3xdpVnDKpump" not in out


def test_extract_token_mints_from_nested_payload():
    out = set()
    payload = {
        "data": [
            {"mint": "So11111111111111111111111111111111111111112"},
            {"token_address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"},
            {"wallet": "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2"},
        ]
    }
    _extract_token_mints(payload, out)
    assert "So11111111111111111111111111111111111111112" in out
    assert "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" in out
    assert "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2" not in out


def test_extract_token_mints_from_smart_money_token_key_payload():
    out = set()
    payload = {
        "data": [
            {
                "token": "63nb8TihiGToYCMxdKrbMyJ8qshZtxx2Q1pgaqM9pump",
                "symbol": "Solmoji",
                "price": 0.0000025,
                "volume_usd": 2326465,
            }
        ]
    }
    _extract_token_mints(payload, out)
    assert "63nb8TihiGToYCMxdKrbMyJ8qshZtxx2Q1pgaqM9pump" in out


def test_extract_token_mints_from_tokenish_address_rows():
    out = set()
    payload = {
        "data": [
            {
                "address": "So11111111111111111111111111111111111111112",
                "symbol": "SOL",
                "price": 140.12,
            },
            {
                "address": "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2",
                "tradeCount": 12,
                "pnl_30d": 5200,
            },
        ]
    }
    _extract_token_mints(payload, out)
    assert "So11111111111111111111111111111111111111112" in out
    assert "DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2" not in out


def test_token_entity_heuristics():
    assert _dict_looks_like_token_entity({"address": "abc", "symbol": "X", "price": 1.2})
    assert not _dict_looks_like_token_entity({"address": "abc", "pnl_30d": 100, "tradeCount": 3})


def test_build_candidate_rows_sorted_and_limited():
    service = SmartWalletDiscovery()
    stats = {
        "w1": {"address": "w1", "pnl_30d": 100},
        "w2": {"address": "w2", "pnl_30d": 300},
        "w3": {"address": "w3", "pnl_30d": 200},
    }
    rows = service._build_candidate_rows(stats)
    assert rows[0]["address"] == "w2"
    assert rows[1]["address"] == "w3"
    assert rows[2]["address"] == "w1"


def test_proxy_stats_fill_non_zero_values():
    service = SmartWalletDiscovery()
    stats = {
        "w1": {"address": "w1"},
        "w2": {"address": "w2", "net_worth_usd": 0},
    }
    service._apply_proxy_stats(stats)

    for row in stats.values():
        assert row["pnl_30d"] > 0
        assert row["pnl_7d"] > 0
        assert row["total_trades"] > 0
        assert row["profitable_trades"] > 0
        assert row["tx_last_7d"] > 0
        assert row["net_worth_usd"] > 0


def test_preview_candidates_includes_debug_snapshot(monkeypatch):
    service = SmartWalletDiscovery()

    async def _fake_fetch(limit=20):
        service.last_candidate_debug = {
            "safe_limit": limit,
            "wallets_found": 1,
            "steps": [{"stage": "direct_wallet_endpoint", "status_code": 200}],
        }
        return ["DwBnzRQ5f7Gn2ujNpZY4bZeMc797cyHSL4ZfmtKFJmt2"]

    monkeypatch.setattr(service, "fetch_candidate_wallets", _fake_fetch)
    payload = asyncio.run(service.preview_candidates(limit=7))
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert "discovery_debug" in payload
    assert payload["discovery_debug"]["safe_limit"] == 7
