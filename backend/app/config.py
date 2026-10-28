import os
from dataclasses import dataclass, field
from pathlib import Path
from ipaddress import ip_address
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DEMO_SECRET = "agriscan-local-demo-secret-change-before-deployment"
EXAMPLE_SECRETS = {DEMO_SECRET, "local-demo-change-this-secret-before-production-2026"}


@dataclass
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'agriscan.db'}")
    )
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    upload_dir: Path = field(default_factory=lambda: Path(os.getenv("UPLOAD_DIR", str(ROOT / "uploads"))))
    demo_mode: bool = field(default_factory=lambda: os.getenv("DEMO_MODE", "true").lower() == "true")
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", DEMO_SECRET))
    admin_username: str = field(default_factory=lambda: os.getenv("ADMIN_USERNAME", "admin"))
    admin_password: str = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", "admin12345"))
    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175,https://localhost,http://localhost,capacitor://localhost"
        ).split(",")
    )
    token_hours: int = 12
    registration_enabled: bool = field(default_factory=lambda: os.getenv("REGISTRATION_ENABLED", "true").lower() == "true")
    email_verification_enabled: bool = field(default_factory=lambda: os.getenv("EMAIL_VERIFICATION_ENABLED", "false").lower() == "true")
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_username: str = field(default_factory=lambda: os.getenv("SMTP_USERNAME", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    smtp_from: str = field(default_factory=lambda: os.getenv("SMTP_FROM", ""))
    smtp_security: str = field(default_factory=lambda: os.getenv("SMTP_SECURITY", "starttls"))
    llm_enabled: bool = field(default_factory=lambda: os.getenv("LLM_ENABLED", "false").lower() == "true")
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    llm_timeout: int = field(default_factory=lambda: int(os.getenv("LLM_TIMEOUT", "30")))
    model_max_mb: int = field(default_factory=lambda: int(os.getenv("MODEL_MAX_UPLOAD_MB", "200")))
    model_manifest: str = field(default_factory=lambda: os.getenv("MODEL_MANIFEST", ""))
    inference_threads: int = field(default_factory=lambda: int(os.getenv("INFERENCE_THREADS", "2")))
    max_upload_bytes: int = 10 * 1024 * 1024

    def validate(self):
        self.upload_dir = Path(self.upload_dir).resolve()
        if not 1 <= self.inference_threads <= 16:
            raise ValueError("INFERENCE_THREADS must be between 1 and 16")
        if self.smtp_security not in {"starttls", "ssl"}:
            raise ValueError("SMTP_SECURITY 必须为 starttls 或 ssl")
        if self.email_verification_enabled and not (self.smtp_host and self.smtp_from):
            raise ValueError("邮件验证需要 SMTP_HOST 和 SMTP_FROM")
        if self.llm_enabled:
            endpoint = urlsplit(self.llm_base_url)
            host = endpoint.hostname or ""
            local = host.lower() == "localhost"
            try:
                local = local or ip_address(host).is_loopback
            except ValueError:
                pass
            valid_url = bool(host) and (endpoint.scheme == "https" or (endpoint.scheme == "http" and local))
            if not (self.llm_api_key and self.llm_model and valid_url) or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
                raise ValueError("大模型需要 HTTPS API 地址（本机回环地址可用 HTTP）、API 密钥及模型名称")
        if not 1 <= self.model_max_mb <= 2048 or not 1 <= self.llm_timeout <= 120:
            raise ValueError("上传限制或 API 超时配置无效")
        if not self.demo_mode:
            if self.jwt_secret in EXAMPLE_SECRETS or len(self.jwt_secret) < 32:
                raise ValueError("生产环境 JWT_SECRET 必须为至少 32 字符的随机密钥。")
            if self.admin_password == "admin12345" or len(self.admin_password) < 12:
                raise ValueError("生产环境 ADMIN_PASSWORD 必须为至少 12 字符的独立密码。")
            if not self.database_url.startswith("mysql+pymysql://"):
                raise ValueError("生产环境必须配置 MySQL DATABASE_URL。")
            if not self.redis_url:
                raise ValueError("生产环境必须配置 REDIS_URL。")
        if not self.admin_username or len(self.admin_username) > 80:
            raise ValueError("ADMIN_USERNAME 长度必须为 1–80 字符。")
