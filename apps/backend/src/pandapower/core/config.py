from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env path relative to the backend repo root (apps/backend/.env),
# so the app works regardless of where uvicorn / pytest / Celery is launched from.
_BACKEND_ROOT = Path(__file__).resolve().parents[3]  # core/ -> pandapower/ -> src/ -> backend/
_ENV_FILE = _BACKEND_ROOT / ".env"

# Eagerly load .env into os.environ so any BaseSettings subclass (including
# nested ones like PandiSettings) picks values up consistently, regardless of
# how each subclass configures its env_file.
# override=True ensures the .env wins over any stale shell exports.
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)


class PandiSettings(BaseSettings):
    """Pandi bot configuration."""
    instance_id: str = Field(default="", description="Green API instance ID")
    token: str = Field(default="", description="Green API API token")
    whatsapp_number: str = Field(default="", description="Pandi WhatsApp number in E.164 format")
    webhook_secret: str = Field(default="", description="Secret for validating webhooks")
    default_monthly_limit: int = Field(default=100, description="Default monthly message quota")
    quota_warning_threshold: float = Field(default=0.80, description="Quota usage warning threshold (0..1)")
    intake_timeout_hours: int = Field(default=24, description="Hours to wait for intake response")
    llm_model: str = Field(default="claude-sonnet-4-5", description="Claude model for Pandi")
    llm_temperature: float = Field(default=0.7, description="LLM temperature")


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), case_sensitive=True, extra="ignore")

    APP_ENV: str = "development"
    DEBUG: bool = True

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # CORS
    # Accept either a JSON array (`["https://a.com","https://b.com"]`) or a
    # comma-separated string (`https://a.com,https://b.com`) — the latter is
    # what gets typed into the Render dashboard 99% of the time. Without this
    # validator, a plain string crashes pydantic-settings at boot with
    # "JSONDecodeError: Expecting value: line 1 column 1 (char 0)".
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:5174"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        if v is None or v == "":
            return ["http://localhost:5173", "http://localhost:5174"]
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            s = v.strip()
            # JSON array form — let pydantic's default JSON decoder handle it.
            if s.startswith("["):
                return s
            # Comma-separated form (the common dashboard input).
            return [item.strip() for item in s.split(",") if item.strip()]
        return v

    # Claude API (Phase 8: CV Parsing)
    ANTHROPIC_API_KEY: str = ""
    CV_PARSE_BATCH_SIZE: int = 10
    CV_PARSE_TIMEOUT_SECONDS: int = 300
    CV_PARSE_MAX_RETRIES: int = 3
    CV_EXTRACT_TIMEOUT_SECONDS: int = 30

    # Resend (transactional admin alerts via /admin/alerts)
    RESEND_API_KEY: str = ""

    # Pipedrive CRM (Phase 5: Carmit Orchestrator)
    PIPEDRIVE_API_TOKEN: str = ""
    PIPEDRIVE_API_DOMAIN: str = "https://api.pipedrive.com"
    PIPEDRIVE_BOT_USER_ID: str = ""

    # Carmit Orchestrator (Phase 5)
    CARMIT_MATCH_SCORE_THRESHOLD: float = 0.70
    CARMIT_CLEARANCE_LEVELS: dict = {
        "none": 0,
        "secret": 1,
        "top secret": 2,
        "ts/sci": 3,
    }

    # Pandi bot (Phase 10)
    pandi: PandiSettings = Field(default_factory=PandiSettings)


def get_settings() -> Settings:
    """Get application settings singleton."""
    return settings


settings = Settings()

# Debug at import time: show whether the .env loaded the keys we care about.
# (Goes to stdout so it appears in uvicorn logs.)
print(
    f"[CONFIG] .env file: {_ENV_FILE} (exists={_ENV_FILE.exists()}); "
    f"ANTHROPIC_API_KEY loaded={bool(settings.ANTHROPIC_API_KEY)} "
    f"(len={len(settings.ANTHROPIC_API_KEY)})",
    flush=True,
)
