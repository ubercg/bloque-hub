"""Public API endpoints (no JWT required)."""

import json
import logging
import mimetypes
import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError

from datetime import date, time

from app.core.config import settings
from app.db.session import get_db_context
from app.modules.crm.public_service import (
    WizardDocumentMeta,
    _duration_hours,
    create_public_quote_request,
)
from app.modules.crm.schemas import PublicQuoteRequestCreate
from app.modules.identity.models import Tenant
from app.modules.inventory.services import (
    SlotNotAvailableError,
    check_group_availability,
)
from app.modules.notifications.email_service import send_email
from app.modules.notifications.templating import render
from app.modules.portal_gate import client as portal_gate_client
from app.modules.portal_gate.client import PortalFolioStatus, PortalUnavailableError, is_valid_folio_format
from app.modules.pricing.services import NoPricingRuleError, calculate_price
from app.modules.reservation_documents.services import (
    _ALLOWED_MIME_NORMALIZED,
    _ext_for_mime,
    normalize_mime,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["public"])

# RN-003 fixed message (design.md §2.2, §4.4).
_FOLIO_NOT_ELIGIBLE_MESSAGE = (
    "El folio proporcionado no se encuentra disponible para iniciar una "
    "cotización. Verifica el estatus en BLOQUE Portal."
)
_PORTAL_UNAVAILABLE_MESSAGE = "Portal no disponible, intenta más tarde."

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
def validate_quote_request_folio(payload: FolioValidateRequest):
    """
    Folio gate (RN-001/002/003/017). Format is checked BEFORE any outbound
    call to Portal — a malformed folio never triggers `portal_gate_client`.
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
        portal_status = portal_gate_client.validate_folio(payload.folio)
    except PortalUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"reason": "PORTAL_UNAVAILABLE", "message": _PORTAL_UNAVAILABLE_MESSAGE},
        )

    if portal_status != PortalFolioStatus.ELIGIBLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason": "FOLIO_NOT_ELIGIBLE", "message": _FOLIO_NOT_ELIGIBLE_MESSAGE},
        )

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
def preview_quote_request_price(payload: PricePreviewRequest):
    """
    Public (no-auth) ADVISORY pricing preview for wizard Step 2
    (design.md §6.6). An anonymous client cannot call the JWT-protected
    `POST /quotes/calculate` or `/pricing-rules` endpoints, so this small
    endpoint lets Step 2 render `cotizacionCalculada` before submit.

    The authoritative price is ALWAYS recomputed server-side at submit
    (`create_public_quote_request` -> `calculate_price`, same correct-types
    call as this endpoint uses) — this preview never persists anything and
    is not trusted for the final total.

    `total` aggregates only the space prices (spaces-only total, matching
    the locked submit-total decision) — no additional services here.
    """
    tenant_id = UUID(str(settings.DEFAULT_TENANT_ID))

    with get_db_context(tenant_id=str(tenant_id), role=None) as db:
        try:
            results = []
            for item in payload.items:
                duration_hours = _duration_hours(
                    item.hora_inicio, item.hora_fin, item.fecha
                )
                breakdown = calculate_price(
                    space_id=item.space_id,
                    duration_hours=duration_hours,
                    tenant_id=tenant_id,
                    target_date=item.fecha,
                    db=db,
                )
                results.append(
                    PricePreviewItemResult(
                        space_id=item.space_id,
                        fecha=item.fecha,
                        hora_inicio=item.hora_inicio,
                        hora_fin=item.hora_fin,
                        price=float(breakdown.total_price),
                    )
                )
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


@router.post(
    "/public/quote-requests",
    response_model=QuoteRequestSubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_quote_request(
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
        portal_status = portal_gate_client.validate_folio(parsed.folio)
    except PortalUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"reason": "PORTAL_UNAVAILABLE", "message": _PORTAL_UNAVAILABLE_MESSAGE},
        )
    if portal_status != PortalFolioStatus.ELIGIBLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason": "FOLIO_NOT_ELIGIBLE", "message": _FOLIO_NOT_ELIGIBLE_MESSAGE},
        )

    tenant_id = UUID(str(settings.DEFAULT_TENANT_ID))
    written_paths: list[Path] = []
    quote_id: UUID
    quote_total: float

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
                # Read scalar values BEFORE the session closes (get_db_context
                # closes on exit) to avoid a DetachedInstanceError on return.
                quote_id = quote.id
                quote_total = float(quote.total)
            except (SlotNotAvailableError, IntegrityError, NoPricingRuleError, ValueError):
                db.rollback()
                raise
    except SlotNotAvailableError as exc:
        _cleanup_written_files(written_paths)
        # `SlotNotAvailableError` is raised from two different call sites with
        # different `args[0]` shapes: `check_group_availability` raises with a
        # list of conflict dicts, but the authoritative `with_for_update()`
        # lock in `apply_soft_hold_for_quote` raises with a plain STRING
        # message (services.py). Normalize so the string-arg (lock) path still
        # maps to a clean 409 instead of crashing on `.items()`.
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
    except IntegrityError:
        _cleanup_written_files(written_paths)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"reason": "DUPLICATE_FOLIO"},
        )
    except NoPricingRuleError:
        _cleanup_written_files(written_paths)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "NO_PRICING_RULE"},
        )
    except ValueError as exc:
        _cleanup_written_files(written_paths)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "INVALID_REQUEST", "message": str(exc)},
        )

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
