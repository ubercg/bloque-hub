"""Integration tests for the public quote-request submit endpoint (REQ-012,
Phase 4 / PR#4).

`POST /api/public/quote-requests` — multipart/form-data (`payload` JSON part +
`files[]`). Exercises the full transaction boundary from design.md §4.2:
payload validation -> file validation -> RN-004 revalidation -> availability
pre-check -> atomic persist (+ file bytes) -> commit. Portal is mocked; DB is
real Postgres via `get_db_context`.
"""

import json
from datetime import date, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

import app.api.public as public_module
from app.core.config import settings
from app.db.session import get_db_context
from app.modules.crm.models import (
    CaracterEvento,
    ComoConociste,
    Lead,
    MontajeRequerido,
    Quote,
    QuoteWizardDetails,
    QuoteWizardDocuments,
    Sector,
    ServicioApoyo,
    TipoEvento,
)
from app.modules.identity.models import User
from app.modules.inventory.models import Space
from app.modules.inventory.services import apply_soft_hold_for_quote
from app.modules.portal_gate.client import PortalFolioStatus, PortalGateResult, PortalUnavailableError
from app.modules.portal_gate.prefill import LeadPrefill
from app.modules.pricing.models import PricingRule
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
        lambda folio: PortalGateResult.eligible(),
    )


def _submit(client, payload_dict, files=None):
    return client.post(
        "/api/public/quote-requests",
        data={"payload": json.dumps(payload_dict)},
        files=files or [],
    )


def _set_default_tenant(monkeypatch, tenant_id):
    monkeypatch.setattr(settings, "DEFAULT_TENANT_ID", str(tenant_id))


def _no_rows_for(db, email: str, folio: str) -> None:
    assert db.query(Lead).filter(Lead.email == email).all() == []
    assert db.query(Quote).filter(Quote.portal_folio == folio).all() == []
    assert (
        db.query(QuoteWizardDetails)
        .filter(QuoteWizardDetails.correo_institucional == email)
        .all()
        == []
    )


@pytest.mark.integration
class TestSubmitHappyPath:
    def test_multi_item_with_documents_persists_and_returns_201(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space_1 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        space_2 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        space_3 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        for s in (space_1, space_2, space_3):
            _make_pricing_rule(db_super, tenant_a.id, s.id)

        day_1 = date.today() + timedelta(days=60)
        day_2 = date.today() + timedelta(days=61)
        day_3 = date.today() + timedelta(days=62)
        items = [
            _item_dict(space_1.id, day_1),
            _item_dict(space_2.id, day_2),
            _item_dict(space_3.id, day_3),
        ]
        payload = _base_payload(items=items)

        files = [
            ("files", ("acta.pdf", b"%PDF-1.4 fake pdf content", "application/pdf")),
            ("files", ("foto.jpg", b"\xff\xd8\xff fake jpeg content", "image/jpeg")),
        ]

        response = _submit(client, payload, files=files)

        assert response.status_code == 201, response.text
        body = response.json()
        assert "quote_id" in body
        assert Decimal(str(body["total"])) > Decimal("0")

        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            quote = db.get(Quote, body["quote_id"])
            assert quote is not None
            assert quote.portal_folio == payload["folio"]
            assert quote.tenant_id == tenant_a.id
            assert len(quote.items) == 3
            assert Decimal(str(quote.total)) == sum(
                (Decimal(str(i.precio)) for i in quote.items), Decimal("0")
            )
            assert quote.wizard_details is not None
            docs = (
                db.query(QuoteWizardDocuments)
                .filter(QuoteWizardDocuments.quote_id == quote.id)
                .all()
            )
            assert len(docs) == 2
            for doc in docs:
                assert doc.storage_key
                full_path = (
                    __import__("pathlib").Path(settings.WIZARD_DOCUMENTS_STORAGE_PATH)
                    / doc.storage_key
                )
                assert full_path.is_file()

            assert (
                db.query(User).filter(User.email == "ana.lopez@municipio.gob.mx").all()
                == []
            )
            lead = db.query(Lead).filter(Lead.id == quote.lead_id).first()
            assert lead is not None
            assert lead.email == "ana.lopez@municipio.gob.mx"

    def test_no_auth_header_required(self, client, monkeypatch, tenant_a, db_super):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=63)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        response = client.post(
            "/api/public/quote-requests",
            data={"payload": json.dumps(payload)},
        )

        assert response.status_code == 201

    def test_lead_prefill_never_appears_on_the_submit_response(
        self, client, monkeypatch, tenant_a, db_super
    ):
        """Task 5.12: `lead_prefill` is a `FolioValidateResponse`-only field —
        it must never appear on `QuoteRequestSubmitResponse`, even though the
        RN-004 revalidation call returns a `PortalGateResult` that could
        carry one."""
        _set_default_tenant(monkeypatch, tenant_a.id)
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda folio: PortalGateResult.eligible(
                prefill=LeadPrefill(
                    nombre_completo="Ana Lopez",
                    cargo_puesto=None,
                    institucion_organizacion=None,
                    correo_institucional=None,
                    telefono_contacto=None,
                    asistentes_estimados=None,
                    fecha_tentativa=None,
                    tipo_evento_sugerido=None,
                    espacio_requerido=None,
                    requerimientos_especiales=None,
                    como_conociste_bloque=None,
                )
            ),
        )

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=66)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        response = _submit(client, payload)

        assert response.status_code == 201, response.text
        assert set(response.json().keys()) == {"quote_id", "total", "email_sent"}


