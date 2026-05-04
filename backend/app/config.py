from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    aws_region: str = "us-east-1"
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    finnhub_api_key: str = ""
    database_url: str = "sqlite:///./trading.db"
    max_risk_usd: float = 5000.0
    log_level: str = "INFO"
    fixtures_mode: bool = False
    anthropic_model: str = "us.anthropic.claude-sonnet-4-6-20260101-v1:0"
    anthropic_haiku_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    def assert_paper(self) -> None:
        if "paper" not in self.alpaca_base_url:
            raise RuntimeError(f"Refusing to start: ALPACA_BASE_URL is not paper ({self.alpaca_base_url})")

settings = Settings()
