"""
app/core/config.py
──────────────────
Central settings management via Pydantic BaseSettings.
All configuration is loaded from environment variables / .env file.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Databricks ──────────────────────────────────────────────────────────
    databricks_server_hostname: str
    databricks_http_path: str
    databricks_token: str

    databricks_catalog: str = "governed_platform_catalog"
    databricks_schema: str = "finance_schema"
    databricks_governance_schema: str = "governance_schema"

    # ── Views that are permitted in Option-B / AI queries ────────────────────
    allowed_views: list[str] = [
        "secure_revenue_yearly",
        "secure_revenue_quarterly",
    ]

    # ── Application ──────────────────────────────────────────────────────────
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"
    log_level: str = "INFO"

    # ── JWT (future) ─────────────────────────────────────────────────────────
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # ── AI / LLM (Stage 3) ───────────────────────────────────────────────────
    # Supported providers: openai | groq | azure | mock | kimi
    # Use "mock" in development to avoid real API calls.
    llm_provider: str = "mock"

    # OpenAI settings (LLM_PROVIDER=openai)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Kimi (Moonshot AI) settings (LLM_PROVIDER=kimi)
    # (Commented out notes about Kimi usage, keeping fields for fallback)
    kimi_api_key: str = ""
    kimi_model: str = "moonshot-v1-8k"
    kimi_base_url: str = "https://api.moonshot.cn/v1"

    # Groq settings (LLM_PROVIDER=groq)
    # Fast inference API, fully OpenAI SDK compatible
    groq_api_key: str = ""
    groq_model: str = "llama3-70b-8192"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Shared AI generation settings (apply to all real providers)
    ai_max_tokens: int = 500
    # Low temperature → deterministic, safe SQL generation
    ai_temperature: float = 0.1

    # ── Per-role row caps (LIMIT injector) ───────────────────────────────────
    # AI-generated queries that omit LIMIT will have one appended automatically.
    # These caps prevent bulk data exfiltration regardless of what the LLM produces.
    role_row_limits: dict[str, int] = {
        "admin": 1000,
        "finance_user": 500,
        "auditor": 200,
    }
    # Fallback if role is not found in the map above
    default_row_limit: int = 100

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.
    Import and call this wherever you need configuration.
    """
    return Settings()