@pytest.mark.integration
class TestSubmitRn004Revalidation:
    def test_not_eligible_at_submit_returns_403_zero_rows(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda folio: PortalGateResult.of(PortalFolioStatus.NOT_ELIGIBLE),
        )

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=64)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        response = _submit(client, payload)

        assert response.status_code == 403
        assert "lead_prefill" not in response.json()["detail"]
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])

    def test_portal_unavailable_at_submit_returns_503_zero_rows(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)

        def _raise(folio: str):
            raise PortalUnavailableError("unreachable")

        monkeypatch.setattr(public_module.portal_gate_client, "validate_folio", _raise)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=65)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        response = _submit(client, payload)

        assert response.status_code == 503
        assert "lead_prefill" not in response.json()["detail"]
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])


@pytest.mark.integration
class TestSubmitAtomicityAndReplay:
    def test_one_of_three_items_preheld_returns_409_zero_rows(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space_1 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        space_2 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        space_3 = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        for s in (space_1, space_2, space_3):
            _make_pricing_rule(db_super, tenant_a.id, s.id)

        day_1 = date.today() + timedelta(days=70)
        day_2 = date.today() + timedelta(days=71)
        day_3 = date.today() + timedelta(days=72)

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
            _item_dict(space_1.id, day_1),
            _item_dict(space_2.id, day_2),
            _item_dict(space_3.id, day_3),
        ]
        payload = _base_payload(items=items)

        response = _submit(client, payload)

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "SLOT_UNAVAILABLE"
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])

    def test_duplicate_folio_replay_returns_409_no_second_quote(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        folio = _valid_folio()

        day_1 = date.today() + timedelta(days=80)
        payload_1 = _base_payload(folio=folio, items=[_item_dict(space.id, day_1)])
        first = _submit(client, payload_1)
        assert first.status_code == 201

        day_2 = date.today() + timedelta(days=81)
        payload_2 = _base_payload(
            folio=folio,
            items=[_item_dict(space.id, day_2)],
            correo_institucional="otro.solicitante@municipio.gob.mx",
        )
        second = _submit(client, payload_2)

        assert second.status_code == 409
        assert second.json()["detail"]["reason"] == "DUPLICATE_FOLIO"
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            quotes = db.query(Quote).filter(Quote.portal_folio == folio).all()
            assert len(quotes) == 1

    def test_soft_hold_lock_conflict_string_arg_returns_409_not_500(
        self, client, monkeypatch, tenant_a, db_super
    ):
        """PR#9 FIX 1 (BLOCKER): `apply_soft_hold_for_quote` raises
        `SlotNotAvailableError` with a STRING arg (the `with_for_update()` lock
        path), not a list of conflict dicts. The endpoint's `except
        SlotNotAvailableError` handler must not crash trying to iterate a
        string as if it were a list of dicts — it must still return a clean
        409 SLOT_UNAVAILABLE with zero rows persisted."""
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=85)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        # `check_group_availability` reports available (pre-check race window),
        # but the authoritative locked soft-hold raises with a STRING message —
        # this is the real shape `apply_soft_hold_for_quote` uses (services.py L508).
        import app.modules.crm.public_service as public_service_module
        from app.modules.inventory.services import SlotNotAvailableError

        monkeypatch.setattr(
            public_module,
            "check_group_availability",
            lambda *args, **kwargs: {"all_available": True, "conflicts": []},
        )

        def _raise_string_conflict(*args, **kwargs):
            raise SlotNotAvailableError("Slot is not available for soft hold")

        monkeypatch.setattr(
            public_service_module, "apply_soft_hold_for_quote", _raise_string_conflict
        )

        response = _submit(client, payload)

        assert response.status_code == 409, response.text
        assert response.json()["detail"]["reason"] == "SLOT_UNAVAILABLE"
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])


