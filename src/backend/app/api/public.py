"""Public API endpoints (no JWT required)."""

import json
import logging
import mimetypes
import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import IntegrityError

from datetime import date, time

from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.session import get_db_context
from app.modules.crm.public_service import (
    WizardDocumentMeta,
    create_public_quote_request,
    price_wizard_items,
)
from app.modules.crm.schemas import PublicQuoteRequestCreate
from app.modules.identity.models import Tenant
from app.modules.inventory.services import (
    SlotNotAvailableError,
    check_group_availability,
)
from app.modules.notifications.email_service import send_email
from app.modules.notifications.templating import render
from app.api.portal_gate_http import raise_for_portal_status
from app.modules.portal_gate import client as portal_gate_client
from app.modules.portal_gate.client import PortalFolioStatus, PortalUnavailableError, is_valid_folio_format
from app.modules.pricing.services import NoPricingRuleError
from app.modules.reservation_documents.services import (
    _ALLOWED_MIME_NORMALIZED,
    _ext_for_mime,
    normalize_mime,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["public"])

# REQ-013 B2: the FOLIO_NOT_ELIGIBLE / PORTAL_UNAVAILABLE / INTEGRATION_AUTH_
# FAILURE copy now lives in `api/portal_gate_http.py` as the single source
# both call sites below read from via `raise_for_portal_status` — no
# duplicated message strings, no per-site catch-all.

_SPACE_PROMO_FILENAME = re.compile(
    r"^[a-f0-9]{32}\.(jpe?g|png|webp|gif)$",
    re.IGNORECASE,
)


class SedeRead(BaseModel):
    """Sede (tenant) for public catalog selector."""

    id: UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


@router.get("/media/space-promo/{tenant_id}/{filename}")
def get_space_promo_media(tenant_id: UUID, filename: str):
    """
    Sirve imágenes subidas para el catálogo (hero/galería). Sin autenticación
    para que `<img src>` funcione en el catálogo público.
    """
    if not _SPACE_PROMO_FILENAME.match(filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    base = Path(settings.SPACE_PROMO_MEDIA_PATH) / str(tenant_id)
    path = (base / filename).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


@router.get("/public/sedes", response_model=list[SedeRead])
def list_sedes():
    """
    List active tenants (sedes) for public catalog.
    No authentication required. Used when the user is anonymous to choose a sede
    or to show a single-sede catalog.
    """
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        tenants = db.query(Tenant).filter(Tenant.is_active.is_(True)).order_by(Tenant.name).all()
        return [SedeRead.model_validate(t) for t in tenants]


# ----- Public quote-request wizard (REQ-012, PR#4: gate + submit endpoints) -----


class FolioValidateRequest(BaseModel):
    folio: str


class FolioValidateResponse(BaseModel):
    unlocked: bool
    folio: str
    portal_status: str


class QuoteRequestSubmitResponse(BaseModel):
    quote_id: UUID
    total: float
    email_sent: bool


@router.post(
    "/public/quote-requests/validate-folio",
    response_model=FolioValidateResponse,
)
@limiter.limit(lambda: settings.RATE_LIMIT_VALIDATE_FOLIO)
def validate_quote_request_folio(request: Request, payload: FolioValidateRequest):
    """
    Folio gate (RN-001/002/003/017). Format is checked BEFORE any outbound
    call to Portal — a malformed folio never triggers `portal_gate_client`.

    Rate limited per-IP (PR#10, `settings.RATE_LIMIT_VALIDATE_FOLIO`,
    default `20/minute`) — unauthenticated, so throttling is the only
    protection against abuse.
    """
    if not is_valid_folio_format(payload.folio):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": "INVALID_FOLIO_FORMAT",
                "message": "El folio debe tener el formato BCE-YYYYMMDD-HHMMSS-RRRR.",
            },
        )

    try:
        result = portal_gate_client.validate_folio(payload.folio)
    except PortalUnavailableError:
        raise_for_portal_status(PortalFolioStatus.UNAVAILABLE)
    raise_for_portal_status(result.status)

    return FolioValidateResponse(
        unlocked=True,
        folio=payload.folio,
        portal_status=portal_gate_client.PORTAL_ELIGIBLE_STATUS_VALUE,
    )


