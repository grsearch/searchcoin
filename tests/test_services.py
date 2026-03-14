from app.services import (
    jupiter_quote_url,
    parse_birdeye_price,
    parse_helius_asset,
    parse_jupiter_quote,
    validate_mint,
)


def test_validate_mint():
    assert validate_mint("So11111111111111111111111111111111111111112")
    assert not validate_mint("invalid")


def test_parse_helius_asset():
    sample = {
        "content": {"metadata": {"symbol": "SOL", "name": "Wrapped SOL"}, "links": {"image": "x"}},
        "token_info": {"supply": 1000, "decimals": 9},
    }
    result = parse_helius_asset(sample)
    assert result["symbol"] == "SOL"
    assert result["decimals"] == 9


def test_parse_birdeye_price():
    result = parse_birdeye_price({"value": 123.45, "priceChange24h": -1.2})
    assert result["price_usd"] == 123.45
    assert result["price_change_24h_percent"] == -1.2


def test_parse_jupiter_quote():
    result = parse_jupiter_quote({"inAmount": "1000000000", "outAmount": "160100000"}, input_decimals=9)
    assert result["price_usd_estimate"] == 160.1


def test_jupiter_quote_url_is_new_v1_endpoint():
    assert jupiter_quote_url().endswith("/swap/v1/quote")
