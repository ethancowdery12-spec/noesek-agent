from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOESEK_", env_file=".env", extra="ignore")
    # Core
    database_url: str = "sqlite+aiosqlite:///./noesek.db"
    public_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    # WhatsApp / Meta
    verify_token: str = "replace-me"
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    meta_app_secret: str = ""
    # Slack (optional channel; slack-sdk)
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    # Telegram (optional channel; aiogram)
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    # LLM
    llm_provider: str = "openai-compatible"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_models: str = ""  # JSON role->model map, e.g. {"chat":"deepseek-chat","reasoning":"deepseek-reasoner"}; empty = defaults
    llm_timeout_seconds: float = 90.0
    llm_max_retries: int = 3
    # Tools
    brave_search_api_key: str = ""
    llm_fallbacks: str = ""  # JSON list of {base_url, model, api_key}; empty = single provider
    llm_max_concurrent: int = 0  # 0 = unbounded; >0 bounds simultaneous LLM calls
    local_read_root: str = ""  # allowlisted root for the read_file tool; default NOESEK_HOME/workspace
    computer_allowed_origins: str = ""  # comma-separated https origins for /computer/browse; empty = allow any
    sandbox_image: str = "python:3.12-alpine"
    sandbox_backend: str = "docker-cli"  # docker-cli | docker-py | e2b
    tool_timeout_seconds: float = 45.0
    # MCP client (roadmap item 12): Context7 first, extra servers via JSON
    mcp_context7_enabled: bool = True
    mcp_context7_url: str = "https://mcp.context7.com/mcp"
    context7_api_key: str = ""  # optional Bearer for higher Context7 rate limits
    mcp_extra_servers: str = ""  # JSON {"name": {"url": "...", "api_key": "..."}}
    # Vector memory: pluggable embedder, zero-dep local default (core.memory_vector)
    vector_memory_enabled: bool = True
    embed_provider: str = "local"  # local (hashed-ngram) | openai-compatible
    embed_base_url: str = ""
    embed_api_key: str = ""
    embed_model: str = ""
    embed_dim: int = 256
    fetch_timeout_seconds: float = 20.0
    fetch_max_bytes: int = 1_000_000
    # Context
    history_limit: int = 24
    long_reminder_enabled: bool = True
    long_reminder_min_messages: int = 30
    memory_limit: int = 12
    max_context_chars: int = 12000
    # Approvals
    approval_ttl_hours: float = 24.0
    policy_rules: str = ""  # JSON list of ordered allow/ask/deny rules (core.policy)
    # Loop guardrails (core.loop_guard)
    loop_max_identical: int = 3
    loop_max_errors: int = 3
    loop_cycle_window: int = 3
    # Tool scaling (stage F): when a registry exceeds this many tools, non-core
    # tools are deferred behind search_tools. 0 = disabled.
    tool_defer_threshold: int = 0
    # Background worker
    worker_poll_seconds: float = 2.0
    task_max_attempts: int = 3
    # Channel authorization (vendored gateway authz chain; deny-by-default)
    whatsapp_allowed_users: str = ""  # comma-separated numbers/JIDs; empty = allowlist off
    gateway_allow_all_users: bool = False
    unauthorized_dm_behavior: str = "pair"  # pair | ignore | decline
    # Abuse control
    rate_limit_messages: int = 20
    rate_limit_window_seconds: float = 60.0
    # Observability
    metrics_enabled: bool = True

settings = Settings()
