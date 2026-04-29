"""Tests para credit_balances (T10.5): crear y aplicar saldo a favor."""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.modules.finance.credit_balances import (
    apply_credit_to_reservation,
    create_credit,
    get_available_credits,
)
from app.modules.finance.models import CreditBalance


def test_create_credit(db_super, tenant_a) -> None:
    """Crear crédito vinculado a cfdi_uuid."""
    cred = create_credit(
        db_super,
        tenant_id=tenant_a.id,
        cfdi_uuid=uuid.uuid4(),
        monto=500.0,
    )
    db_super.commit()
    assert cred.saldo_restante == 500.0
    assert cred.monto_original == 500.0


def test_apply_credit_reduces_saldo(db_super, tenant_a, user_a) -> None:
    """Aplicar crédito a reserva reduce saldo_restante."""
    from app.modules.booking.models import Reservation, ReservationStatus
    from app.modules.inventory.models import Space
    from datetime import date, time

    space = db_super.query(Space).filter(Space.tenant_id == tenant_a.id).first()
    if not space:
        space = Space(
            tenant_id=tenant_a.id,
            name="Space Credit",
            slug="space-credit-test",
            capacidad_maxima=10,
        )
        db_super.add(space)
        db_super.commit()
        db_super.refresh(space)

    res = Reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space.id,
        fecha=date(2026, 6, 1),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        status=ReservationStatus.CONFIRMED,
    )
    db_super.add(res)
    db_super.commit()
    db_super.refresh(res)

    cred = create_credit(
        db_super,
        tenant_id=tenant_a.id,
        cfdi_uuid=uuid.uuid4(),
        monto=200.0,
    )
    db_super.commit()
    db_super.refresh(cred)

    applied = apply_credit_to_reservation(
        db_super,
        credit_id=cred.id,
        reservation_id=res.id,
        monto_a_aplicar=150.0,
    )
    db_super.commit()
    assert applied is not None
    db_super.refresh(applied)
    assert float(applied.saldo_restante) == 50.0
    assert applied.aplicado_a_reservation_id == res.id


def test_apply_credit_twice_rejected(db_super, tenant_a, user_a) -> None:
    """No se puede aplicar el mismo crédito dos veces."""
    from app.modules.booking.models import Reservation, ReservationStatus
    from app.modules.inventory.models import Space
    from datetime import date, time

    space = db_super.query(Space).filter(Space.tenant_id == tenant_a.id).first()
    if not space:
        space = Space(
            tenant_id=tenant_a.id,
            name="Space Credit 2",
            slug="space-credit-test-2",
            capacidad_maxima=10,
        )
        db_super.add(space)
        db_super.commit()
        db_super.refresh(space)

    res1 = Reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space.id,
        fecha=date(2026, 7, 1),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        status=ReservationStatus.CONFIRMED,
    )
    db_super.add(res1)
    db_super.commit()
    db_super.refresh(res1)

    cred = create_credit(
        db_super,
        tenant_id=tenant_a.id,
        cfdi_uuid=uuid.uuid4(),
        monto=100.0,
    )
    db_super.commit()
    db_super.refresh(cred)

    apply_credit_to_reservation(db_super, credit_id=cred.id, reservation_id=res1.id, monto_a_aplicar=100.0)
    db_super.commit()

    second = apply_credit_to_reservation(db_super, credit_id=cred.id, reservation_id=res1.id, monto_a_aplicar=50.0)
    assert second is None