# ----- Public pricing preview (REQ-012, PR#6b: fills a gap found during -----
# ----- Phase 7 planning — design §6.6 anticipated it as a small, advisory ---
# ----- public pricing-preview endpoint if needed) ---------------------------


class PricePreviewItem(BaseModel):
    space_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time


class PricePreviewRequest(BaseModel):
    items: list[PricePreviewItem]


class PricePreviewItemResult(BaseModel):
    space_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time
    price: float


class PricePreviewResponse(BaseModel):
    items: list[PricePreviewItemResult]
    total: float


@router.post(
    "/public/quote-requests/price-preview",
    response_model=PricePreviewResponse,
)
@limiter.limit(lambda: settings.RATE_LIMIT_PRICE_PREVIEW)
def preview_quote_request_price(request: Request, payload: PricePreviewRequest):
    """
    Public (no-auth) ADVISORY pricing preview for wizard Step 2
    (design.md §6.6). An anonymous client cannot call the JWT-protected
    `POST /quotes/calculate` or `/pricing-rules` endpoints, so this small
    endpoint lets Step 2 render `cotizacionCalculada` before submit.

    The authoritative price is ALWAYS recomputed server-side at submit
    (`create_public_quote_request` -> `price_wizard_items` / `calculate_price`)
    — this preview never persists anything and is not trusted for the final
    total.

    Contiguous slots on the same space+date are merged before pricing so the
    hybrid package tariff (base_6h / base_12h / extra_hour) matches Detalle de
    Espacios; per-item prices in the response are the allocated share.

    `total` aggregates only the space prices (spaces-only total, matching
    the locked submit-total decision) — no additional services here.

    Rate limited per-IP (PR#10, `settings.RATE_LIMIT_PRICE_PREVIEW`,
    default `30/minute`) — flagged in the 4R review as the CHEAPEST
    amplification vector of the three public endpoints: it needs no valid
    folio at all, only tenant/space/date/time.
    """
    tenant_id = UUID(str(settings.DEFAULT_TENANT_ID))

    with get_db_context(tenant_id=str(tenant_id), role=None) as db:
        try:
            item_prices = price_wizard_items(payload.items, tenant_id, db)
            results = [
                PricePreviewItemResult(
                    space_id=item.space_id,
                    fecha=item.fecha,
                    hora_inicio=item.hora_inicio,
                    hora_fin=item.hora_fin,
                    price=float(price),
                )
                for item, price in zip(payload.items, item_prices)
            ]
        except NoPricingRuleError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"reason": "NO_PRICING_RULE"},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"reason": "INVALID_REQUEST", "message": str(exc)},
            )

    total = sum((item.price for item in results), 0.0)
    return PricePreviewResponse(items=results, total=total)


# ----- Public precotización PDF (REQ-012 wizard Step 5, anonymous) ----------


class PrecotizacionPdfItem(BaseModel):
    space_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time


class PrecotizacionPdfRequest(BaseModel):
    items: list[PrecotizacionPdfItem] = Field(..., min_length=1)
    discount_code: str | None = None
    client_name: str = ""
    client_email: str = ""
    event_name: str = "Solicitud de cotización"
    document_ref: str = "borrador"
    asistentes_estimados: int | None = None