@pytest.mark.integration
class TestSubmitIntegrityErrorClassification:
    """PR#9 FIX 6 (WARNING): only an `IntegrityError` naming the
    `uq_quotes_portal_folio` constraint should map to 409 DUPLICATE_FOLIO —
    any other constraint violation must NOT be mislabeled as a duplicate-folio
    replay (it should surface as an unexpected 500, not a wrong 409)."""

    def test_unrelated_integrity_error_is_not_labeled_duplicate_folio(
        self, client, monkeypatch, tenant_a, db_super
    ):
        from sqlalchemy.exc import IntegrityError

        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=114)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        class _FakeDiag:
            constraint_name = "some_other_unrelated_constraint"

        class _FakeOrig(Exception):
            diag = _FakeDiag()

        def _raise_unrelated_integrity_error(*args, **kwargs):
            raise IntegrityError(
                "INSERT INTO quote_items ...", {}, _FakeOrig("not a folio conflict")
            )

        monkeypatch.setattr(
            public_module, "create_public_quote_request", _raise_unrelated_integrity_error
        )

        with pytest.raises(IntegrityError):
            _submit(client, payload)

        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])


@pytest.mark.integration
class TestSubmitServiciosApoyo:
    """servicios_apoyo is a FIXED closed enum (REQ-012 §4.5), NOT a catalog
    lookup — persisted verbatim on quote_wizard_details, not priced (PR#8)."""

    def test_selected_servicios_persist_on_wizard_details(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=94)
        selected = [
            ServicioApoyo.EQUIPO_AUDIOVISUAL.value,
            ServicioApoyo.COFFEE_BREAK.value,
        ]
        payload = _base_payload(items=[_item_dict(space.id, day)], servicios_apoyo=selected)

        response = _submit(client, payload)

        assert response.status_code == 201, response.text
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            quote = db.get(Quote, response.json()["quote_id"])
            assert quote.wizard_details.servicios_apoyo == selected

    def test_invalid_servicio_value_returns_422_zero_rows(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=95)
        payload = _base_payload(
            items=[_item_dict(space.id, day)],
            servicios_apoyo=["Servicio inventado que no existe"],
        )

        response = _submit(client, payload)

        assert response.status_code == 422
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])


@pytest.mark.integration
class TestSubmitTenantResolution:
    def test_persisted_rows_carry_default_tenant_id(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=90)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        response = _submit(client, payload)
        assert response.status_code == 201

        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            quote = db.get(Quote, response.json()["quote_id"])
            assert quote.tenant_id == tenant_a.id


@pytest.mark.integration
class TestSubmitFieldLengthLimits:
    """PR#9 FIX 2 (CRITICAL): unbounded string/int fields let a client send a
    payload the DB column cannot hold (String(N) truncation -> DataError) or
    an int overflowing Postgres int4 -> 500 instead of a clean 422, and (when
    files were already written) orphaned files on disk. All three must be
    rejected by Pydantic (422) before any DB write or file write happens."""

    def test_over_length_nombre_completo_returns_422_zero_rows(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=110)
        payload = _base_payload(
            items=[_item_dict(space.id, day)],
            nombre_completo="A" * 10_000,
        )

        response = _submit(client, payload)

        assert response.status_code == 422, response.text
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])

    def test_asistentes_estimados_beyond_int4_returns_422_zero_rows(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=111)
        payload = _base_payload(
            items=[_item_dict(space.id, day)],
            asistentes_estimados=99_999_999_999,
        )

        response = _submit(client, payload)

        assert response.status_code == 422, response.text
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])

    def test_giant_no_whitespace_descripcion_evento_returns_422_zero_rows(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=112)
        # A single no-whitespace "word" bypasses the 300-word RN-006 rule but
        # must still be rejected by a character cap.
        payload = _base_payload(
            items=[_item_dict(space.id, day)],
            descripcion_evento="x" * 50_000,
        )

        response = _submit(client, payload)

        assert response.status_code == 422, response.text
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])


@pytest.mark.integration
class TestSubmitUnexpectedExceptionCleanup:
    """PR#9 FIX 3 (CRITICAL): file bytes are written to disk BEFORE
    `create_public_quote_request` is called and the transaction commits.
    Cleanup previously only ran inside the 4 explicitly-caught exception
    types — any OTHER unexpected exception left orphaned files on disk with
    no DB row referencing them. Cleanup must run on ANY failure before
    commit, regardless of exception type."""

    def test_unexpected_exception_after_files_written_cleans_up_disk(
        self, client, monkeypatch, tenant_a, db_super
    ):
        import pathlib

        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=113)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        def _raise_unexpected(*args, **kwargs):
            raise RuntimeError("unexpected failure after files were written")

        monkeypatch.setattr(
            public_module, "create_public_quote_request", _raise_unexpected
        )

        storage_dir = pathlib.Path(settings.WIZARD_DOCUMENTS_STORAGE_PATH)
        files = [("files", ("acta.pdf", b"%PDF-1.4 fake pdf content", "application/pdf"))]

        with pytest.raises(RuntimeError):
            _submit(client, payload, files=files)

        # No orphaned files should remain for this tenant after the crash.
        tenant_dir = storage_dir / str(tenant_a.id)
        leftover = list(tenant_dir.glob("*")) if tenant_dir.exists() else []
        assert leftover == []
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])


