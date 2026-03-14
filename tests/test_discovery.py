from app.discovery import SmartWalletDiscovery, _extract_base58_wallets


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
