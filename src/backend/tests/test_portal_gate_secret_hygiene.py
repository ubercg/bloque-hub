"""Secret-hygiene tests for the BLOQUE Portal HMAC integration (REQ-013,
design.md §9, tasks 7.1/7.2).

Design §9 lists THREE checks because a source grep alone is not enough:
  1. No credential-shaped field on any response model (this file).
  2. The secret never appears as a substring of a serialized response body,
     success or error (this file).
  3. The secret is absent from the built frontend bundle — NOT a pytest
     test, requires `npm run build`; verified manually and recorded in the
     bitácora (BIT-021).

Check #2 exercises BOTH public endpoints because they are the only two
response surfaces that ever touch a `PortalGateResult`. Every case uses
`response.text` — the raw serialized body — never `response.json()`, so a
leak inside a string value cannot hide behind dict-key access.
"""

import json
import re
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

import app.api.public as public_module
from app.api.public import FolioValidateResponse, LeadPrefillOut
from app.api.portal_gate_http import PORTAL_AUTH_FAILURE_HTTP_STATUS
from app.core.config import settings
from app.modules.crm.models import (
    CaracterEvento,
    ComoConociste,
    MontajeRequerido,
    Sector,
    TipoEvento,
)
from app.modules.inventory.models import Space
from app.modules.portal_gate.client import PortalFolioStatus, PortalGateResult, PortalUnavailableError
from app.modules.portal_gate.prefill import LeadPrefill
from app.modules.pricing.models import PricingRule
from tests.conftest import unique_portal_folio

# design §9 check #1 — anything shaped like a credential, not just the
# literal setting names, so a future field named e.g. `portal_signature`
# also fails this test rather than being missed by an exact-name check.
_SECRET_SHAPED_FIELD = re.compile(r"api_key|secret|signature", re.IGNORECASE)

_FULL_PREFILL = LeadPrefill(
    nombre_completo="Ana Torres",
    cargo_puesto="Directora",
    institucion_organizacion="Municipio Y",
    correo_institucional="ana.torres@example.com",
    telefono_contacto="5512345678",
    asistentes_estimados=150,
    fecha_tentativa="2026-08-20",
    tipo_evento_sugerido="boda",
    espacio_requerido="Salon Jacarandas",
    requerimientos_especiales="Sonido especial.",
    como_conociste_bloque="redes_sociales",
)


def _assert_secret_absent(response) -> None:
    """The configured secret must not appear anywhere in the raw body —
    success or error, gate or submit (design §9 check #2)."""
    assert settings.PORTAL_HUB_API_SECRET not in response.text


class TestSecretHygieneModelFields:
    """Task 7.1 (design §9 check #1)."""

    def test_folio_validate_response_has_no_secret_shaped_field(self):
        offenders = [
            name for name in FolioValidateResponse.model_fields if _SECRET_SHAPED_FIELD.search(name)
        ]
        assert offenders == []

    def test_lead_prefill_out_has_no_secret_shaped_field(self):
        offenders = [name for name in LeadPrefillOut.model_fields if _SECRET_SHAPED_FIELD.search(name)]
        assert offenders == []


@pytest.mark.integration
class TestSecretHygieneGateResponseBody:
    """Task 7.2 — `/api/public/quote-requests/validate-folio`, every path."""

    def _post(self, client, folio: str | None = None):
        return client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": folio or unique_portal_folio()},
        )

    def test_eligible_with_full_prefill_never_leaks_secret(self, client, monkeypatch):
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalGateResult.eligible(prefill=_FULL_PREFILL),
        )
        response = self._post(client)
        assert response.status_code == 200
        _assert_secret_absent(response)

    def test_not_eligible_never_leaks_secret(self, client, monkeypatch):
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalGateResult.of(PortalFolioStatus.NOT_ELIGIBLE),
        )
        response = self._post(client)
        assert response.status_code == 403
        _assert_secret_absent(response)

    def test_portal_unavailable_never_leaks_secret(self, client, monkeypatch):
        def _raise(folio: str):
            raise PortalUnavailableError("Portal unreachable after 3 attempts")

        monkeypatch.setattr(public_module.portal_gate_client, "validate_folio", _raise)
        response = self._post(client)
        assert response.status_code == 503
        _assert_secret_absent(response)

    def test_auth_failure_never_leaks_secret(self, client, monkeypatch):
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalGateResult.of(
                PortalFolioStatus.INTEGRATION_AUTH_FAILURE, error_code="INVALID_SIGNATURE"
            ),
        )
        response = self._post(client)
        assert response.status_code == PORTAL_AUTH_FAILURE_HTTP_STATUS
        _assert_secret_absent(response)

    def test_invalid_folio_format_never_leaks_secret(self, client):
        response = self._post(client, folio="ABC-123")
        assert response.status_code == 422
        _assert_secret_absent(response)


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


def _base_payload(space_id, fecha, **overrides) -> dict:
    payload = {
        "folio": unique_portal_folio(),
        "tipo_evento": TipoEvento.CONFERENCIA.value,
        "nombre_evento": None,
        "caracter_evento": CaracterEvento.PUBLICO.value,
        "descripcion_evento": "Evento de prueba",
        "asistentes_estimados": 50,
        "habra_prensa": False,
        "items": [
            {
                "space_id": str(space_id),
                "fecha": fecha.isoformat(),
                "hora_inicio": "10:00:00",
                "hora_fin": "12:00:00",
            }
        ],
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


def _submit(client, payload_dict: dict):
    return client.post(
        "/api/public/quote-requests",
        data={"payload": json.dumps(payload_dict)},
    )


@pytest.mark.integration
class TestSecretHygieneSubmitResponseBody:
    """Task 7.2 — `POST /api/public/quote-requests`, success and error."""

    def test_happy_path_submit_never_leaks_secret(self, client, monkeypatch, tenant_a, db_super):
        monkeypatch.setattr(settings, "DEFAULT_TENANT_ID", str(tenant_a.id))
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda folio: PortalGateResult.eligible(prefill=_FULL_PREFILL),
        )
        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=90)
        payload = _base_payload(space.id, day)

        response = _submit(client, payload)

        assert response.status_code == 201, response.text
        _assert_secret_absent(response)

    def test_not_eligible_at_submit_never_leaks_secret(self, client, monkeypatch, tenant_a, db_super):
        monkeypatch.setattr(settings, "DEFAULT_TENANT_ID", str(tenant_a.id))
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda folio: PortalGateResult.of(PortalFolioStatus.NOT_ELIGIBLE),
        )
        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=91)
        payload = _base_payload(space.id, day)

        response = _submit(client, payload)

        assert response.status_code == 403
        _assert_secret_absent(response)

    def test_auth_failure_at_submit_never_leaks_secret(self, client, monkeypatch, tenant_a, db_super):
        monkeypatch.setattr(settings, "DEFAULT_TENANT_ID", str(tenant_a.id))
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda folio: PortalGateResult.of(
                PortalFolioStatus.INTEGRATION_AUTH_FAILURE, error_code="TIMESTAMP_EXPIRED"
            ),
        )
        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=92)
        payload = _base_payload(space.id, day)

        response = _submit(client, payload)

        assert response.status_code == PORTAL_AUTH_FAILURE_HTTP_STATUS
        _assert_secret_absent(response)

    def test_payload_validation_error_never_leaks_secret(self, client):
        response = client.post(
            "/api/public/quote-requests",
            data={"payload": "not valid json"},
        )
        assert response.status_code == 422
        _assert_secret_absent(response)