@router.post("/public/quote-requests/precotizacion.pdf")
@limiter.limit(lambda: settings.RATE_LIMIT_PRECOTIZACION_PDF)
def download_wizard_precotizacion_pdf(request: Request, payload: PrecotizacionPdfRequest):
    """Advisory PDF for wizard Step 5 — same template as portal precotización.

    No JWT. Does not persist. Recomputes Detalle de Espacios + optional discount
    from `discount_code`. Rate-limited (WeasyPrint is relatively expensive).
    """
    from app.modules.booking.order_table_rows import CartItem
    from app.modules.booking.precotizacion_pdf import generate_cart_precotizacion_pdf_bytes
    from app.modules.inventory.models import Space

    if not settings.DEFAULT_TENANT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"reason": "DEFAULT_TENANT_UNSET"},
        )

    tenant_id = UUID(str(settings.DEFAULT_TENANT_ID))

    with get_db_context(tenant_id=str(tenant_id), role=None) as db:
        sids = {it.space_id for it in payload.items}
        spaces = db.query(Space).filter(Space.id.in_(sids), Space.tenant_id == tenant_id).all()
        names = {s.id: s.name for s in spaces}
        missing = sids - set(names)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"reason": "UNKNOWN_SPACE", "message": "Uno o más espacios no existen."},
            )

        cart = [
            CartItem(
                space_id=it.space_id,
                space_name=names[it.space_id],
                fecha=it.fecha,
                hora_inicio=it.hora_inicio.strftime("%H:%M"),
                hora_fin=it.hora_fin.strftime("%H:%M"),
                precio=0,
            )
            for it in payload.items
        ]

        try:
            pdf_bytes = generate_cart_precotizacion_pdf_bytes(
                db,
                tenant_id,
                cart,
                client_name=(payload.client_name or "").strip() or "—",
                client_email=(payload.client_email or "").strip() or "—",
                event_name=(payload.event_name or "").strip() or "Solicitud de cotización",
                document_ref=(payload.document_ref or "").strip() or "borrador",
                discount_code=payload.discount_code,
                aforo_personas=payload.asistentes_estimados,
            )
        except Exception:
            logger.exception("Failed to generate wizard precotizacion PDF")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"reason": "PDF_GENERATION_FAILED", "message": "No se pudo generar el PDF."},
            )

    safe_ref = "".join(c if c.isalnum() or c in "-_" else "-" for c in (payload.document_ref or "borrador"))[:48]
    filename = f"precotizacion-{safe_ref or 'borrador'}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ----- Public discount preview (REQ-012 wizard Step 2, anonymous) ------------


class PublicDiscountValidateRequest(BaseModel):
    code: str
    subtotal: float


class PublicDiscountValidateResponse(BaseModel):
    valid: bool
    code: str
    discount_code_id: UUID | None = None
    discount_type: str | None = None
    discount_value: float | None = None
    discount_amount: float
    subtotal: float
    total: float
    reason: str | None = None


@router.post(
    "/public/quote-requests/validate-discount",
    response_model=PublicDiscountValidateResponse,
)
@limiter.limit(lambda: settings.RATE_LIMIT_VALIDATE_DISCOUNT)
def validate_public_discount_code(request: Request, payload: PublicDiscountValidateRequest):
    """Advisory discount preview for the anonymous quote wizard.

    No JWT. Uses DEFAULT_TENANT_ID (same as price-preview). Does not consume
    usage / does not persist — submit may re-validate later. Skips
    single_use_per_user (no authenticated user). Rate-limited per IP.
    """
    from decimal import Decimal

    from app.modules.discounts.services import (
        DiscountValidationError,
        normalize_discount_code,
        validate_code_for_subtotal,
    )

    if not settings.DEFAULT_TENANT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"reason": "DEFAULT_TENANT_UNSET"},
        )

    tenant_id = UUID(str(settings.DEFAULT_TENANT_ID))
    subtotal = Decimal(str(payload.subtotal)).quantize(Decimal("0.01"))
    code = normalize_discount_code(payload.code)

    with get_db_context(tenant_id=str(tenant_id), role=None) as db:
        try:
            discount_code, discount_amount, total = validate_code_for_subtotal(
                db=db,
                tenant_id=tenant_id,
                code=code,
                subtotal=subtotal,
                user_id=None,
            )
            return PublicDiscountValidateResponse(
                valid=True,
                code=discount_code.code,
                discount_code_id=discount_code.id,
                discount_type=str(discount_code.discount_type),
                discount_value=float(discount_code.discount_value),
                discount_amount=float(discount_amount),
                subtotal=float(subtotal),
                total=float(total),
                reason=None,
            )
        except DiscountValidationError as exc:
            return PublicDiscountValidateResponse(
                valid=False,
                code=code,
                discount_amount=0.0,
                subtotal=float(subtotal),
                total=float(subtotal),
                reason=exc.reason,
            )


def _wizard_documents_storage_dir() -> Path:
    p = Path(settings.WIZARD_DOCUMENTS_STORAGE_PATH)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cleanup_written_files(paths: list[Path]) -> None:
    """Best-effort cleanup of file bytes written before a transaction rolled
    back, so an aborted submit never leaves orphaned files on disk."""
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


