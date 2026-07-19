"""Integration tests for `crm.public_service.create_public_quote_request` pricing
correctness (REQ-012, Phase 3 / PR#3).

This is the regression suite proving the new service does NOT replicate the
`create_quote` bug: `get_quote_for_space`/`calculate_price` must be called with
`target_date: date` + `duration_hours: Decimal`, `NoPricingRuleError` must
propagate (never swallowed by a broad `except`, never silently defaulted).
"""

from datetime import date, timedelta
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
    Sector,
    TipoEvento,
)
from app.modules.crm.public_service import create_public_quote_request
from app.modules.crm.schemas import PublicQuoteRequestCreate, PublicWizardItem
from app.modules.inventory.models import Space
from app.modules.pricing.models import PricingRule
from app.modules.pricing.services import NoPricingRuleError, calculate_price
from tests.conftest import unique_portal_folio


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


def _make_pricing_rule(db_super, tenant_id, space_id) -> PricingRule:
    rule = PricingRule(
        tenant_id=tenant_id,
        space_id=space_id,
        base_6h=Decimal("100.0000"),
        base_12h=Decimal("180.0000"),
        extra_hour_rate=Decimal("20.0000"),
        discount_threshold=Decimal("0"),
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )
    db_super.add(rule)
    db_super.commit()
    return rule


def _valid_folio() -> str:
    return unique_portal_folio()


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
        "nombre_completo": "Juan Perez",
        "cargo_puesto": "Director",
        "institucion_organizacion": "Municipio X",
        "sector": Sector.GOBIERNO_MUNICIPAL_ESTATAL_FEDERAL,
        "sector_otro": None,
        "correo_institucional": "juan.perez@municipio.gob.mx",
        "telefono_contacto": "5555555555",
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
def test_pricing_matches_calculate_price_exactly(tenant_a, db_super):
    """Regression: computed item price equals calculate_price(...) result
    exactly — NOT the broken create_quote pattern (broad except + fallback)."""
    space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
    _make_pricing_rule(db_super, tenant_a.id, space.id)

    event_day = date.today() + timedelta(days=30)
    item = PublicWizardItem(
        space_id=space.id,
        fecha=event_day,
        hora_inicio="10:00:00",
        hora_fin="12:00:00",
    )
    payload = PublicQuoteRequestCreate(**_base_payload(items=[item]))

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        quote = create_public_quote_request(tenant_a.id, payload, db)
        db.commit()
        quote_id = quote.id

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        expected = calculate_price(
            space_id=space.id,
            duration_hours=Decimal("2.00"),
            tenant_id=tenant_a.id,
            target_date=event_day,
            db=db,
        )
        persisted = db.get(Quote, quote_id)
        assert persisted is not None
        assert Decimal(str(persisted.total)) == expected.total_price
        assert len(persisted.items) == 1
        assert Decimal(str(persisted.items[0].precio)) == expected.total_price


@pytest.mark.integration
def test_no_pricing_rule_propagates_not_silently_defaulted(tenant_a, db_super):
    """A space with NO PricingRule must raise NoPricingRuleError — never a
    silent fallback default (that was the create_quote bug)."""
    space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
    # No PricingRule created for this space.

    event_day = date.today() + timedelta(days=30)
    item = PublicWizardItem(
        space_id=space.id,
        fecha=event_day,
        hora_inicio="10:00:00",
        hora_fin="12:00:00",
    )
    payload = PublicQuoteRequestCreate(**_base_payload(items=[item]))

    with pytest.raises(NoPricingRuleError):
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            create_public_quote_request(tenant_a.id, payload, db)

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        leads = (
            db.query(Lead)
            .filter(Lead.email == "juan.perez@municipio.gob.mx")
            .all()
        )
        assert leads == []
        quotes = (
            db.query(Quote).filter(Quote.portal_folio == payload.folio).all()
        )
        assert quotes == []


@pytest.mark.integration
def test_multi_item_aggregate_equals_sum_of_item_prices(tenant_a, db_super):
    """Quote.total must equal the sum of each item's computed price."""
    space_1 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
    space_2 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
    _make_pricing_rule(db_super, tenant_a.id, space_1.id)
    _make_pricing_rule(db_super, tenant_a.id, space_2.id)

    day_1 = date.today() + timedelta(days=30)
    day_2 = date.today() + timedelta(days=31)
    items = [
        PublicWizardItem(
            space_id=space_1.id, fecha=day_1, hora_inicio="10:00:00", hora_fin="12:00:00"
        ),
        PublicWizardItem(
            space_id=space_2.id, fecha=day_2, hora_inicio="09:00:00", hora_fin="15:00:00"
        ),
    ]
    payload = PublicQuoteRequestCreate(**_base_payload(items=items))

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        quote = create_public_quote_request(tenant_a.id, payload, db)
        db.commit()
        quote_id = quote.id

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        expected_1 = calculate_price(
            space_id=space_1.id,
            duration_hours=Decimal("2.00"),
            tenant_id=tenant_a.id,
            target_date=day_1,
            db=db,
        ).total_price
        expected_2 = calculate_price(
            space_id=space_2.id,
            duration_hours=Decimal("6.00"),
            tenant_id=tenant_a.id,
            target_date=day_2,
            db=db,
        ).total_price
        persisted = db.get(Quote, quote_id)
        assert persisted is not None
        assert len(persisted.items) == 2
        assert Decimal(str(persisted.total)) == expected_1 + expected_2
