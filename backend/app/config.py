from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    anthropic_api_key: str = ""
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    finnhub_api_key: str = ""
    database_url: str = "sqlite:///./trading.db"
    max_risk_usd: float = 5000.0
    log_level: str = "INFO"
    fixtures_mode: bool = False
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    def assert_paper(self) -> None:
        if "paper" not in self.alpaca_base_url:
            raise RuntimeError(f"Refusing to start: ALPACA_BASE_URL is not paper ({self.alpaca_base_url})")

settings = Settings()
