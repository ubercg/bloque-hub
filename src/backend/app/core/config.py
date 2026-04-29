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
    NOTIFICATION_COMMERCIAL_EMAIL: str = "comercial@bloque.example"
    PORTAL_BASE_URL: str = "https://portal.bloque.example"
    # Datos SPEI para Pase de Caja (placeholder si no hay integración)
    SPEI_CLABE: str = ""
    SPEI_REFERENCE_PREFIX: str = "BLOQUE"
    SPEI_SECRET_KEY: str = "test_secret"
    SPEI_BANCO: str = "Banco"


settings = Settings()
