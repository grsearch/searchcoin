import asyncio

from app.discovery import (
    SmartWalletDiscovery,
    _dict_looks_like_token_entity,
    _extract_base58_wallets,
    _extract_token_mints_from_token_rows,
    _extract_token_mints,
    _is_probably_pump_mint,
    _token_row_passes_seed_filters,
    _extract_token_age_hours,
    _extract_token_fdv_usd,
    _extract_token_lp_usd,
    _extract_token_lp_burned_ratio,
)



def test_extract_token_age_fdv_lp_helpers():
    row = {"age": 2, "fdv": "1,500,000", "liquidity": 250_000, "lp_burned_percent": 100}
    assert _extract_token_age_hours(row) == 2
    assert _extract_token_fdv_usd(row) == 1_500_000
    assert _extract_token_lp_usd(row) == 250_000
    assert _extract_token_lp_burned_ratio(row) == 1.0

    row_days = {"age_days": 2}
    assert _extract_token_age_hours(row_days) == 48


def test_token_row_passes_seed_filters():
    ok_row = {"age": 30, "fdv": 2_000_000, "liquidity": 300_000, "lp_burned_percent": 100}
    ok, reason = _token_row_passes_seed_filters(
        ok_row,
        min_age_hours=24,
        max_age_hours=14 * 24,
        min_fdv_usd=1_000_000,
        min_lp_to_fdv_ratio=0.10,
        min_lp_burned_ratio=1.0,
    )
    assert ok and reason == "accepted"

    missing_age, reason = _token_row_passes_seed_filters(
        {"fdv": 2_000_000, "liquidity": 300_000, "lp_burned_percent": 100},
        min_age_hours=24,
        max_age_hours=14 * 24,
        min_fdv_usd=1_000_000,
        min_lp_to_fdv_ratio=0.10,
        min_lp_burned_ratio=1.0,
    )
    assert not missing_age and reason == "missing_age"

    missing_fdv, reason = _token_row_passes_seed_filters(
        {"age": 48, "liquidity": 300_000, "lp_burned_percent": 100},
        min_age_hours=24,
        max_age_hours=14 * 24,
        min_fdv_usd=1_000_000,
        min_lp_to_fdv_ratio=0.10,
        min_lp_burned_ratio=1.0,
    )
    assert not missing_fdv and reason == "missing_fdv"

    missing_lp, reason = _token_row_passes_seed_filters(
        {"age": 48, "fdv": 2_000_000, "lp_burned_percent": 100},
        min_age_hours=24,
        max_age_hours=14 * 24,
        min_fdv_usd=1_000_000,
        min_lp_to_fdv_ratio=0.10,
        min_lp_burned_ratio=1.0,
    )
    assert not missing_lp and reason == "missing_lp"

    missing_lp_burned, reason = _token_row_passes_seed_filters(
        {"age": 48, "fdv": 2_000_000, "liquidity": 300_000},
        min_age_hours=24,
        max_age_hours=14 * 24,
        min_fdv_usd=1_000_000,
        min_lp_to_fdv_ratio=0.10,
        min_lp_burned_ratio=1.0,
    )
    assert not missing_lp_burned and reason == "missing_lp_burned"

    too_new, reason = _token_row_passes_seed_filters(
        {"age": 12, "fdv": 2_000_000, "liquidity": 300_000, "lp_burned_percent": 100},
        min_age_hours=24,
        max_age_hours=14 * 24,
        min_fdv_usd=1_000_000,
        min_lp_to_fdv_ratio=0.10,
        min_lp_burned_ratio=1.0,
    )
    assert not too_new and reason == "age_too_low"

    too_old, reason = _token_row_passes_seed_filters(
        {"age": 400, "fdv": 2_000_000, "liquidity": 300_000, "lp_burned_percent": 100},
        min_age_hours=24,
        max_age_hours=14 * 24,
        min_fdv_usd=1_000_000,
        min_lp_to_fdv_ratio=0.10,
        min_lp_burned_ratio=1.0,
    )
    assert not too_old and reason == "age_too_high"

    low_fdv, reason = _token_row_passes_seed_filters(
        {"age": 48, "fdv": 900_000, "liquidity": 300_000, "lp_burned_percent": 100},
        min_age_hours=24,
        max_age_hours=14 * 24,
        min_fdv_usd=1_000_000,
        min_lp_to_fdv_ratio=0.10,
        min_lp_burned_ratio=1.0,
    )
    assert not low_fdv and reason == "fdv_too_low"

    low_lp_ratio, reason = _token_row_passes_seed_filters(
        {"age": 48, "fdv": 2_000_000, "liquidity": 150_000, "lp_burned_percent": 100},
        min_age_hours=24,
        max_age_hours=14 * 24,
        min_fdv_usd=1_000_000,
        min_lp_to_fdv_ratio=0.10,
        min_lp_burned_ratio=1.0,
    )
    assert not low_lp_ratio and reason == "lp_to_fdv_too_low"

    low_lp_burned, reason = _token_row_passes_seed_filters(
        {"age": 48, "fdv": 2_000_000, "liquidity": 300_000, "lp_burned_percent": 95},
        min_age_hours=24,
        max_age_hours=14 * 24,
        min_fdv_usd=1_000_000,
        min_lp_to_fdv_ratio=0.10,
        min_lp_burned_ratio=1.0,
    )
    assert not low_lp_burned and reason == "lp_burned_too_low"


