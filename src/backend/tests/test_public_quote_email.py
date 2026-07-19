"""Integration tests for the best-effort confirmation email on submit
(REQ-012, Phase 5 / PR#5, RN-016).

`send_email` is mocked; DB is real Postgres via `get_db_context`. Verifies
the email is attempted after commit, never fails the request, and never
writes a `NotificationLog` row (it FKs reservations, not quotes).
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

import app.api.public as public_module
from app.db.session import get_db_context
from app.modules.inventory.models import Space
from app.modules.notifications.models import NotificationLog
from app.modules.portal_gate.client import PortalFolioStatus
from app.modules.pricing.models import PricingRule
from app.modules.crm.models import (
    CaracterEvento,
    ComoConociste,
    MontajeRequerido,
    Sector,
    TipoEvento,
)
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
    return unique_portal_folio()


def _item_dict(space_id, fecha, hora_inicio="10:00:00", hora_fin="12:00:00") -> dict:
    return {
        "space_id": str(space_id),
        "fecha": fecha.isoformat(),
        "hora_inicio": hora_inicio,
        "hora_fin": hora_fin,
    }


def _base_payload(**overrides) -> dict:
    payload = {
        "folio": _valid_folio(),
        "tipo_evento": TipoEvento.CONFERENCIA.value,
        "nombre_evento": None,
        "caracter_evento": CaracterEvento.PUBLICO.value,
        "descripcion_evento": "Evento de prueba",
        "asistentes_estimados": 50,
        "habra_prensa": False,
        "items": [],
        "nombre_completo": "Ana Lopez",
        "cargo_puesto": "Coordinadora",
        "institucion_organizacion": "Municipio Y",
        "sector": Sector.GOBIERNO_MUNICIPAL_ESTATAL_FEDERAL.value,
        "sector_otro": None,
        "correo_institucional": "ana.lopez@municipio.gob.mx",
        "telefono_contacto": "5555555556",
        "responsable_sitio_nombre": None,
        "responsable_sitio_telefono": None,
        "como_conociste_bloque": ComoConociste.REDES_SOCIALES.value,
        "como_conociste_otro": None,
        "servicios_apoyo": [],
        "montaje_requerido": MontajeRequerido.TEATRO.value,
        "requerimientos_especiales": None,
        "material_externo": False,
        "material_externo_detalle": None,
        "acepta_info_correcta_autorizacion": True,
        "acepta_reglamento_y_aviso_privacidad": True,
    }
    payload.update(overrides)
    return payload


def _mock_eligible(monkeypatch):
    monkeypatch.setattr(
        public_module.portal_gate_client,
        "validate_folio",
        lambda folio: PortalFolioStatus.ELIGIBLE,
    )


def _submit(client, payload_dict, files=None):
    return client.post(
        "/api/public/quote-requests",
        data={"payload": json.dumps(payload_dict)},
        files=files or [],
    )


def _set_default_tenant(monkeypatch, tenant_id):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DEFAULT_TENANT_ID", str(tenant_id))


@pytest.mark.integration
class TestSubmitConfirmationEmail:
    def test_send_email_raises_submit_still_succeeds_email_sent_false(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        def _raise(**kwargs):
            raise RuntimeError("SMTP down")

        monkeypatch.setattr(public_module, "send_email", _raise)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=100)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        response = _submit(client, payload)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["email_sent"] is False

        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            assert db.query(NotificationLog).all() == []

    def test_send_email_succeeds_email_sent_true_called_with_requester_email(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        calls = []

        def _fake_send_email(**kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(public_module, "send_email", _fake_send_email)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=101)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        response = _submit(client, payload)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["email_sent"] is True

        assert len(calls) == 1
        assert calls[0]["to"] == payload["correo_institucional"]

        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            assert db.query(NotificationLog).all() == []
