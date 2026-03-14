from typing import Any

from pydantic import BaseModel, Field


class JupiterQuote(BaseModel):
    in_amount: str | None = None
    out_amount: str | None = None
    price_usd_estimate: float | None = None
    route: dict[str, Any] | None = None


class AggregatedTokenResponse(BaseModel):
    mint: str
    symbol: str | None = None
    name: str | None = None
    image_url: str | None = None
    supply: int | None = None
    decimals: int | None = None
    price_usd: float | None = None
    price_change_24h_percent: float | None = Field(default=None)
    jupiter_quote: JupiterQuote | None = None
    sources: dict[str, bool]
    errors: dict[str, str]