def test_extract_token_mints_from_token_rows_applies_age_and_fdv_filters():
    out = set()
    payload = {
        "data": [
            {"token": "So11111111111111111111111111111111111111112", "age": 12, "fdv": 2_000_000, "liquidity": 300_000, "lp_burned_percent": 100},
            {"token": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "age": 48, "fdv": 500_000, "liquidity": 300_000, "lp_burned_percent": 100},
            {"token": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", "age": 48, "fdv": 2_000_000, "liquidity": 250_000, "lp_burned_percent": 100},
        ]
    }
    _, stats = _extract_token_mints_from_token_rows(payload, out)
    assert "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN" in out
    assert "So11111111111111111111111111111111111111112" not in out
    assert "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" not in out
    assert stats["rejected_age_too_low"] == 1
    assert stats["rejected_fdv_too_low"] == 1


def test_extract_token_mints_from_token_rows_applies_lp_filters():
    out = set()
    payload = {
        "data": [
            {"token": "So11111111111111111111111111111111111111112", "age": 48, "fdv": 2_000_000, "liquidity": 150_000, "lp_burned_percent": 100},
            {"token": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "age": 48, "fdv": 2_000_000, "liquidity": 300_000, "lp_burned_percent": 95},
            {"token": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", "age": 48, "fdv": 2_000_000, "liquidity": 300_000, "lp_burned_percent": 100},
        ]
    }
    _, stats = _extract_token_mints_from_token_rows(payload, out)
    assert "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN" in out
    assert stats["rejected_lp_to_fdv_too_low"] == 1
    assert stats["rejected_lp_burned_too_low"] == 1



def test_extract_token_mints_from_token_rows_rejects_missing_quality_fields():
    out = set()
    payload = {
        "data": [
            {"token": "So11111111111111111111111111111111111111112", "fdv": 2_000_000, "liquidity": 300_000, "lp_burned_percent": 100},
            {"token": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "age": 48, "liquidity": 300_000, "lp_burned_percent": 100},
            {"token": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", "age": 48, "fdv": 2_000_000, "lp_burned_percent": 100},
            {"token": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6P4A1Aq9Ex6vR7x", "age": 48, "fdv": 2_000_000, "liquidity": 300_000},
        ]
    }
    _, stats = _extract_token_mints_from_token_rows(payload, out)
    assert len(out) == 0
    assert stats["rejected_missing_age"] == 1
    assert stats["rejected_missing_fdv"] == 1
    assert stats["rejected_missing_lp"] == 1
    assert stats["rejected_missing_lp_burned"] == 1


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


def test_extract_token_mints_with_stats_counts():
    out = set()
    stats = {
        "rows_seen": 0,
        "tokens_extracted": 0,
        "accepted_mints": 0,
        "rejected_non_base58": 0,
    }
    payload = {
        "data": [
            {
                "token": "63nb8TihiGToYCMxdKrbMyJ8qshZtxx2Q1pgaqM9pump",
                "symbol": "Solmoji",
                "price": 0.0000025,
            },
            {
                "token": "bad-token-with-dash",
                "symbol": "Bad",
                "price": 1.0,
            },
        ]
    }
    _extract_token_mints(payload, out, stats=stats)
    assert stats["tokens_extracted"] >= 2
    assert stats["accepted_mints"] >= 1
    assert stats["rejected_non_base58"] >= 1


def test_extract_token_mints_from_token_rows_includes_first_candidate_debug():
    out = set()
    payload = {
        "data": [
            {
                "token": "63nb8TihiGToYCMxdKrbMyJ8qshZtxx2Q1pgaqM9pump",
                "symbol": "Solmoji",
                "price": 0.0000025,
            }
        ]
    }
    debug, stats = _extract_token_mints_from_token_rows(payload, out)
    assert debug["sample_row_token"] == "63nb8TihiGToYCMxdKrbMyJ8qshZtxx2Q1pgaqM9pump"
    assert debug["sample_candidate"] == "63nb8TihiGToYCMxdKrbMyJ8qshZtxx2Q1pgaqM9pump"
    assert stats["tokens_extracted"] == 1
    assert stats["accepted_mints"] == 1


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



def test_is_probably_pump_mint():
    assert _is_probably_pump_mint("63nb8TihiGToYCMxdKrbMyJ8qshZtxx2Q1pgaqM9pump")
    assert _is_probably_pump_mint(" 63nb8TihiGToYCMxdKrbMyJ8qshZtxx2Q1pgaqM9pump ")
    assert not _is_probably_pump_mint("So11111111111111111111111111111111111111112")


def test_non_pump_mints_are_prioritized_for_top_traders():
    mints = {
        "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzpump",
        "So11111111111111111111111111111111111111112",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    }
    ordered = sorted(mints, key=lambda m: (1 if _is_probably_pump_mint(m) else 0, m))
    assert ordered[-1].endswith("pump")
    assert not ordered[0].endswith("pump")


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