_DUPLICATE_FOLIO_CONSTRAINT = "uq_quotes_portal_folio"


def _is_duplicate_folio_integrity_error(exc: IntegrityError) -> bool:
    """PR#9 FIX 6: only classify an `IntegrityError` as DUPLICATE_FOLIO when
    it actually names the `portal_folio` unique constraint. A broad
    `except IntegrityError -> 409 DUPLICATE_FOLIO` mislabels any other
    constraint violation (e.g. a future FK/NOT NULL constraint) as a
    duplicate-folio replay, which is both wrong for the client and hides a
    real bug from monitoring."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name:
        return constraint_name == _DUPLICATE_FOLIO_CONSTRAINT
    # Fallback for drivers/backends without `.diag` (e.g. SQLite in unit
    # tests) — inspect the stringified error for the constraint name.
    return _DUPLICATE_FOLIO_CONSTRAINT in str(exc)


@router.post(
    "/public/quote-requests",
    response_model=QuoteRequestSubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(lambda: settings.RATE_LIMIT_SUBMIT)
def submit_quote_request(
    request: Request,
    payload: str = Form(...),
    files: list[UploadFile] = File(default=[]),
):
    """
    Wizard submit (RN-004..014, RN-015, RN-017). multipart/form-data: `payload`
    is a JSON string parsed into `PublicQuoteRequestCreate`; `files` are 0..N
    documents. Transaction boundary per design.md §4.2 (exact ordering):
      1. Parse + validate payload -> 422, nothing touched
      2. Validate files (MIME/size) -> 422, nothing touched, no Portal call
      3. RN-004 revalidation BEFORE opening the write tx -> 403 / 503
      4. Availability pre-check -> write files -> create_public_quote_request -> commit
      5. Map SlotNotAvailableError/IntegrityError/NoPricingRuleError/ValueError -> 409/422

    Rate limited per-IP (PR#10, `settings.RATE_LIMIT_SUBMIT`, default
    `5/minute`) — the strictest of the three public limits: this is the
    only one that sends an email and writes files to disk.
    """
    # 1. Parse + validate payload.
    try:
        payload_dict = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "INVALID_PAYLOAD", "message": "payload debe ser JSON válido."},
        )

    try:
        parsed = PublicQuoteRequestCreate(**payload_dict)
    except ValidationError as exc:
        # `exc.errors()` includes a `ctx.error` exception instance (pydantic v2),
        # which is not JSON-serializable — strip it down to plain, safe fields.
        errors = [
            {"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=errors,
        )

    # 2. Validate uploaded files (RN-015) — reuse existing MIME/size rules.
    #    No DB touched, no Portal call yet.
    # PR#9 FIX 8: app-level file COUNT cap, checked BEFORE reading/writing
    # any file byte — nginx-level limits alone are not defense in depth.
    if len(files) > settings.MAX_WIZARD_FILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": "TOO_MANY_FILES",
                "message": f"Máximo {settings.MAX_WIZARD_FILES} archivos permitidos.",
            },
        )

    validated_files: list[tuple[str, str, bytes]] = []
    for upload in files:
        content = upload.file.read()
        mime = normalize_mime(upload.content_type or "")
        if mime not in _ALLOWED_MIME_NORMALIZED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "reason": "INVALID_FILE_MIME",
                    "message": f"Tipo de archivo no permitido: {upload.content_type}",
                },
            )
        if len(content) > settings.MAX_KYC_FILE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "reason": "FILE_TOO_LARGE",
                    "message": f"El archivo {upload.filename} excede el tamaño máximo permitido.",
                },
            )
        validated_files.append((upload.filename or "documento", mime, content))

    # 3. RN-004 revalidation BEFORE opening the write transaction.
    try:
        result = portal_gate_client.validate_folio(parsed.folio)
    except PortalUnavailableError:
        raise_for_portal_status(PortalFolioStatus.UNAVAILABLE)
    raise_for_portal_status(result.status)

    tenant_id = UUID(str(settings.DEFAULT_TENANT_ID))
    written_paths: list[Path] = []
    quote_id: UUID
    quote_total: float
    # PR#9 FIX 3: tracks whether the transaction actually committed. The
    # `finally` block below cleans up `written_paths` whenever it did NOT —
    # regardless of WHICH exception type caused that, not just the 4 mapped
    # ones — so no failure mode (known or unexpected) can leave orphaned
    # files on disk with no DB row referencing them.
    committed = False

    try:
        try:
            with get_db_context(tenant_id=str(tenant_id), role=None) as db:
                try:
                    group = check_group_availability(
                        [
                            {
                                "espacio_id": item.space_id,
                                "fecha": item.fecha,
                                "hora_inicio": item.hora_inicio,
                                "hora_fin": item.hora_fin,
                            }
                            for item in parsed.items
                        ],
                        db=db,
                        role=None,
                    )
                    if not group["all_available"]:
                        raise SlotNotAvailableError(group["conflicts"])

                    documents: list[WizardDocumentMeta] = []
                    storage_dir = _wizard_documents_storage_dir()
                    for filename, mime, content in validated_files:
                        doc_id = uuid4()
                        ext = _ext_for_mime(mime)
                        storage_key = f"{tenant_id}/{doc_id}{ext}"
                        full_path = storage_dir / storage_key
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        full_path.write_bytes(content)
                        written_paths.append(full_path)
                        documents.append(
                            WizardDocumentMeta(
                                storage_key=storage_key,
                                mime_type=mime,
                                size_bytes=len(content),
                                original_filename=filename,
                            )
                        )

                    quote = create_public_quote_request(
                        tenant_id, parsed, db, documents=documents
                    )
                    db.commit()
                    committed = True
                    # Read scalar values BEFORE the session closes
                    # (get_db_context closes on exit) to avoid a
                    # DetachedInstanceError on return.
                    quote_id = quote.id
                    quote_total = float(quote.total)
                except Exception:
                    db.rollback()
                    raise
        except SlotNotAvailableError as exc:
            # `SlotNotAvailableError` is raised from two different call sites
            # with different `args[0]` shapes: `check_group_availability`
            # raises with a list of conflict dicts, but the authoritative
            # `with_for_update()` lock in `apply_soft_hold_for_quote` raises
            # with a plain STRING message (services.py). Normalize so the
            # string-arg (lock) path still maps to a clean 409 instead of
            # crashing on `.items()`.
            raw_conflicts = (
                exc.args[0]
                if exc.args and isinstance(exc.args[0], list)
                else []
            )
            conflicts = [
                {
                    key: (str(value) if isinstance(value, UUID) else value)
                    for key, value in conflict.items()
                }
                for conflict in raw_conflicts
            ]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"reason": "SLOT_UNAVAILABLE", "conflicts": conflicts},
            )
        except IntegrityError as exc:
            # PR#9 FIX 6: only DUPLICATE_FOLIO when it's actually the
            # `portal_folio` unique constraint — any other IntegrityError is
            # a different bug and must not be mislabeled, so re-raise it as
            # an unexpected 500.
            if not _is_duplicate_folio_integrity_error(exc):
                raise
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"reason": "DUPLICATE_FOLIO"},
            ) from exc
        except NoPricingRuleError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"reason": "NO_PRICING_RULE"},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"reason": "INVALID_REQUEST", "message": str(exc)},
            )
    finally:
        if not committed:
            _cleanup_written_files(written_paths)

    # Best-effort confirmation email (RN-016, design.md §5). Placed AFTER
    # commit, in the endpoint (not the service), so a mail failure can never
    # touch the transaction. No NotificationLog write (it FKs reservations,
    # not quotes).
    email_sent = False
    try:
        html = render(
            "public_quote_confirmation.html",
            nombre_completo=parsed.nombre_completo,
            folio=parsed.folio,
            total=quote_total,
        )
        send_email(
            to=parsed.correo_institucional,
            subject="Recibimos tu solicitud de cotización",
            html_body=html,
        )
        email_sent = True
    except Exception as exc:
        logger.warning("Confirmation email failed for quote %s: %s", quote_id, exc)

    return QuoteRequestSubmitResponse(
        quote_id=quote_id, total=quote_total, email_sent=email_sent
    )
