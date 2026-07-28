import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Backend API"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["*"]

    # Database
    # DATABASE_URL: usado por Alembic (migraciones) y por defecto por la app. Con superuser (bloque) RLS no se aplica.
    # APP_DATABASE_URL: si está definido, la app usa este (ej. bloque_app) para que RLS sí se aplique. Ver docs/architecture/rls-multi-tenant.md
    DATABASE_URL: str = "postgresql://bloque:bloque_secret@localhost:5432/bloque_hub"
    APP_DATABASE_URL: str | None = None
    POSTGRES_USER: str = "bloque"
    POSTGRES_PASSWORD: str = "bloque_secret"
    POSTGRES_DB: str = "bloque_hub"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # Public catalog: tenant used when listing spaces without auth (e.g. GET /api/spaces). Optional.
    DEFAULT_TENANT_ID: str | None = None

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str | None = None

    # FEA (Firma Electrónica Avanzada) — mock or provider
    FEA_PROVIDER: str = "mock"
    FEA_WEBHOOK_SECRET: str = "change-me-webhook-secret"
    FEA_SKIP_HMAC_IN_TESTS: bool = False  # Allow bypass for mock/testing

    # Storage for signed contract PDFs (filesystem; no S3)
    CONTRACTS_STORAGE_PATH: str = "data/contracts"
    # Storage for evidence documents (Buzón de Evidencias; filesystem)
    EVIDENCE_STORAGE_PATH: str = "data/evidence"
    # Storage for payment vouchers (comprobantes SPEI; filesystem)
    PAYMENT_VOUCHERS_STORAGE_PATH: str = "data/payment_vouchers"
    # Imágenes promo del catálogo (hero / galería por espacio); filesystem, servidas en GET /api/media/space-promo/...
    SPACE_PROMO_MEDIA_PATH: str = "data/space_promo"
    MAX_SPACE_PROMO_IMAGE_BYTES: int = 5 * 1024 * 1024  # 5 MB

    # KYC / expediente borradores (mismo patrón; S3-ready via storage_key)
    RESERVATION_DOCUMENTS_STORAGE_PATH: str = "data/reservation_documents"
    MAX_KYC_FILE_BYTES: int = 10 * 1024 * 1024  # 10 MB
    MAX_KYC_GROUP_BYTES: int = 50 * 1024 * 1024  # 50 MB total por group_event_id
    KYC_DRAFT_TTL_HOURS: int = 72  # cleanup de borradores huérfanos (reservas abandonadas)

    # CFDI 4.0 (emisor: Municipio de Querétaro; PAC mock o Facturapi/SW Sápien)
    CFDI_PROVIDER: str = "mock"
    CFDI_EMISOR_RFC: str = "MQT800101XXX"
    CFDI_EMISOR_RAZON_SOCIAL: str = "Municipio de Querétaro"
    CFDI_EMISOR_REGIMEN: str = "601"
    CFDI_CODIGO_POSTAL: str = "76000"

    # Firmante delegado (si representante BLOQUE no firma en 24h)
    FEA_DELEGATE_SIGNER_EMAIL: str = "delegado@bloque.example"
    FEA_DELEGATE_SIGNER_NAME: str = "Firmante Delegado BLOQUE"

    # Notificaciones (email)
    EMAIL_PROVIDER: str = "mock"  # mock | smtp
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@bloque.example"
    # PR#9 FIX 4: explicit socket timeout for SMTP connections — without it a
    # hung/black-holed SMTP server can block the worker thread indefinitely.
    SMTP_TIMEOUT_SECONDS: float = 10.0
    NOTIFICATION_COMMERCIAL_EMAIL: str = "comercial@bloque.example"
    PORTAL_BASE_URL: str = "https://portal.bloque.example"
    # BLOQUE Portal gate (folio validation, RN-001/002/004) — REQ-012
    # Distinct from PORTAL_BASE_URL (display/link URL); this is the API host.
    PORTAL_API_BASE_URL: str = "https://portal.bloque.example"
    PORTAL_RETRY_ATTEMPTS: int = 3  # 1 initial + 2 retries
    PORTAL_API_KEY: str | None = None  # optional; header added only if set
    # REQ-013 (D9): HMAC credential pair for the real Portal integration route.
    # Annotated, NO default on purpose — a missing value must fail Settings()
    # construction at process start (loud, at boot) rather than at the first
    # request to the gate. Every environment that imports app.core.config
    # (local dev, CI, staging, production) must supply both. See
    # .env.example and tests/conftest.py for the local-double values.
    PORTAL_HUB_API_KEY: str
    PORTAL_HUB_API_SECRET: str
    # Storage for public wizard documents (quote_wizard_documents, Option B); filesystem
    WIZARD_DOCUMENTS_STORAGE_PATH: str = "data/wizard_documents"
    # PR#9 FIX 8: app-level cap on the number of files in one wizard submit —
    # nginx-level limits alone are not defense in depth for the application.
    MAX_WIZARD_FILES: int = 10
    # Legal copy URLs (placeholders until legal supplies canonical docs) — RN-014 checkboxes
    LEGAL_REGLAMENTO_URL: str = "https://bloque.example/reglamento"
    LEGAL_AVISO_PRIVACIDAD_URL: str = "https://bloque.example/aviso-privacidad"
    # Datos SPEI para Pase de Caja (placeholder si no hay integración)
    SPEI_CLABE: str = ""
    SPEI_REFERENCE_PREFIX: str = "BLOQUE"
    SPEI_SECRET_KEY: str = "test_secret"
    SPEI_BANCO: str = "Banco"

    # Rate limiting (PR#10, REQ-012) — public endpoints are unauthenticated
    # (no JWT) so they need per-IP throttling. `RATE_LIMIT_VALIDATE_FOLIO`,
    # `RATE_LIMIT_PRICE_PREVIEW`, `RATE_LIMIT_SUBMIT` use slowapi/`limits`
    # syntax ("N/second|minute|hour|day"). Kept mutable (plain settings
    # attributes, not frozen) so tests can monkeypatch a low limit for
    # deterministic 429 assertions — see `app/core/rate_limit.py`, which
    # reads them via a callable at request time (not decoration time).
    RATE_LIMIT_VALIDATE_FOLIO: str = "20/minute"
    RATE_LIMIT_PRICE_PREVIEW: str = "30/minute"  # cheapest amplification vector (no folio required)
    RATE_LIMIT_SUBMIT: str = "5/minute"  # sends email + writes files
    RATE_LIMIT_VALIDATE_DISCOUNT: str = "20/minute"  # public wizard discount preview
    RATE_LIMIT_PRECOTIZACION_PDF: str = "10/minute"  # WeasyPrint PDF — heavier than price-preview

    @property
    def RATE_LIMIT_STORAGE_URI(self) -> str:
        """Redis URI used by the rate limiter's storage backend.

        Reuses the Celery/Redis instance already configured via
        `CELERY_BROKER_URL`, but on a distinct logical DB (index 1 instead
        of 0) so rate-limit counters never collide with Celery's broker
        keys. Override with `RATE_LIMIT_REDIS_URL` env var if a dedicated
        Redis instance/DB is preferred (e.g. isolated test DB).
        """
        override = os.environ.get("RATE_LIMIT_REDIS_URL")
        if override:
            return override
        base = self.CELERY_BROKER_URL
        head, _, tail = base.rpartition("/")
        if head and tail.isdigit():
            return f"{head}/1"
        return base


settings = Settings()
