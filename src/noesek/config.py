from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOESEK_", env_file=".env", extra="ignore")
    # Core
    database_url: str = "sqlite+aiosqlite:///./noesek.db"
    # Connection pooling (Postgres only; sqlite always NullPool). Lane 1 scale
    # hardening: NullPool's connect-per-request churn melts a hosted Postgres
    # at concurrency; bounded QueuePool caps per-instance connections at
    # pool_size + max_overflow. pool_recycle below Neon's ~5min idle-compute
    # autosuspend so stale sockets are recycled before use (with pre-ping).
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: float = 30.0
    db_pool_recycle_seconds: int = 300
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
    webmcp_pages: str = ""  # JSON {"name": "https://..."} - pages the webmcp sidecar exposes as tools
    webmcp_host: str = "127.0.0.1"
    linkedin_access_token: str = ""  # member token for the LinkedIn layer (item 52); server-side only
    browser_state_key: str = ""  # passphrase -> Fernet key for stored browser sessions (item 56)
    browser_profile_dir: str = ""  # persistent chromium profile dir; default ~/.noesek/browser-profile
    webmcp_port: int = 8795
    # Vector memory: pluggable embedder, zero-dep local default (core.memory_vector)
    vector_memory_enabled: bool = True
    embed_provider: str = "local"  # local (hashed-ngram) | openai-compatible
    embed_base_url: str = ""
    embed_api_key: str = ""
    embed_model: str = ""
    embed_dim: int = 256
    # Graph memory: deterministic entity/relationship extraction (core.memory_graph)
    graph_memory_enabled: bool = True
    # Item 66: LLM-augmented entity extraction. Off by default - lands only if
    # it beats deterministic extraction on evals/entity_fixtures.py (the IBM
    # VLDB 2026 layer-utility gate). Falls back to deterministic on any error.
    llm_entity_extraction_enabled: bool = False
    # Multi-hop graph recall (HippoRAG pattern, own-words): recursive walk past
    # the 1-hop neighborhood with per-depth decay. decay(0)=decay(1)=1 keeps
    # the item-65 frontier values identical; deeper hops add graded boosts.
    graph_walk_depth: int = 3
    graph_walk_decay: float = 0.5
    fetch_timeout_seconds: float = 20.0
    fetch_max_bytes: int = 1_000_000
    # Context
    history_limit: int = 24
    parallel_read_tools_enabled: bool = True
    core_memory_max_chars: int = 2000
    condenser_enabled: bool = True
    condenser_keep_full_tool_results: int = 6
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
    # Memory pool scoping (item 68): 'deployment' = one shared pool (single-user
    # deploys, today's behavior); 'user' = one pool per (channel, external_user_id).
    memory_pool_mode: str = "deployment"
    # Needle 3 on-device tool routing (item 64/69). Opt-OUT since Sep 23:
    # routing assist is on by default. Auto-executing needle's proposed calls
    # stays OFF on the base weights - measured on the 34-tool production set,
    # wrong picks carried 0.69-0.99 confidence with no separating threshold
    # and picks varied run to run, so no safe auto-execute threshold exists.
    # Revisit with tuned weights (needle weights= + needle.environments).
    # OFF by default since Sep 23 (owner call: "remove it entirely for now"
    # after the tune lane was deferred). Re-enable is one env flip:
    # NOESEK_NEEDLE_ENABLED=1. Modules stay; nothing else was ripped out.
    needle_enabled: bool = False
    needle_min_confidence: float = 0.75
    needle_auto_execute: bool = False
    needle_timeout_seconds: float = 20.0  # wall-clock guard around one route()

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
