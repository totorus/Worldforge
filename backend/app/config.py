from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379"

    # LLM API Keys
    kimi_api_key: str
    openrouter_api_key: str

    # Bookstack (optional at startup — export unavailable without them)
    bookstack_url: str = "http://bookstack:80"
    bookstack_token_id: str = ""
    bookstack_token_secret: str = ""
    bookstack_public_url: str = ""

    # JWT
    jwt_secret: str = "changeme-generate-a-real-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8", "extra": "ignore", "env_ignore_empty": True}


settings = Settings()
