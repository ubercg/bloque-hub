"""Integration tests for `crm.public_service.create_public_quote_request`
multi-item atomicity (REQ-012, Phase 3 / PR#3, RN-012).

All-or-nothing within one transaction: either every item is available and
every row (Lead, Quote, QuoteItem[], QuoteWizardDetails, soft-hold) persists,
or nothing persists at all.
"""

from datetime import date, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.session import get_db_context
from app.modules.crm.models import (
    CaracterEvento,
    ComoConociste,
    Lead,
    MontajeRequerido,
    Quote,
    QuoteWizardDetails,
    Sector,
    TipoEvento,
)
from app.modules.crm.public_service import create_public_quote_request
from app.modules.crm.schemas import PublicQuoteRequestCreate, PublicWizardItem
from app.modules.inventory.models import Inventory, Space, SlotStatus
from app.modules.inventory.services import (
    SlotNotAvailableError,
    apply_soft_hold_for_quote,
)
from app.modules.pricing.models import PricingRule


def _make_space(db_super, tenant_id, suffix: str) -> Space:
    space = Space(
        tenant_id=tenant_id,
        name=f"Space {suffix}",
        slug=f"space-{suffix}",
        capacidad_maxima=100,
        precio_por_hora=500,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)
    return space


def _make_pricing_rule(db_super, tenant_id, space_id) -> None:
    db_super.add(
        PricingRule(
            tenant_id=tenant_id,
            space_id=space_id,
            base_6h=Decimal("100.0000"),
            base_12h=Decimal("180.0000"),
            extra_hour_rate=Decimal("20.0000"),
            discount_threshold=Decimal("0"),
            effective_from=date(2025, 1, 1),
            effective_to=None,
        )
    )
    db_super.commit()


def _valid_folio() -> str:
    return f"BCE-20260715-172822-{uuid4().int % 10000:04d}"


def _base_payload(**overrides) -> dict:
    payload = {
        "folio": _valid_folio(),
        "tipo_evento": TipoEvento.CONFERENCIA,
        "nombre_evento": None,
        "caracter_evento": CaracterEvento.PUBLICO,
        "descripcion_evento": "Evento de prueba",
        "asistentes_estimados": 50,
        "habra_prensa": False,
        "items": [],
        "nombre_completo": "Ana Lopez",
        "cargo_puesto": "Coordinadora",
        "institucion_organizacion": "Municipio Y",
        "sector": Sector.GOBIERNO_MUNICIPAL_ESTATAL_FEDERAL,
        "sector_otro": None,
        "correo_institucional": "ana.lopez@municipio.gob.mx",
        "telefono_contacto": "5555555556",
        "responsable_sitio_nombre": None,
        "responsable_sitio_telefono": None,
        "como_conociste_bloque": ComoConociste.REDES_SOCIALES,
        "como_conociste_otro": None,
        "servicios_apoyo": [],
        "montaje_requerido": MontajeRequerido.TEATRO,
        "requerimientos_especiales": None,
        "material_externo": False,
        "material_externo_detalle": None,
        "acepta_info_correcta_autorizacion": True,
        "acepta_reglamento_y_aviso_privacidad": True,
    }
    payload.update(overrides)
    return payload


@pytest.mark.integration
def test_all_items_available_persists_all_rows_and_soft_hold(tenant_a, db_super):
    space_1 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
    space_2 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
    _make_pricing_rule(db_super, tenant_a.id, space_1.id)
    _make_pricing_rule(db_super, tenant_a.id, space_2.id)

    day_1 = date.today() + timedelta(days=40)
    day_2 = date.today() + timedelta(days=41)
    items = [
        PublicWizardItem(
            space_id=space_1.id, fecha=day_1, hora_inicio="10:00:00", hora_fin="12:00:00"
        ),
        PublicWizardItem(
            space_id=space_2.id, fecha=day_2, hora_inicio="10:00:00", hora_fin="12:00:00"
        ),
    ]
    payload = PublicQuoteRequestCreate(**_base_payload(items=items))

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        quote = create_public_quote_request(tenant_a.id, payload, db)
        db.commit()
        quote_id = quote.id

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        persisted = db.get(Quote, quote_id)
        assert persisted is not None
        assert persisted.lead is not None
        assert len(persisted.items) == 2
        assert persisted.wizard_details is not None

        for space, day in ((space_1, day_1), (space_2, day_2)):
            slot = (
                db.query(Inventory)
                .filter(
                    Inventory.space_id == space.id,
                    Inventory.fecha == day,
                )
                .first()
            )
            assert slot is not None
            assert slot.estado == SlotStatus.SOFT_HOLD
            assert slot.quote_id == quote_id


@pytest.mark.integration
def test_one_item_unavailable_rolls_back_everything(tenant_a, db_super):
    """One item pre-held by another quote -> SlotNotAvailableError and ZERO
    rows persisted for this attempt (verified via DB query after rollback)."""
    space_1 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
    space_2 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
    _make_pricing_rule(db_super, tenant_a.id, space_1.id)
    _make_pricing_rule(db_super, tenant_a.id, space_2.id)

    day_1 = date.today() + timedelta(days=50)
    day_2 = date.today() + timedelta(days=51)

    # Pre-hold space_2's slot for a different quote so the second item
    # conflicts.
    other_quote_id = uuid4()
    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        apply_soft_hold_for_quote(
            other_quote_id,
            [(space_2.id, day_2, time(10, 0), time(12, 0))],
            tenant_a.id,
            db,
        )
        db.commit()

    items = [
        PublicWizardItem(
            space_id=space_1.id, fecha=day_1, hora_inicio="10:00:00", hora_fin="12:00:00"
        ),
        PublicWizardItem(
            space_id=space_2.id, fecha=day_2, hora_inicio="10:00:00", hora_fin="12:00:00"
        ),
    ]
    payload = PublicQuoteRequestCreate(**_base_payload(items=items))

    with pytest.raises(SlotNotAvailableError):
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            create_public_quote_request(tenant_a.id, payload, db)

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        leads = (
            db.query(Lead)
            .filter(Lead.email == "ana.lopez@municipio.gob.mx")
            .all()
        )
        assert leads == []
        quotes = (
            db.query(Quote).filter(Quote.portal_folio == payload.folio).all()
        )
        assert quotes == []
        wizard_details = (
            db.query(QuoteWizardDetails)
            .filter(QuoteWizardDetails.correo_institucional == "ana.lopez@municipio.gob.mx")
            .all()
        )
        assert wizard_details == []

        # space_1's slot must NOT have been left soft-held by the rolled-back
        # attempt.
        slot_1 = (
            db.query(Inventory)
            .filter(Inventory.space_id == space_1.id, Inventory.fecha == day_1)
            .first()
        )
        assert slot_1 is None or slot_1.estado == SlotStatus.AVAILABLE
