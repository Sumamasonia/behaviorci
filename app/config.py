"""
Central configuration. Everything has a free-by-default value so the
project runs with zero paid services out of the box.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./behaviorci.db"

    judge_mode: str = "ollama"
    ollama_model: str = "llama3.1:8b"
    ollama_host: str = "http://localhost:11434"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    embed_mode: str = "local"
    embed_local_model: str = "all-MiniLM-L6-v2"

    max_concurrent_evaluations: int = 10
    regression_score_threshold: float = 0.10
    drift_distance_threshold: float = 0.15

    github_token: str = ""

    slack_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_to: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()