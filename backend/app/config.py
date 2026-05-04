from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # AWS Bedrock credentials (optional — boto3 uses default chain if not set)
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_session_token: str = ""

    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    finnhub_api_key: str = ""
    database_url: str = "sqlite:///./trading.db"
    max_risk_usd: float = 5000.0
    log_level: str = "INFO"
    fixtures_mode: bool = False
    anthropic_model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    anthropic_haiku_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    def assert_paper(self) -> None:
        if "paper" not in self.alpaca_base_url:
            raise RuntimeError(f"Refusing to start: ALPACA_BASE_URL is not paper ({self.alpaca_base_url})")

    def bedrock_kwargs(self) -> dict:
        """Build kwargs for AnthropicBedrock client. Uses boto3 default chain if keys not set."""
        kwargs: dict = {"aws_region": self.aws_region}
        if self.aws_access_key_id:
            kwargs["aws_access_key"] = self.aws_access_key_id
            kwargs["aws_secret_key"] = self.aws_secret_access_key
        if self.aws_session_token:
            kwargs["aws_session_token"] = self.aws_session_token
        return kwargs

settings = Settings()
