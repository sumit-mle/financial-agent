"""
Central settings — loaded once at startup via pydantic-settings.
All values come from environment variables or .env file.
"""
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "fin-ai-agent"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # ── API ──────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    secret_key: str = Field(default="dev-secret-key-change-in-production")
    admin_token: str = Field(default="admin-secret-token-change-in-production")
    # Accepts both a Python list and a JSON-encoded string from .env
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            import json
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
            # Fallback: comma-separated string
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_provider: Literal["openai", "anthropic", "local"] = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # ── Reranker ─────────────────────────────────────────────────────────────
    cohere_api_key: str = ""
    reranker_provider: Literal["flashrank", "cohere"] = "flashrank"
    reranker_top_k: int = 5

    # ── Vector Store ─────────────────────────────────────────────────────────
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""
    qdrant_collection_complaints: str = "complaints"
    qdrant_collection_policies: str = "policies"
    qdrant_collection_faq: str = "faq"

    # ── Postgres ─────────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@postgres:5432/fin_ai_agent"
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"

    # ── Observability ─────────────────────────────────────────────────────────
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # ── Data Sources ──────────────────────────────────────────────────────────
    cfpb_data_url: str = (
        "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"
    )
    sec_edgar_base_url: str = "https://data.sec.gov"

    # ── Ingestion ─────────────────────────────────────────────────────────────
    chunk_size: int = 512
    chunk_overlap: int = 64
    embedding_batch_size: int = 32
    ingest_workers: int = 4
    skip_ingest: bool = False

    # ── Agent ─────────────────────────────────────────────────────────────────
    agent_max_iterations: int = 10
    agent_confidence_threshold: float = 0.75
    agent_escalation_threshold: float = 0.50
    retrieval_top_k: int = 10
    context_max_tokens: int = 8000

    # ── Action Execution ──────────────────────────────────────────────────────
    
    # MLOps Pipeline Configuration
    mlops_monitoring_interval_seconds: int = Field(300, description="MLOps monitoring interval (seconds)")
    mlops_data_dir: str = Field("data", description="MLOps data directory")  
    mlops_model_dir: str = Field("models", description="MLOps model directory")
    
    # Salesforce CRM Integration
    salesforce_username: str = Field(default="", description="Salesforce username")
    salesforce_password: str = Field(default="", description="Salesforce password + security token")
    salesforce_client_id: str = Field(default="", description="Salesforce connected app consumer key")  
    salesforce_client_secret: str = Field(default="", description="Salesforce connected app consumer secret")
    salesforce_domain: str = Field(default="login", description="Salesforce instance domain")
    
    # Legacy API endpoints (fallback when Salesforce unavailable)
    crm_api_url: str = "http://localhost:9001/mock/crm"
    ticketing_api_url: str = "http://localhost:9001/mock/tickets"
    notification_api_url: str = "http://localhost:9001/mock/notify"

    @computed_field  # type: ignore[misc]
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @computed_field  # type: ignore[misc]
    @property
    def observability_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()


# Module-level alias for convenience
settings = get_settings()
