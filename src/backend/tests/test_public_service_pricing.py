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
from app.modules.crm.public_service import (
    _package_price_for_duration,
    create_public_quote_request,
    price_wizard_items,
)
from app.modules.crm.schemas import PublicQuoteRequestCreate, PublicWizardItem
from app.modules.inventory.models import Space
from app.modules.pricing.models import PricingRule
from app.modules.pricing.services import NoPricingRuleError, get_pricing_rule_by_space
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
def test_pricing_matches_package_decomposition(tenant_a, db_super):
    """Wizard pricing matches Detalle package decomposition (not hybrid tier jump)."""
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
        rule = get_pricing_rule_by_space(db, tenant_a.id, space.id, event_day)
        assert rule is not None
        # 2h → 2 × extra_hour_rate (20) = 40; hybrid would have charged base_6h=100
        expected = _package_price_for_duration(Decimal("2.00"), rule)
        assert expected == Decimal("40.00")

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        persisted = db.get(Quote, quote_id)
        assert persisted is not None
        assert Decimal(str(persisted.total)) == expected
        assert len(persisted.items) == 1
        assert Decimal(str(persisted.items[0].precio)) == expected


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
        expected_1 = price_wizard_items(
            [
                PublicWizardItem(
                    space_id=space_1.id,
                    fecha=day_1,
                    hora_inicio="10:00:00",
                    hora_fin="12:00:00",
                )
            ],
            tenant_a.id,
            db,
        )[0]
        expected_2 = price_wizard_items(
            [
                PublicWizardItem(
                    space_id=space_2.id,
                    fecha=day_2,
                    hora_inicio="09:00:00",
                    hora_fin="15:00:00",
                )
            ],
            tenant_a.id,
            db,
        )[0]
        persisted = db.get(Quote, quote_id)
        assert persisted is not None
        assert len(persisted.items) == 2
        assert Decimal(str(persisted.total)) == expected_1 + expected_2


@pytest.mark.integration
def test_contiguous_slots_use_package_tariff_not_per_slot_base_6h(tenant_a, db_super):
    """Seven contiguous 1h slots must price as one 7h block (base_6h + 1×extra),
    not 7× base_6h (the bandeja bug when each slot was previewed alone)."""
    space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
    _make_pricing_rule(db_super, tenant_a.id, space.id)
    day = date.today() + timedelta(days=40)
    hours = [
        ("10:00:00", "11:00:00"),
        ("11:00:00", "12:00:00"),
        ("12:00:00", "13:00:00"),
        ("13:00:00", "14:00:00"),
        ("14:00:00", "15:00:00"),
        ("15:00:00", "16:00:00"),
        ("16:00:00", "17:00:00"),
    ]
    items = [
        PublicWizardItem(space_id=space.id, fecha=day, hora_inicio=a, hora_fin=b)
        for a, b in hours
    ]
    payload = PublicQuoteRequestCreate(**_base_payload(items=items))

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        quote = create_public_quote_request(tenant_a.id, payload, db)
        db.commit()
        quote_id = quote.id
        rule = get_pricing_rule_by_space(db, tenant_a.id, space.id, day)
        assert rule is not None
        expected_block = _package_price_for_duration(Decimal("7.00"), rule)
        # base_6h=100 + 1*extra=20 → 120 (not 7*100 hybrid-per-slot, not base_12h=180)
        assert expected_block == Decimal("120.00")

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        persisted = db.get(Quote, quote_id)
        assert persisted is not None
        assert len(persisted.items) == 7
        assert Decimal(str(persisted.total)) == expected_block
        assert sum(Decimal(str(i.precio)) for i in persisted.items) == expected_block
