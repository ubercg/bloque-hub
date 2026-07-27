"""Public (no-auth) quote-request wizard service (REQ-012).

Design reference: openspec/changes/quote-request-folio/design.md §2.

`create_public_quote_request` is a NEW, dedicated service — it does NOT reuse
`create_quote`. `create_quote` has a pricing bug: it calls
`get_quote_for_space(db, tenant_id, space_id, start_time, end_time)` with two
`datetime`s (the real signature wants `target_date: date` + `duration_hours:
Decimal`), the wrong-typed call is swallowed by a broad `except (ValueError,
Exception)`, and it silently falls back to a caller-supplied `precio`. This
service calls `pricing.services.calculate_price` with the CORRECT types and
lets `NoPricingRuleError` propagate — no broad except, no client-trusted
fallback price (design §2.1, ADR-1).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time
from datetime import date as date_
from decimal import Decimal
from typing import Protocol, Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.crm.models import (
    Lead,
    Quote,
    QuoteItem,
    QuoteStatus,
    QuoteWizardDetails,
    QuoteWizardDocuments,
)
from app.modules.crm.schemas import PublicQuoteRequestCreate
from app.modules.inventory.services import apply_soft_hold_for_quote
from app.modules.pricing.models import PricingRule
from app.modules.pricing.services import NoPricingRuleError, get_pricing_rule_by_space


@dataclass(frozen=True)
class WizardDocumentMeta:
    """Metadata for an already-validated document (byte persistence is the
    submit endpoint's job, PR#4 — this service only writes the metadata row)."""

    storage_key: str
    mime_type: str
    size_bytes: int
    original_filename: str


class _PricedSlot(Protocol):
    space_id: UUID
    fecha: date_
    hora_inicio: time
    hora_fin: time


def _duration_hours(hora_inicio: time, hora_fin: time, fecha: date_) -> Decimal:
    """Compute item duration in hours as a Decimal, matching calculate_price's
    expected type (design §2.1 — the corrected pricing call)."""
    start = datetime.combine(fecha, hora_inicio)
    end = datetime.combine(fecha, hora_fin)
    secs = (end - start).total_seconds()
    return Decimal(str(secs / 3600.0)).quantize(Decimal("0.01"))


def _time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _allocate_totals(total: Decimal, weights: Sequence[Decimal]) -> list[Decimal]:
    """Split `total` across `weights` (hours), last slot absorbs rounding."""
    if not weights:
        return []
    sum_w = sum(weights, Decimal("0"))
    if sum_w <= 0:
        return [Decimal("0.00") for _ in weights]
    out: list[Decimal] = []
    acc = Decimal("0.00")
    last = len(weights) - 1
    for i, w in enumerate(weights):
        if i == last:
            out.append((total - acc).quantize(Decimal("0.01")))
        else:
            part = (total * w / sum_w).quantize(Decimal("0.01"))
            out.append(part)
            acc += part
    return out


def _package_price_for_duration(duration_hours: Decimal, rule: PricingRule) -> Decimal:
    """Package decomposition matching Detalle de Espacios / confirm-summary.

    Greedy: N×12h packs, then N×6h packs, remainder × extra_hour_rate.
    Differs from `calculate_hybrid_price` (tier jump: ≤6→base_6h, ≤12→base_12h),
    which made a 7h block jump to the 12h package and made each lone 1h slot
    cost base_6h — both wrong vs the catalog table the wizard shows.
    """
    remaining = Decimal(duration_hours)
    if remaining <= 0:
        raise ValueError("Duration hours must be > 0")

    total = Decimal("0.00")
    if rule.base_12h > 0:
        n12 = int(remaining // Decimal("12"))
        if n12:
            total += Decimal(n12) * rule.base_12h
            remaining -= Decimal(n12) * Decimal("12")
    if rule.base_6h > 0:
        n6 = int(remaining // Decimal("6"))
        if n6:
            total += Decimal(n6) * rule.base_6h
            remaining -= Decimal(n6) * Decimal("6")
    if remaining > 0:
        total += (remaining * rule.extra_hour_rate).quantize(Decimal("0.01"))
    return total.quantize(Decimal("0.01"))


def price_wizard_items(
    items: Sequence[_PricedSlot],
    tenant_id: UUID,
    db: Session,
) -> list[Decimal]:
    """Price wizard slots applying package rules to contiguous blocks.

    Inventory soft-holds stay per 1h slot, but catalog tariffs are packages
    (12h / 6h / hourly remainder). Contiguous slots on the same space+date are
    merged, priced once with that decomposition, then allocated back
    proportionally so bandeja, Detalle de Espacios and submit stay aligned.
    """
    n = len(items)
    prices = [Decimal("0.00")] * n
    if n == 0:
        return prices

    by_space_date: dict[tuple[UUID, date_], list[int]] = defaultdict(list)
    for i, item in enumerate(items):
        by_space_date[(item.space_id, item.fecha)].append(i)

    for (space_id, fecha), indices in by_space_date.items():
        rule = get_pricing_rule_by_space(db, tenant_id, space_id, fecha)
        if not rule:
            raise NoPricingRuleError(
                f"No pricing rule for space {space_id} on {fecha}"
            )

        indices.sort(
            key=lambda i: (
                _time_to_minutes(items[i].hora_inicio),
                _time_to_minutes(items[i].hora_fin),
            )
        )

        blocks: list[list[int]] = []
        current = [indices[0]]
        for idx in indices[1:]:
            prev = items[current[-1]]
            cur = items[idx]
            if _time_to_minutes(cur.hora_inicio) == _time_to_minutes(prev.hora_fin):
                current.append(idx)
            else:
                blocks.append(current)
                current = [idx]
        blocks.append(current)

        for block in blocks:
            first = items[block[0]]
            last = items[block[-1]]
            duration = _duration_hours(first.hora_inicio, last.hora_fin, fecha)
            block_price = _package_price_for_duration(duration, rule)
            weights = [
                _duration_hours(items[i].hora_inicio, items[i].hora_fin, fecha)
                for i in block
            ]
            allocated = _allocate_totals(block_price, weights)
            for i, price in zip(block, allocated):
                prices[i] = price

    return prices


def create_public_quote_request(
    tenant_id: UUID,
    payload: PublicQuoteRequestCreate,
    db: Session,
    documents: list[WizardDocumentMeta] | None = None,
) -> Quote:
    """Atomically create Lead + Quote(portal_folio) + QuoteItem[] +
    QuoteWizardDetails (incl. `servicios_apoyo`, a fixed enum list — REQ-012
    §4.5, PR#8 — not a catalog/pricing lookup) + QuoteWizardDocuments[],
    computing pricing with correct types and applying the multi-item soft hold.

    The caller (endpoint) owns `db.commit()` / `db.rollback()` and RN-004
    revalidation (which happens BEFORE this is called). This function only
    flushes — it never commits — so a caught exception + `db.rollback()` (or a
    closed, uncommitted session) leaves zero rows behind.

    Raises:
        NoPricingRuleError: a wizard item's space has no applicable
            PricingRule for its date — propagated, never swallowed.
        SlotNotAvailableError: any item's slot could not be soft-held
            (raised by `apply_soft_hold_for_quote`).
    """
    # 1. Lead from Step-3 requester data.
    lead = Lead(
        tenant_id=tenant_id,
        name=payload.nombre_completo,
        email=payload.correo_institucional,
        phone=payload.telefono_contacto,
        company=payload.institucion_organizacion,
    )
    db.add(lead)
    db.flush()

    # Pricing FIRST (correct types), so a NoPricingRuleError aborts before any
    # further persistence beyond the Lead (caller rolls back the whole tx).
    # Contiguous same-space/same-date slots are merged for package tariffs
    # (base_6h / base_12h), then allocated back per QuoteItem row.
    item_prices = price_wizard_items(payload.items, tenant_id, db)

    total = sum(item_prices, Decimal("0.00"))

    # 2. Quote (aggregate total, portal_folio set).
    quote = Quote(
        tenant_id=tenant_id,
        lead_id=lead.id,
        status=QuoteStatus.DRAFT,
        total=total,
        portal_folio=payload.folio,
    )
    db.add(quote)
    db.flush()

    # 3. QuoteItem[] — one per Step-2 block.
    for i, (item, price) in enumerate(zip(payload.items, item_prices)):
        db.add(
            QuoteItem(
                quote_id=quote.id,
                space_id=item.space_id,
                fecha=item.fecha,
                hora_inicio=item.hora_inicio,
                hora_fin=item.hora_fin,
                precio=price,
                item_order=i,
            )
        )
    db.flush()

    # 4. QuoteWizardDetails (Step 1/3/4 + legal acceptance flags). `servicios_apoyo`
    #    is a FIXED closed enum (REQ-012 §4.5, PR#8) persisted verbatim — NOT a
    #    catalog lookup, NOT priced.
    db.add(
        QuoteWizardDetails(
            tenant_id=tenant_id,
            quote_id=quote.id,
            tipo_evento=payload.tipo_evento,
            nombre_evento=payload.nombre_evento,
            caracter_evento=payload.caracter_evento,
            descripcion_evento=payload.descripcion_evento,
            asistentes_estimados=payload.asistentes_estimados,
            habra_prensa=payload.habra_prensa,
            nombre_completo=payload.nombre_completo,
            cargo_puesto=payload.cargo_puesto,
            institucion_organizacion=payload.institucion_organizacion,
            sector=payload.sector,
            sector_otro=payload.sector_otro,
            correo_institucional=payload.correo_institucional,
            telefono_contacto=payload.telefono_contacto,
            responsable_sitio_nombre=payload.responsable_sitio_nombre,
            responsable_sitio_telefono=payload.responsable_sitio_telefono,
            como_conociste_bloque=payload.como_conociste_bloque,
            como_conociste_otro=payload.como_conociste_otro,
            servicios_apoyo=[s.value for s in payload.servicios_apoyo],
            montaje_requerido=payload.montaje_requerido,
            requerimientos_especiales=payload.requerimientos_especiales,
            material_externo=payload.material_externo,
            material_externo_detalle=payload.material_externo_detalle,
            acepta_info_correcta_autorizacion=payload.acepta_info_correcta_autorizacion,
            acepta_reglamento_y_aviso_privacidad=payload.acepta_reglamento_y_aviso_privacidad,
        )
    )
    db.flush()

    # 5. QuoteWizardDocuments[] — metadata rows only (byte persistence is PR#4's
    #    job); zero rows if no documents were provided (option A/B compatible).
    for doc in documents or []:
        db.add(
            QuoteWizardDocuments(
                tenant_id=tenant_id,
                quote_id=quote.id,
                storage_key=doc.storage_key,
                mime_type=doc.mime_type,
                size_bytes=doc.size_bytes,
                original_filename=doc.original_filename,
            )
        )
    db.flush()

    # 6. Atomic multi-item soft hold — authoritative concurrency guard.
    #    Raises SlotNotAvailableError if any slot is no longer AVAILABLE; the
    #    caller rolls back the whole transaction (zero rows persisted).
    slots = [
        (item.space_id, item.fecha, item.hora_inicio, item.hora_fin)
        for item in payload.items
    ]
    apply_soft_hold_for_quote(quote.id, slots, tenant_id, db)

    return quote
