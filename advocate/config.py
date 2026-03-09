from pydantic_settings import BaseSettings
from pydantic import field_validator


class SafetyError(Exception):
    """Raised when a safety gate blocks an operation."""
    pass


class Config(BaseSettings):
    # RevenueCat
    revenuecat_api_key: str | None = None
    revenuecat_project_id: str | None = None

    # Anthropic
    anthropic_api_key: str | None = None

    # GitHub
    github_token: str | None = None
    github_repo: str | None = None

    # Twitter/X
    twitter_bearer_token: str | None = None
    twitter_api_key: str | None = None
    twitter_api_secret: str | None = None
    twitter_access_token: str | None = None
    twitter_access_secret: str | None = None

    # Reddit
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_username: str | None = None
    reddit_password: str | None = None

    # Safety flags
    demo_mode: bool = False
    dry_run: bool = True
    allow_writes: bool = False

    # Hugging Face (free, for embeddings and reranking)
    hf_token: str | None = None

    # Turso (free, cloud SQLite)
    turso_database_url: str | None = None
    turso_auth_token: str | None = None

    # ChromaDB Cloud (free, cloud vector database)
    chroma_api_key: str | None = None
    chroma_tenant: str | None = None
    chroma_database: str | None = None

    # AI Model
    ai_model: str = "claude-sonnet-4-6"

    # Ledger
    ledger_hmac_key: str | None = None

    # Paths
    db_path: str = "./advocate.db"
    docs_cache_dir: str = "./.docs_cache"
    site_output_dir: str = "./site_output"
    runs_dir: str = "./runs"

    # Site
    site_base_url: str = ""  # e.g. "/revcat-agent-advocate" for GitHub Pages project sites
    search_api_url: str = ""  # e.g. "https://rcagent-search.fly.dev" for live doc search

    # Analytics (GoatCounter — free, privacy-friendly)
    goatcounter_token: str | None = None
    goatcounter_site: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @field_validator(
        "revenuecat_api_key", "anthropic_api_key", "github_token", "hf_token",
        "turso_database_url", "turso_auth_token", "chroma_api_key",
        "twitter_bearer_token", "reddit_client_id",
        "goatcounter_token", "goatcounter_site",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v

    @field_validator("revenuecat_api_key")
    @classmethod
    def validate_rc_key(cls, v):
        if v and not (v.startswith("sk_") or v.startswith("atk_")):
            raise ValueError("REVENUECAT_API_KEY must start with sk_ or atk_")
        return v

    @property
    def has_rc_credentials(self) -> bool:
        return self.revenuecat_api_key is not None

    @property
    def has_anthropic(self) -> bool:
        return self.anthropic_api_key is not None

    @property
    def has_github(self) -> bool:
        return self.github_token is not None and self.github_repo is not None

    @property
    def has_twitter(self) -> bool:
        """Check for OAuth1 posting credentials, not just bearer token."""
        return all([
            self.twitter_api_key,
            self.twitter_api_secret,
            self.twitter_access_token,
            self.twitter_access_secret,
        ])

    @property
    def has_reddit(self) -> bool:
        return self.reddit_client_id is not None