@pytest.mark.integration
class TestSubmitFileValidation:
    def test_invalid_mime_rejected_zero_rows(self, client, monkeypatch, tenant_a, db_super):
        _set_default_tenant(monkeypatch, tenant_a.id)
        called = {"count": 0}

        def _spy(folio: str):
            called["count"] += 1
            return PortalGateResult.eligible()

        monkeypatch.setattr(public_module.portal_gate_client, "validate_folio", _spy)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=91)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        files = [("files", ("malware.exe", b"binary content", "application/x-msdownload"))]
        response = _submit(client, payload, files=files)

        assert response.status_code == 422
        assert called["count"] == 0
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])

    def test_oversized_file_rejected_zero_rows(self, client, monkeypatch, tenant_a, db_super):
        _set_default_tenant(monkeypatch, tenant_a.id)
        monkeypatch.setattr(settings, "MAX_KYC_FILE_BYTES", 10)
        called = {"count": 0}

        def _spy(folio: str):
            called["count"] += 1
            return PortalGateResult.eligible()

        monkeypatch.setattr(public_module.portal_gate_client, "validate_folio", _spy)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=92)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        files = [("files", ("big.pdf", b"0123456789ABCDEF", "application/pdf"))]
        response = _submit(client, payload, files=files)

        assert response.status_code == 422
        assert called["count"] == 0
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])

    def test_too_many_files_rejected_before_any_file_written(
        self, client, monkeypatch, tenant_a, db_super
    ):
        """PR#9 FIX 8 (WARNING): a file COUNT cap must exist in the app
        itself (not only at the nginx layer) — rejected with 422 BEFORE any
        file bytes are read/written or the DB is touched."""
        import pathlib

        _set_default_tenant(monkeypatch, tenant_a.id)
        monkeypatch.setattr(settings, "MAX_WIZARD_FILES", 3)
        called = {"count": 0}

        def _spy(folio: str):
            called["count"] += 1
            return PortalGateResult.eligible()

        monkeypatch.setattr(public_module.portal_gate_client, "validate_folio", _spy)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=96)
        payload = _base_payload(items=[_item_dict(space.id, day)])

        files = [
            ("files", (f"doc{i}.pdf", b"%PDF-1.4 fake pdf content", "application/pdf"))
            for i in range(4)
        ]
        response = _submit(client, payload, files=files)

        assert response.status_code == 422, response.text
        assert called["count"] == 0
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])
        storage_dir = pathlib.Path(settings.WIZARD_DOCUMENTS_STORAGE_PATH)
        tenant_dir = storage_dir / str(tenant_a.id)
        leftover = list(tenant_dir.glob("*")) if tenant_dir.exists() else []
        assert leftover == []


@pytest.mark.integration
class TestSubmitPayloadValidation:
    def test_malformed_json_payload_returns_422(self, client, monkeypatch, tenant_a):
        _set_default_tenant(monkeypatch, tenant_a.id)
        response = client.post(
            "/api/public/quote-requests",
            data={"payload": "not-json"},
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "overrides",
        [
            {"tipo_evento": TipoEvento.OTRO.value, "nombre_evento": None},  # RN-008
            {"sector": Sector.OTRO.value, "sector_otro": None},  # RN-009
            {
                "como_conociste_bloque": ComoConociste.OTRO.value,
                "como_conociste_otro": None,
            },  # RN-010
            {"material_externo": True, "material_externo_detalle": None},  # RN-011
            {"descripcion_evento": " ".join(["palabra"] * 301)},  # RN-006
            {"asistentes_estimados": 0},  # RN-007
            {
                "acepta_info_correcta_autorizacion": True,
                "acepta_reglamento_y_aviso_privacidad": False,
            },  # RN-014
            {
                "acepta_info_correcta_autorizacion": False,
                "acepta_reglamento_y_aviso_privacidad": False,
            },  # RN-014
        ],
    )
    def test_conditional_validation_matrix_returns_422_zero_rows(
        self, client, monkeypatch, tenant_a, db_super, overrides
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _mock_eligible(monkeypatch)

        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=93)
        payload = _base_payload(items=[_item_dict(space.id, day)], **overrides)

        response = _submit(client, payload)

        assert response.status_code == 422
        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            _no_rows_for(db, payload["correo_institucional"], payload["folio"])
