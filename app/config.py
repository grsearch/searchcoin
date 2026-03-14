from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Keep keys optional at startup so dashboard endpoints can work without token API access.
    helius_api_key: str = ""
    birdeye_api_key: str = ""
    jupiter_api_key: str = ""
    jupiter_base_url: str = "https://api.jup.ag"
    birdeye_base_url: str = "https://public-api.birdeye.so"

    host: str = "0.0.0.0"
    port: int = 8000
    usdc_mint: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    request_timeout_seconds: float = 10.0
    dashboard_data_file: str = "data/dashboard.json"
    smart_wallets_data_file: str = "data/smart_wallets.json"
    discovery_max_wallets: int = 100

    # Auto discovery scheduler
    smart_wallet_auto_refresh_enabled: bool = True
    smart_wallet_refresh_interval_seconds: int = 3600
    smart_wallet_refresh_on_startup: bool = True

    # 3-server deployment mode: all | scanner | strategy | trader
    server_role: str = "all"
    strategy_ingest_url: str = ""
    trader_signal_url: str = ""
    inter_server_shared_token: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
