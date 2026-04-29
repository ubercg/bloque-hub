"""Unit tests for Expediente Digital Chain of Trust (T10.1)."""

import hashlib
import uuid

import pytest
from sqlalchemy.orm import Session

from app.modules.expediente.models import ExpedienteDocument
from app.modules.expediente.services import (
    _compute_chain_sha256,
    append_document,
    get_last_chain_sha256,
)


def test_compute_chain_sha256_genesis() -> None:
    """Genesis: chain_prev is None -> chain = SHA256(doc)."""
    doc_hash = hashlib.sha256(b"doc1").hexdigest()
    chain = _compute_chain_sha256(None, doc_hash)
    expected = hashlib.sha256(doc_hash.encode("utf-8")).hexdigest()
    assert chain == expected


def test_compute_chain_sha256_deterministic() -> None:
    """Same prev + same doc -> same chain."""
    prev = "a" * 64
    doc = "b" * 64
    c1 = _compute_chain_sha256(prev, doc)
    c2 = _compute_chain_sha256(prev, doc)
    assert c1 == c2


def test_compute_chain_sha256_sequential_order_matters() -> None:
    """Order of documents changes the chain (sequential)."""
    doc1 = hashlib.sha256(b"doc1").hexdigest()
    doc2 = hashlib.sha256(b"doc2").hexdigest()
    chain1 = _compute_chain_sha256(None, doc1)
    chain2 = _compute_chain_sha256(chain1, doc2)
    # If we had doc2 first then doc1, result would differ
    chain2_alt = _compute_chain_sha256(None, doc2)
    chain1_alt = _compute_chain_sha256(chain2_alt, doc1)
    assert chain2 != chain1_alt


def test_append_document_requires_reservation_or_contract(db_super: Session, tenant_a) -> None:
    """Exactly one of reservation_id or contract_id must be set."""
    tid = tenant_a.id

    with pytest.raises(ValueError, match="Exactly one of reservation_id or contract_id"):
        append_document(
            db_super,
            tenant_id=tid,
            document_type="TEST",
            doc_sha256="a" * 64,
            reservation_id=None,
            contract_id=None,
        )

    with pytest.raises(ValueError, match="Exactly one of reservation_id or contract_id"):
        append_document(
            db_super,
            tenant_id=tid,
            document_type="TEST",
            doc_sha256="a" * 64,
            reservation_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
        )


def test_append_document_genesis_and_chain(db_super: Session, tenant_a, user_a) -> None:
    """First document is genesis; second document chains correctly."""
    from app.modules.booking.models import Reservation
    from app.modules.identity.models import Tenant
    from app.modules.inventory.models import Space

    tenant = tenant_a
    space = db_super.query(Space).filter(Space.tenant_id == tenant.id).first()
    if not space:
        space = Space(
            tenant_id=tenant.id,
            name="Test Space",
            slug="test-space-expediente",
            capacidad_maxima=10,
        )
        db_super.add(space)
        db_super.commit()
        db_super.refresh(space)

        from datetime import date, time

    from app.modules.booking.models import ReservationStatus

    res = Reservation(
        tenant_id=tenant.id,
        user_id=user_a.id,
        space_id=space.id,
        fecha=date(2026, 3, 1),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        status=ReservationStatus.PENDING_SLIP,
    )
    db_super.add(res)
    db_super.commit()
    db_super.refresh(res)

    doc1_sha = hashlib.sha256(b"content1").hexdigest()
    doc1 = append_document(
        db_super,
        tenant_id=tenant.id,
        document_type="SOLICITUD_ORIGINAL",
        doc_sha256=doc1_sha,
        reservation_id=res.id,
    )
    db_super.commit()
    assert doc1.chain_prev_sha256 is None
    assert doc1.chain_sha256 == _compute_chain_sha256(None, doc1_sha)

    last = get_last_chain_sha256(db_super, reservation_id=res.id, tenant_id=tenant.id)
    assert last == doc1.chain_sha256

    doc2_sha = hashlib.sha256(b"content2").hexdigest()
    doc2 = append_document(
        db_super,
        tenant_id=tenant.id,
        document_type="COMPROBANTE",
        doc_sha256=doc2_sha,
        reservation_id=res.id,
    )
    db_super.commit()
    assert doc2.chain_prev_sha256 == doc1.chain_sha256
    expected_chain2 = _compute_chain_sha256(doc1.chain_sha256, doc2_sha)
    assert doc2.chain_sha256 == expected_chain2
