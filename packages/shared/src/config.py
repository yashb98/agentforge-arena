"""
AgentForge Arena — Centralized Configuration

All environment variables are loaded here via Pydantic Settings.
Import this module instead of reading os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection settings."""

    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 5432
    name: str = "agentforge"
    user: str = "agentforge"
    password: SecretStr = SecretStr("agentforge")
    pool_size: int = 20
    max_overflow: int = 10

    @property
    def async_url(self) -> str:
        pw = self.password.get_secret_value()
        return f"postgresql+asyncpg://{self.user}:{pw}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = "localhost"
    port: int = 6379
    password: SecretStr | None = None
    db: int = 0

    @property
    def url(self) -> str:
        if self.password:
            pw = self.password.get_secret_value()
            return f"redis://:{pw}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class LLMSettings(BaseSettings):
    """LLM provider settings (via LiteLLM)."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    litellm_proxy_url: str = "http://localhost:4000"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    default_model: str = "claude-sonnet-4-6"
    max_tokens_default: int = 8192
    timeout_seconds: int = 300
    budget_per_tournament_usd: float = 500.0
    budget_alert_threshold: float = 0.8


class LangfuseSettings(BaseSettings):
    """Langfuse tracing settings."""

    model_config = SettingsConfigDict(env_prefix="LANGFUSE_")

    public_key: str = ""
    secret_key: SecretStr = SecretStr("")
    host: str = "https://cloud.langfuse.com"
    project_name: str = "agentforge-arena"
    enabled: bool = True
    flush_interval_seconds: float = 5.0


class SandboxSettings(BaseSettings):
    """Docker Sandbox MicroVM settings."""

    model_config = SettingsConfigDict(env_prefix="SANDBOX_")

    default_memory: str = "4g"
    default_cpus: int = 2
    max_memory_gb: int = 32
    max_cpus: int = 16
    default_disk: str = "10g"
    max_idle_seconds: int = 90
    network_allow: list[str] = Field(
        default=[
            "pypi.org",
            "registry.npmjs.org",
            "api.anthropic.com",
            "api.openai.com",
            "github.com",
            "api.github.com",
            "arxiv.org",
            "export.arxiv.org",
        ]
    )
    workspace_base: str = "/arena"
    pre_warm: bool = True


class StorageSettings(BaseSettings):
    """MinIO / S3 object storage settings."""

    model_config = SettingsConfigDict(env_prefix="S3_")

    endpoint: str = "http://localhost:9000"
    access_key: str = "minioadmin"
    secret_key: SecretStr = SecretStr("minioadmin")
    bucket_artifacts: str = "arena-artifacts"
    bucket_replays: str = "arena-replays"


class ResearchSettings(BaseSettings):
    """Automated challenge research (arXiv + GitHub) seeded into team sandboxes."""

    model_config = SettingsConfigDict(env_prefix="RESEARCH_", extra="ignore")

    seed_briefs_on_research_phase: bool = True
    peer_review_with_llm: bool = True
    seed_architecture_phase: bool = True
    architecture_followup_sweep: bool = True
    architecture_seed_with_llm: bool = True
    arxiv_max_per_query: int = Field(default=5, ge=1, le=20)
    github_per_query: int = Field(default=7, ge=1, le=30)
    github_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("RESEARCH_GITHUB_TOKEN", "GITHUB_TOKEN"),
    )


class MemorySettings(BaseSettings):
    """Agent memory defaults for resilient long-running execution."""

    model_config = SettingsConfigDict(env_prefix="MEMORY_")

    enabled: bool = True
    l1_key_prefix: str = "memory:l1"
    l1_ttl_seconds: int = 6 * 60 * 60
    l1_max_events: int = 50
    l2_enabled: bool = True
    l2_search_limit: int = 10


class AppSettings(BaseSettings):
    """Top-level application settings."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    name: str = "AgentForge Arena"
    version: str = "2.0.0"
    environment: str = "development"  # development | staging | production
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(default=["http://localhost:3000"])
    jwt_secret: SecretStr = SecretStr("change-me-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # Sub-configs
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    research: ResearchSettings = Field(default_factory=ResearchSettings)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Get cached application settings. Call once at startup."""
    return AppSettings()
