from app.dashboard import PositionItem, WalletItem, dashboard_json_payload, token_gmgn_url, wallet_gmgn_url


def test_gmgn_urls():
    assert wallet_gmgn_url("abc") == "https://gmgn.ai/sol/address/abc"
    assert token_gmgn_url("xyz") == "https://gmgn.ai/sol/token/xyz"


def test_position_pnl_math():
    p = PositionItem(
        wallet_address="w",
        symbol="AAA",
        token_mint="m",
        quantity=100,
        avg_buy_price_usd=2,
        current_price_usd=3,
    )
    assert p.market_value_usd == 300
    assert p.cost_basis_usd == 200
    assert p.pnl_usd == 100
    assert p.pnl_percent == 50


def test_wallet_has_label_default():
    wallet = WalletItem(address="abc", total_asset_usd=1)
    assert wallet.label == ""


def test_dashboard_payload_shape():
    payload = dashboard_json_payload()
    assert "wallets" in payload
    assert "positions" in payload
    if payload["positions"]:
        assert "signal_rule" in payload["positions"][0]
