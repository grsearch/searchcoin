from app.smart_wallets import (
    activity_score,
    pnl_score,
    score_to_weight,
    should_blacklist,
    smart_wallet_report,
    timing_score,
    wallet_size_score,
    winrate_score,
)


def test_score_functions():
    assert pnl_score(120000) == 100
    assert winrate_score(0.65) == 85
    assert activity_score(60) == 85
    assert wallet_size_score(250000) == 85
    assert timing_score(0.12) == 80


def test_weight_and_blacklist():
    assert score_to_weight(91) == 3
    assert score_to_weight(86) == 2
    assert score_to_weight(80) == 1
    assert score_to_weight(79.99) == 0
    assert should_blacklist(0.51)
    assert not should_blacklist(0.5)


def test_report_shape():
    report = smart_wallet_report()
    assert "smart_wallets" in report
    assert "blacklisted_wallets" in report
    assert "count_whitelisted" in report
    if report["scored_wallets"]:
        first = report["scored_wallets"][0]
        assert "score" in first
        assert "wallet_weight" in first
