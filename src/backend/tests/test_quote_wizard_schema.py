"""Integration tests for the quote-request-folio (REQ-012) Phase 1 data model:
`Quote.portal_folio`, `QuoteWizardDetails`, `QuoteWizardDocuments`.

Covers:
- Insert + read-back of all three under a tenant-scoped (RLS-applying) session.
- Partial unique index on `portal_folio`: rejects duplicate non-null folios,
  allows multiple NULLs.
- RLS isolates `quote_wizard_details` / `quote_wizard_documents` rows by tenant.
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

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
    TipoEvento,
)


def _make_lead(db, tenant_id) -> Lead:
    lead = Lead(tenant_id=tenant_id, name="Solicitante Wizard", email="wizard@test.com")
    db.add(lead)
    db.flush()
    return lead


def _make_quote(db, tenant_id, lead_id, portal_folio: str | None) -> Quote:
    quote = Quote(
        tenant_id=tenant_id,
        lead_id=lead_id,
        total=1000,
        portal_folio=portal_folio,
    )
    db.add(quote)
    db.flush()
    return quote


@pytest.mark.integration
def test_insert_and_read_back_wizard_details_and_documents(tenant_a):
    """Insert Quote(portal_folio) + QuoteWizardDetails + QuoteWizardDocuments under a
    tenant-scoped session and read them back."""
    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        lead = _make_lead(db, tenant_a.id)
        folio = f"BCE-20260715-172822-{uuid.uuid4().hex[:4]}"
        quote = _make_quote(db, tenant_a.id, lead.id, folio)

        details = QuoteWizardDetails(
            tenant_id=tenant_a.id,
            quote_id=quote.id,
            tipo_evento=TipoEvento.CONFERENCIA,
            nombre_evento=None,
            caracter_evento=CaracterEvento.PUBLICO,
            descripcion_evento="Evento de prueba",
            asistentes_estimados=50,
            habra_prensa=False,
            nombre_completo="Juan Perez",
            cargo_puesto="Director",
            institucion_organizacion="Municipio X",
            sector=Sector.GOBIERNO_MUNICIPAL_ESTATAL_FEDERAL,
            sector_otro=None,
            correo_institucional="juan.perez@municipio.gob.mx",
            telefono_contacto="5555555555",
            responsable_sitio_nombre=None,
            responsable_sitio_telefono=None,
            como_conociste_bloque=ComoConociste.REDES_SOCIALES,
            como_conociste_otro=None,
            montaje_requerido=MontajeRequerido.TEATRO,
            requerimientos_especiales=None,
            material_externo=False,
            material_externo_detalle=None,
            acepta_info_correcta_autorizacion=True,
            acepta_reglamento_y_aviso_privacidad=True,
        )
        db.add(details)

        document = QuoteWizardDocuments(
            tenant_id=tenant_a.id,
            quote_id=quote.id,
            storage_key="wizard_documents/2026/07/some-file.pdf",
            mime_type="application/pdf",
            size_bytes=12345,
            original_filename="carta-responsiva.pdf",
        )
        db.add(document)
        db.commit()
        db.refresh(quote)

        assert quote.portal_folio == folio
        assert quote.wizard_details is not None
        assert quote.wizard_details.tipo_evento == TipoEvento.CONFERENCIA
        assert quote.wizard_details.sector == Sector.GOBIERNO_MUNICIPAL_ESTATAL_FEDERAL
        assert quote.wizard_details.acepta_info_correcta_autorizacion is True
        assert quote.wizard_details.acepta_reglamento_y_aviso_privacidad is True
        assert len(quote.wizard_documents) == 1
        assert quote.wizard_documents[0].storage_key == document.storage_key
        assert quote.wizard_documents[0].mime_type == "application/pdf"


@pytest.mark.integration
def test_internal_quotes_allow_multiple_null_portal_folios(tenant_a):
    """Internal COMMERCIAL quotes leave portal_folio NULL; multiple NULLs must coexist."""
    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        lead = _make_lead(db, tenant_a.id)
        _make_quote(db, tenant_a.id, lead.id, None)
        _make_quote(db, tenant_a.id, lead.id, None)
        db.commit()  # must not raise


@pytest.mark.integration
def test_duplicate_portal_folio_rejected_by_partial_unique_index(tenant_a):
    """A duplicate non-null portal_folio must violate the partial unique index."""
    folio = f"BCE-20260715-172822-{uuid.uuid4().hex[:4]}"
    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        lead = _make_lead(db, tenant_a.id)
        _make_quote(db, tenant_a.id, lead.id, folio)
        db.commit()

    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        lead2 = _make_lead(db, tenant_a.id)
        with pytest.raises(IntegrityError):
            _make_quote(db, tenant_a.id, lead2.id, folio)
        db.rollback()


@pytest.mark.integration
def test_rls_isolates_wizard_details_and_documents_by_tenant(tenant_a, tenant_b):
    """quote_wizard_details / quote_wizard_documents rows are isolated per tenant by RLS."""
    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        lead = _make_lead(db, tenant_a.id)
        quote = _make_quote(db, tenant_a.id, lead.id, None)
        details = QuoteWizardDetails(
            tenant_id=tenant_a.id,
            quote_id=quote.id,
            tipo_evento=TipoEvento.TALLER,
            caracter_evento=CaracterEvento.PRIVADO,
            asistentes_estimados=10,
            habra_prensa=False,
            nombre_completo="Tenant A Solicitante",
            sector=Sector.EMPRESA_PRIVADA,
            correo_institucional="a@tenant-a.com",
            telefono_contacto="5551112233",
            como_conociste_bloque=ComoConociste.SITIO_WEB_MUNICIPIO,
            montaje_requerido=MontajeRequerido.AULA,
            material_externo=False,
            acepta_info_correcta_autorizacion=True,
            acepta_reglamento_y_aviso_privacidad=True,
        )
        db.add(details)
        document = QuoteWizardDocuments(
            tenant_id=tenant_a.id,
            quote_id=quote.id,
            storage_key="wizard_documents/tenant-a/file.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            original_filename="doc.pdf",
        )
        db.add(document)
        db.commit()
        quote_id = quote.id

    # tenant_b session must not see tenant_a's rows
    with get_db_context(tenant_id=str(tenant_b.id), role=None) as db:
        details_visible = (
            db.query(QuoteWizardDetails)
            .filter(QuoteWizardDetails.quote_id == quote_id)
            .all()
        )
        documents_visible = (
            db.query(QuoteWizardDocuments)
            .filter(QuoteWizardDocuments.quote_id == quote_id)
            .all()
        )
        assert details_visible == []
        assert documents_visible == []

    # tenant_a session sees its own rows
    with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
        details_visible = (
            db.query(QuoteWizardDetails)
            .filter(QuoteWizardDetails.quote_id == quote_id)
            .all()
        )
        assert len(details_visible) == 1
