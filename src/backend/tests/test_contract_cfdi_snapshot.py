import pytest
from uuid import uuid4
from datetime import date, time, datetime, timedelta
from decimal import Decimal

from app.modules.finance.services import generate_contract, generate_cfdi, check_quote_mutability, ContractImmutableError, CFDIAmountMismatchError, ImmutableQuoteError
from app.modules.crm.models import Quote, QuoteItem, QuoteStatus, Contract, ContractStatus, QuoteAdditionalService
from app.modules.finance.models import CfdiDocument, CfdiEstado
from app.modules.booking.models import Reservation, ReservationStatus, EventPhase
from app.modules.inventory.models import Inventory, Space, SlotStatus
from app.modules.crm.models import Lead

def setup_quote_and_reservation(db_super, tenant_a, lead_a, space_parent, user_a):
    # Setup quote digitally approved with a frozen snapshot
    quote = Quote(tenant_id=tenant_a.id, lead_id=lead_a.id, status=QuoteStatus.DIGITAL_APPROVED, total=1000.0)
    db_super.add(quote)
    db_super.flush()
    
    item = QuoteItem(
        quote_id=quote.id,
        space_id=space_parent.id,
        fecha=date.today(),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        precio=1000.0,
        subtotal_frozen=1000.0,
        uma_snapshot=108.57,
        uma_snapshot_date=date.today() - timedelta(days=1),
        item_order=0
    )
    db_super.add(item)
    db_super.flush()
    
    res = Reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space_parent.id,
        fecha=date.today(),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        status=ReservationStatus.CONFIRMED,
        phase=EventPhase.USO,
        multi_day=False,
    )
    db_super.add(res)
    db_super.flush()
    
    inv = Inventory(
        space_id=space_parent.id,
        tenant_id=tenant_a.id,
        fecha=date.today(),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        estado=SlotStatus.RESERVED,
        quote_id=quote.id,
        reservation_id=res.id
    )
    db_super.add(inv)
    db_super.flush()
    
    return quote, res


def test_contract_uses_frozen_snapshot_not_realtime(db_super, tenant_a, user_a):
    space_parent = Space(tenant_id=tenant_a.id, name="Test Space", slug="test-space-419ab80f", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space_parent)
    db_super.commit()
    lead_a = Lead(tenant_id=tenant_a.id, name="Test Lead", email="test@test.com")
    db_super.add(lead_a)
    db_super.commit()
    
    quote, _ = setup_quote_and_reservation(db_super, tenant_a, lead_a, space_parent, user_a)
    
    # Generate contract
    contract = generate_contract(quote.id, tenant_a.id, db_super)
    assert contract is not None
    assert contract.contract_snapshot_hash is not None
    assert len(contract.contract_snapshot_hash) == 64  # SHA256 length


def test_contract_immutable_post_signing(db_super, tenant_a, user_a):
    space_parent = Space(tenant_id=tenant_a.id, name="Test Space", slug=f"test-space-{uuid4().hex[:8]}", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space_parent)
    db_super.commit()
    lead_a = Lead(tenant_id=tenant_a.id, name="Test Lead 2", email="test@test.com")
    db_super.add(lead_a)
    db_super.commit()
    
    quote, _ = setup_quote_and_reservation(db_super, tenant_a, lead_a, space_parent, user_a)
    contract = generate_contract(quote.id, tenant_a.id, db_super)
    
    # Mark as signed
    contract.status = ContractStatus.SIGNED
    db_super.flush()
    
    with pytest.raises(ContractImmutableError):
        generate_contract(quote.id, tenant_a.id, db_super)


def test_cfdi_requires_contract_signed(db_super, tenant_a, user_a):
    space_parent = Space(tenant_id=tenant_a.id, name="Test Space", slug=f"test-space-{uuid4().hex[:8]}", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space_parent)
    db_super.commit()
    lead_a = Lead(tenant_id=tenant_a.id, name="Test Lead 3", email="test@test.com")
    db_super.add(lead_a)
    db_super.commit()
    
    quote, res = setup_quote_and_reservation(db_super, tenant_a, lead_a, space_parent, user_a)
    contract = generate_contract(quote.id, tenant_a.id, db_super)
    
    with pytest.raises(ValueError, match="CFDI requires a signed contract"):
        generate_cfdi(res.id, tenant_a.id, db_super)


def test_cfdi_amount_matches_snapshot(db_super, tenant_a, user_a):
    space_parent = Space(tenant_id=tenant_a.id, name="Test Space", slug=f"test-space-{uuid4().hex[:8]}", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space_parent)
    db_super.commit()
    lead_a = Lead(tenant_id=tenant_a.id, name="Test Lead 4", email="test@test.com")
    db_super.add(lead_a)
    db_super.commit()
    
    quote, res = setup_quote_and_reservation(db_super, tenant_a, lead_a, space_parent, user_a)
    contract = generate_contract(quote.id, tenant_a.id, db_super)
    contract.status = ContractStatus.SIGNED
    db_super.flush()
    
    cfdi = generate_cfdi(res.id, tenant_a.id, db_super)
    
    # Subtotal frozen was 1000.0, so CFDI total should sum up to 1000.0
    total_cfdi = Decimal(str(cfdi.monto)) + Decimal(str(cfdi.iva_monto))
    assert total_cfdi == Decimal('1000.00')


def test_quote_modification_blocked_post_contract(db_super, tenant_a, user_a):
    space_parent = Space(tenant_id=tenant_a.id, name="Test Space", slug=f"test-space-{uuid4().hex[:8]}", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space_parent)
    db_super.commit()
    lead_a = Lead(tenant_id=tenant_a.id, name="Test Lead 5", email="test@test.com")
    db_super.add(lead_a)
    db_super.commit()
    
    quote, res = setup_quote_and_reservation(db_super, tenant_a, lead_a, space_parent, user_a)
    contract = generate_contract(quote.id, tenant_a.id, db_super)
    contract.status = ContractStatus.SIGNED
    db_super.flush()
    
    with pytest.raises(ImmutableQuoteError):
        check_quote_mutability(quote, db_super)
